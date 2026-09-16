"""The /runs history page shell and its data states (TASK-20, 20.4).

The page fetches /api/runs via Alpine. This suite covers the loading/empty/
error rendering paths on the rendered shell: empty state when there are no
runs, and a Retry affordance when the API answers non-200.
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
        database_url=f"sqlite+aiosqlite:///{tmp_path}/history-page-test.db",
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


async def test_history_page_renders(client) -> None:
    response = await client.get("/runs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Local history" in response.text
    # Data loads client-side from the runs API; never rendered inline.
    assert "/api/runs" in response.text


async def test_history_page_has_empty_state_shell(client) -> None:
    """The page ships the empty-state markup (Alpine reveals it when no runs)."""
    response = await client.get("/runs")
    html = response.text
    assert "No runs yet" in html
    assert "Start a scan to build a local history" in html


async def test_history_page_has_loading_and_error_shells(client) -> None:
    """Loading and error (with Retry) affordances are present in the shell."""
    response = await client.get("/runs")
    html = response.text
    assert "Loading history" in html
    # Error block + retry button (revealed by Alpine on a failed fetch).
    assert "Could not load the local history" in html or "role=\"alert\"" in html
    assert "Retry" in html


async def test_history_page_has_pagination_controls(client) -> None:
    """TASK-21 (v2.4): the prev/next affordances and cursor wiring are present."""
    response = await client.get("/runs")
    html = response.text
    assert "Older" in html
    assert "Newer" in html
    assert "next_cursor" in html
    assert "has_more" in html
    # The untruncated counter reads the global total from the API.
    assert "totalRuns" in html
