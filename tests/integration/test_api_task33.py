"""TASK-33 API: terminal SSE without history, login lockout, setup race, readiness."""

import asyncio
from pathlib import Path

import httpx
from sqlalchemy.exc import OperationalError
from sqlmodel import select

from metatracer.api.app import create_app
from metatracer.api.auth import login_lockout
from metatracer.core.config import Settings
from metatracer.db.models import Run, RunStatus, User


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/task33.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


async def test_stream_of_terminal_run_without_history_closes(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session:
            run = Run(
                target_input="[]",
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id
        assert app.state.bus.has_history(run_id) is False
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/runs/{run_id}/stream")
        assert response.status_code == 200
        assert response.text.startswith("data: ")
        assert '"stage":"completed"' in response.text.replace(" ", "")


async def test_ready_is_503_when_the_database_is_down(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        class _Down:
            def connect(self):
                raise OperationalError("SELECT 1", {}, Exception("down"))

        app.state.engine = _Down()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            ready = await client.get("/api/ready")
            health = await client.get("/api/health")
        assert ready.status_code == 503
        assert health.status_code == 200


async def test_ten_failed_logins_block_a_later_correct_password(tmp_path: Path) -> None:
    login_lockout.reset()
    app = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                page = await client.get("/api/auth/me")
                # Signed out answers 401, but the pre-session CSRF token is issued.
                assert page.status_code in (200, 401)
                csrf = client.cookies.get("csrf_token", "")
                for _ in range(10):
                    failed = await client.post(
                        "/api/auth/login",
                        json={"username": "operator", "password": "wrong-password"},
                        headers={"X-CSRF-Token": csrf},
                    )
                    assert failed.status_code == 401
                blocked = await client.post(
                    "/api/auth/login",
                    json={"username": "operator", "password": "test-password-123"},
                    headers={"X-CSRF-Token": csrf},
                )
                assert blocked.status_code == 429
                assert blocked.headers.get("retry-after")
    finally:
        login_lockout.reset()


async def test_concurrent_setup_creates_one_operator(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password=""),
        reports_dir=tmp_path / "reports",
    )
    async with app.router.lifespan_context(app):
        token = app.state.setup_token
        assert isinstance(token, str)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/api/auth/me")
            csrf = client.cookies.get("csrf_token", "")

            async def post(name: str) -> httpx.Response:
                return await client.post(
                    "/api/auth/setup",
                    json={
                        "setup_token": token,
                        "username": name,
                        "password": "first-pass-1",
                    },
                    headers={"X-CSRF-Token": csrf},
                )

            first, second = await asyncio.gather(post("one"), post("two"))
        codes = sorted([first.status_code, second.status_code])
        assert codes == [200, 409]
        async with app.state.session_factory() as session:
            users = (await session.exec(select(User))).all()
        assert len(users) == 1
