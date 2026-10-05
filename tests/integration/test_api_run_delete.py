"""TASK-30 API: delete is operator-only and refuses an active scan."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.api.auth import hash_password
from metatracer.core.config import Settings
from metatracer.db.models import Run, RunStatus, User, UserRole
from metatracer.db.repositories import RunRepository


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/delete-api.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": False,
        "api_rate_limit_per_minute": 0,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with application.router.lifespan_context(application):
        yield application


async def test_delete_active_run_is_409(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.example"]',
                allowed_scope='["target.example"]',
                scope_confirmed=True,
                status=RunStatus.running,
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.delete(f"/api/runs/{run.id}")
    assert response.status_code == 409


async def test_viewer_cannot_delete(tmp_path: Path) -> None:
    application = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    async with application.router.lifespan_context(application):
        async with application.state.session_factory() as session:
            session.add(
                User(
                    username="viewer",
                    password_hash=hash_password("viewer-password-123"),
                    role=UserRole.viewer,
                )
            )
            await session.commit()
            run = await RunRepository(session).create(
                Run(
                    target_input='["target.example"]',
                    allowed_scope='["target.example"]',
                    scope_confirmed=True,
                    status=RunStatus.completed,
                )
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as viewer:
            page = await viewer.get("/login")
            assert page.status_code == 200
            csrf = viewer.cookies.get("csrf_token", "")
            logged = await viewer.post(
                "/api/auth/login",
                json={"username": "viewer", "password": "viewer-password-123"},
                headers={"X-CSRF-Token": csrf},
            )
            assert logged.status_code == 200
            response = await viewer.delete(
                f"/api/runs/{run.id}",
                headers={"X-CSRF-Token": logged.json()["csrf_token"]},
            )
            assert response.status_code == 403
