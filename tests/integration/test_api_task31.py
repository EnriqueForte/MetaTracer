"""TASK-31: chunked body cap and operator-only admin reads."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.api.auth import hash_password
from metatracer.core.config import Settings
from metatracer.core.ratelimit import read_body_capped
from metatracer.db.models import User, UserRole


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/task31.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": False,
        "api_rate_limit_per_minute": 0,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


class _Chunked:
    """Yields fixed chunks and counts how many the reader actually pulled."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.pulled = 0

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._chunks:
            self.pulled += 1
            yield chunk


class _Request:
    def __init__(self, chunks: list[bytes]) -> None:
        self.headers: dict[str, str] = {}
        self._body = _Chunked(chunks)

    async def stream(self):
        async for chunk in self._body:
            yield chunk

    async def body(self) -> bytes:
        return b"".join([chunk async for chunk in self.stream()])


async def test_read_body_capped_stops_before_the_rest_of_the_stream() -> None:
    chunks = [b"x" * 1024 for _ in range(6)]
    request = _Request(chunks)
    with pytest.raises(Exception) as excinfo:
        await read_body_capped(request, 3 * 1024)  # type: ignore[arg-type]
    assert getattr(excinfo.value, "status_code", None) == 413
    # Four chunks cross 3 KiB; the last two must stay unread.
    assert request._body.pulled == 4
    assert request._body.pulled < len(chunks)


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        yield http


def _six_mib() -> tuple[_Chunked, int]:
    chunk = b"x" * (256 * 1024)
    count = (6 * 1024 * 1024) // len(chunk)
    return _Chunked([chunk] * count), count


async def test_chunked_import_is_rejected_before_the_whole_body(
    client: httpx.AsyncClient,
) -> None:
    for path in ("/api/scopes/import", "/api/knowledge/import"):
        body, total = _six_mib()
        response = await client.post(
            path,
            content=body,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 413, path
        assert body.pulled < total


async def test_non_numeric_content_length_is_400(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/scopes/import",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "nope"},
    )
    assert response.status_code == 400


@pytest.fixture()
async def auth_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    async with application.router.lifespan_context(application):
        yield application


async def _login(client: httpx.AsyncClient, username: str, password: str) -> str:
    page = await client.get("/login")
    assert page.status_code == 200
    csrf = client.cookies.get("csrf_token", "")
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


async def test_viewer_cannot_read_admin_surfaces(auth_app: FastAPI) -> None:
    async with auth_app.state.session_factory() as session:
        session.add(
            User(
                username="viewer",
                password_hash=hash_password("viewer-password-123"),
                role=UserRole.viewer,
            )
        )
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
    ) as viewer:
        csrf = await _login(viewer, "viewer", "viewer-password-123")
        assert (await viewer.get("/api/users")).status_code == 403
        assert (await viewer.get("/api/invitations")).status_code == 403
        assert (await viewer.get("/api/webhooks")).status_code == 403
        exported = await viewer.post(
            "/api/knowledge/export", headers={"X-CSRF-Token": csrf}
        )
        assert exported.status_code == 403
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
    ) as operator:
        csrf = await _login(operator, "operator", "test-password-123")
        assert (await operator.get("/api/users")).status_code == 200
        assert (await operator.get("/api/invitations")).status_code == 200
        assert (await operator.get("/api/webhooks")).status_code == 200
        exported = await operator.post(
            "/api/knowledge/export", headers={"X-CSRF-Token": csrf}
        )
        assert exported.status_code == 200


async def test_auth_off_admin_reads_stay_open(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/users")).status_code == 200
    assert (await client.get("/api/invitations")).status_code == 200
    assert (await client.get("/api/webhooks")).status_code == 200
    exported = await client.post("/api/knowledge/export")
    assert exported.status_code == 200
