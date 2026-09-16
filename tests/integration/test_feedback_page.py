"""The feedback controls live on the run detail page (TASK-13).

The run page renders the operator-feedback section unconditionally; the actual
drawer appears via Alpine when a finding is selected. This smoke test checks
the shell is present and the API route is wired in the app — no data needed.
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
        database_url=f"sqlite+aiosqlite:///{tmp_path}/feedback-page.db",
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


async def test_run_page_contains_feedback_shell(client) -> None:
    # A non-existent run still renders the page shell (with the not-found
    # state); the feedback markup lives in the same template.
    response = await client.get("/runs/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 200
    html = response.text
    assert "Feedback" in html
    assert "api/feedback" in html


async def test_feedback_router_is_mounted(client) -> None:
    # PUT against an empty finding id resolves the route (404, not 404 of route).
    response = await client.put(
        "/api/feedback/00000000-0000-4000-8000-000000000000",
        json={"vote": "down", "severity_after": "low"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "finding not found"


async def test_run_page_distinguishes_zero_findings_from_error(client) -> None:
    """TASK-20 (20.4): 'no findings' and 'findings unavailable' are distinct.

    A valid zero-findings result renders a dedicated emerald state; a failed
    findings fetch renders a red 'Findings unavailable' block. The two must
    never be conflated.
    """
    response = await client.get("/runs/00000000-0000-4000-8000-000000000000")
    html = response.text
    # The zero-findings state (revealed when findings is an empty list).
    assert "No findings" in html
    assert "No sensitive metadata was identified" in html
    # The findings-failure state (revealed when the /findings fetch fails).
    assert "Findings unavailable" in html
    assert "findingsError" in html
