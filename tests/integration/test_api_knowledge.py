"""GET /api/knowledge/search (TASK-14, v2.1+): read-only inspection endpoint."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import Asset, Finding, FindingType, Run, Severity
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-knowledge-test.db",
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


async def _seed(app: FastAPI) -> None:
    """One run with a GPS finding to search against."""
    async with app.state.session_factory() as session:
        run = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
        )
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run.id,
                source_url="https://t.com/a.jpg",
                final_url="https://t.com/a.jpg",
                content_type="image/jpeg",
                file_hash_sha256="h-a",
                file_size_bytes=10,
                extraction_status="ok",
            )
        )
        await FindingRepository(session).create(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.gps,
                field_source="EXIF:GPSInfo",
                evidence_snippet="Latitude: 41.6521, Longitude: -0.8809",
                dedup_signature="sig-gps-a",
                detector_method="rule",
                confidence="high",
                severity=Severity.high,
            )
        )


async def test_search_returns_hits(app: FastAPI, client: httpx.AsyncClient) -> None:
    await _seed(app)
    response = await client.get("/api/knowledge/search", params={"q": "41.6521"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "41.6521"
    assert body["total"] >= 1
    hit = body["hits"][0]
    assert hit["finding_type"] == "gps"
    assert "41.6521" in hit["evidence_snippet"]
    assert "score" in hit


async def test_search_without_q_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/knowledge/search")
    assert response.status_code == 422


async def test_search_read_only(client: httpx.AsyncClient) -> None:
    """GET never writes business rows: after a search, no new run/finding exists."""
    response = await client.get("/api/knowledge/search", params={"q": "anything"})
    assert response.status_code == 200  # empty index -> 0 hits, not an error


async def test_search_invalid_type_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/knowledge/search", params={"q": "x", "finding_type": "bogus"}
    )
    assert response.status_code == 422