"""Security headers are attached by the HTTP middleware, including errors."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/headers.db",
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


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


def _assert_baseline(response: httpx.Response) -> None:
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "geolocation=()" in response.headers["permissions-policy"]
    assert "strict-transport-security" not in response.headers


async def test_pages_do_not_load_third_party_scripts(client: httpx.AsyncClient) -> None:
    home = await client.get("/")
    login = await client.get("/login")
    for response in (home, login):
        assert response.status_code == 200
        assert "cdn.tailwindcss.com" not in response.text
        assert "cdn.jsdelivr.net" not in response.text
        assert "/static/tailwind.css" in response.text
        assert "/static/alpine-csp-3.17.4.min.js" in response.text


async def test_health_and_html_carry_security_headers(client: httpx.AsyncClient) -> None:
    health = await client.get("/api/health")
    page = await client.get("/")
    assert health.status_code == 200
    assert page.status_code == 200
    _assert_baseline(health)
    _assert_baseline(page)


async def test_error_json_carries_security_headers(client: httpx.AsyncClient) -> None:
    missing = await client.get("/api/runs/00000000-0000-4000-8000-000000000000")
    assert missing.status_code == 404
    _assert_baseline(missing)
