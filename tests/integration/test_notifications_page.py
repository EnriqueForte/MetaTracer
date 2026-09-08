"""The notifications bell lives in the shared layout (TASK-12).

Every page extends base.html, so the bell must be present on the scan wizard
without any data — the shell renders unconditionally and Alpine covers the
loading/empty states.
"""

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
        database_url=f"sqlite+aiosqlite:///{tmp_path}/bell-page.db",
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


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


async def test_bell_present_on_every_page(client) -> None:
    for path in ["/", "/dashboard", "/runs", "/scopes"]:
        response = await client.get(path)
        assert response.status_code == 200
        html = response.text
        assert "notifications_bell" in html
        assert "api/notifications" in html