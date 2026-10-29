"""GET /api/stats and the /dashboard page (TASK-11, v2.0).

Reuses the in-process ASGI setup of the other API tests. The stats endpoint is
read-only and agent-agnostic: works with zero runs and never leaks
raw_response / bytes / secrets.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from tests.unit.test_dashboard_repository import _seed


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-stats-test.db",
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


async def test_stats_empty_database(client) -> None:
    response = await client.get("/api/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["runs"]["total"] == 0
    assert payload["assets"]["total"] == 0
    assert payload["findings"]["total"] == 0
    assert payload["findings"]["unclassified"] == 0
    assert payload["top_domains"] == []
    assert payload["top_evidence"] == []
    assert payload["agent_usage"]["calls"] == 0
    assert payload["agent_usage"]["total_tokens"] == 0


async def test_stats_with_seeded_data(app, client) -> None:
    # Seed through the app's own session factory (same db the API reads).
    await _seed(app.state.session_factory)

    response = await client.get("/api/stats")
    assert response.status_code == 200
    payload = response.json()

    assert payload["runs"]["total"] == 2
    assert payload["runs"]["completed"] == 1
    assert payload["runs"]["failed"] == 1
    assert payload["assets"]["total"] == 2
    assert payload["assets"]["with_issues"] == 1
    assert payload["findings"]["total"] == 3
    assert payload["findings"]["severity_breakdown"]["high"] == 1
    assert payload["findings"]["severity_breakdown"]["unclassified"] == 1
    assert payload["findings"]["by_type"]["email"] == 2

    domains = {entry["domain"] for entry in payload["top_domains"]}
    assert "target.com" in domains  # normalized from the seeded scope/URL

    evidence = payload["top_evidence"]
    assert len(evidence) == 2
    # Aggregation is by type + normalized snippet, not by dedup_signature
    # (which embeds the asset id and therefore can never repeat).
    by_snippet = {entry["evidence_snippet"]: entry for entry in evidence}
    assert by_snippet["a@b.com"]["occurrences"] == 2
    assert by_snippet["a@b.com"]["finding_type"] == "email"

    # Agent usage sums, and raw_response never travels to the API.
    assert payload["agent_usage"]["calls"] == 1
    assert payload["agent_usage"]["total_tokens"] == 30


async def test_stats_never_leaks_raw_response(app, client) -> None:
    await _seed(app.state.session_factory)
    response = await client.get("/api/stats")
    blob = response.text
    assert "raw_response" not in blob
    assert '{"severity": "high"}' not in blob


async def test_stats_is_read_only(app, client) -> None:
    """The endpoint never writes: row counts are unchanged after a GET."""
    from sqlmodel import select

    from metatracer.db.models import Asset, Finding, Run

    await _seed(app.state.session_factory)

    async with app.state.session_factory() as session:
        run_rows = (await session.exec(select(Run))).all()
        asset_rows = (await session.exec(select(Asset))).all()
        finding_rows = (await session.exec(select(Finding))).all()

    assert (await client.get("/api/stats")).status_code == 200

    async with app.state.session_factory() as session:
        run_rows_after = (await session.exec(select(Run))).all()
        asset_rows_after = (await session.exec(select(Asset))).all()
        finding_rows_after = (await session.exec(select(Finding))).all()

    assert len(run_rows) == len(run_rows_after)
    assert len(asset_rows) == len(asset_rows_after)
    assert len(finding_rows) == len(finding_rows_after)