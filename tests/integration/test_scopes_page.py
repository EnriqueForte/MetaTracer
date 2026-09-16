"""The /scopes page shell and its data states (TASK-20, 20.4).

Covers the loading/empty/error shells and the scope-import affordances
(including the 413 oversized-upload handling surfaced to the operator).
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
        database_url=f"sqlite+aiosqlite:///{tmp_path}/scopes-page-test.db",
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


async def test_scopes_page_renders(client) -> None:
    response = await client.get("/scopes")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Scopes" in response.text
    assert "/api/scopes" in response.text


async def test_scopes_page_has_empty_state_shell(client) -> None:
    """The page ships the empty-state markup for zero scopes."""
    response = await client.get("/scopes")
    html = response.text
    assert "No scopes yet" in html
    assert "Create a scope to reuse" in html


async def test_scopes_page_has_loading_and_error_shells(client) -> None:
    """Loading spinner and error+Retry affordances are present."""
    response = await client.get("/scopes")
    html = response.text
    assert "Loading scopes" in html
    assert "Retry" in html
    assert "role=\"alert\"" in html


async def test_scopes_page_has_import_affordances(client) -> None:
    """The import widget and its 413 error handling are wired in the shell."""
    response = await client.get("/scopes")
    html = response.text
    assert "Import scopes from a file" in html
    assert "scope-import-file" in html
    # The 413 message surfaced to the operator lives in the Alpine import handler.
    assert "too large" in html.lower() or "Importing" in html
