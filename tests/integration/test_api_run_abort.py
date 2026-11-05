"""TASK-28 API: startup recovery and POST /api/runs/{id}/abort."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.api.auth import hash_password
from metatracer.core.config import Settings
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Run, RunStatus, User, UserRole
from metatracer.db.repositories import RunRepository
from metatracer.services.orchestrator import INTERRUPTED_MESSAGE


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/abort-api.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


async def _seed_open_run(database_url: str) -> str:
    engine = create_db_engine(database_url)
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.com"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.running,
            )
        )
        run.started_at = datetime(2020, 1, 1, tzinfo=UTC)
        run = await RunRepository(session).update(run)
        run_id = run.id
    await engine.dispose()
    return run_id


async def test_app_startup_aborts_orphaned_running_run(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_id = await _seed_open_run(settings.database_url)
    app = create_app(settings, reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session:
            stored = await RunRepository(session).get(run_id)
    assert stored is not None
    assert stored.status is RunStatus.aborted
    assert stored.error_message == INTERRUPTED_MESSAGE
    assert stored.completed_at is not None


@pytest.fixture()
async def open_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        yield app


async def test_abort_completed_run_is_409(open_app: FastAPI) -> None:
    async with open_app.state.session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.com"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=open_app), base_url="http://testserver"
    ) as client:
        response = await client.post(f"/api/runs/{run.id}/abort")
    assert response.status_code == 409


async def test_resume_completed_run_is_409(open_app: FastAPI) -> None:
    async with open_app.state.session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.com"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=open_app), base_url="http://testserver"
    ) as client:
        response = await client.post(f"/api/runs/{run.id}/resume")
    assert response.status_code == 409


async def test_abort_missing_run_is_404(open_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=open_app), base_url="http://testserver"
    ) as client:
        response = await client.post("/api/runs/does-not-exist/abort")
    assert response.status_code == 404


@pytest.fixture()
async def auth_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    async with app.router.lifespan_context(app):
        yield app


async def _login(client: httpx.AsyncClient, username: str, password: str) -> str:
    page = await client.get("/api/auth/me")
    # Signed out answers 401, but the pre-session CSRF token is issued.
    assert page.status_code in (200, 401)
    csrf = client.cookies.get("csrf_token", "")
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


async def test_abort_without_csrf_and_as_viewer_is_403(auth_app: FastAPI) -> None:
    async with auth_app.state.session_factory() as session:
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
                target_input='["target.com"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.running,
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
    ) as operator:
        csrf = await _login(operator, "operator", "test-password-123")
        missing = await operator.post(f"/api/runs/{run.id}/abort")
        assert missing.status_code == 403
        allowed = await operator.post(
            f"/api/runs/{run.id}/abort", headers={"X-CSRF-Token": csrf}
        )
        # The run is not an in-process task, so abort persists it.
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "aborted"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
    ) as viewer:
        await _login(viewer, "viewer", "viewer-password-123")
        response = await viewer.post(
            f"/api/runs/{run.id}/abort",
            headers={"X-CSRF-Token": viewer.cookies.get("csrf_token", "")},
        )
        assert response.status_code == 403
