"""API-edge performance guards (v2.3): rate limiting and request-body caps.

Exercises the real middleware wiring through the ASGI transport: the 429 must
carry Retry-After, the 413 must fire before any handler work, the exempt paths
must NOT consume the budget, and a disabled limiter must be a transparent
no-op.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/api-perf-test.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        # A tiny budget so the tests stay fast and deterministic.
        "api_rate_limit_per_minute": 3,
        # A small body cap so the 413 path is reachable in tests.
        "max_request_body_bytes": 2048,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def test_rate_limit_429_with_retry_after(app: FastAPI, client: httpx.AsyncClient) -> None:
    """The 4th request within a minute is refused with a Retry-After header."""
    for _ in range(3):
        response = await client.get("/api/stats")
        assert response.status_code == 200  # 3 requests fill the budget

    response = await client.get("/api/stats")
    assert response.status_code == 429
    assert response.headers.get("retry-after") == "60"


async def test_rate_limit_disabled_when_zero(
    tmp_path: Path, client: httpx.AsyncClient
) -> None:
    """A limiter configured to 0 is a transparent no-op (reverse proxy case)."""
    app0 = create_app(_settings(tmp_path, api_rate_limit_per_minute=0))
    async with app0.router.lifespan_context(app0):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app0), base_url="http://testserver"
        ) as c:
            for _ in range(10):
                response = await c.get("/api/stats")
                assert response.status_code == 200


async def test_health_and_static_exempt_from_rate_limit(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """Health liveness and static assets never consume the client's budget."""
    for _ in range(6):
        response = await client.get("/api/health")
        assert response.status_code == 200
    response = await client.get("/static/metatracer.css")
    assert response.status_code in (200, 404)  # file exists in dev; 404 is fine
    response = await client.get("/api/stats")
    assert response.status_code == 200  # budget untouched by the 7 exempt calls


async def test_body_413_on_scopes_import(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    """An oversized import body is rejected with 413 before any parsing."""
    big = json.dumps(
        {"format_version": 1, "scopes": [{"name": "x" * 100, "domains": ["a.com"] * 500}]}
    )
    response = await client.post(
        "/api/scopes/import",
        content=big.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


async def test_body_413_on_knowledge_import(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """The KB import shares the same edge cap."""
    big = json.dumps({"format_version": 1, "entries": [{"k": "v" * 4000} for _ in range(10)]})
    response = await client.post(
        "/api/knowledge/import",
        content=big.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


async def test_small_import_bodies_still_work(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """Legitimate small imports are unaffected by the new guards."""
    scopes_body = json.dumps(
        {"format_version": 1, "scopes": [{"name": "tiny", "domains": ["t.com"]}]}
    )
    response = await client.post(
        "/api/scopes/import",
        content=scopes_body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (201, 400, 422)