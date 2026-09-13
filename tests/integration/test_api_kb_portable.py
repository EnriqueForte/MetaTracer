"""POST /api/knowledge/export + /import (TASK-17, v2.2): portable KB over the API."""

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
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-kb-portable-test.db",
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
    """One run with one GPS finding to export."""
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


async def test_export_returns_downloadable_json(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    await _seed(app)
    response = await client.post("/api/knowledge/export")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")
    payload = response.json()
    assert payload["format_version"] == 1
    entries = payload["entries"]
    assert len(entries) == 1
    entry = entries[0]
    # Only portable-KB keys; never run/asset provenance or raw metadata.
    assert set(entry) <= {"finding_id", "finding_type", "evidence_snippet",
                          "severity", "title", "created_at"}
    assert entry["finding_type"] == "gps"
    assert entry["severity"] == "high"
    assert "41.6521" in entry["evidence_snippet"]


async def test_import_inserts_and_is_idempotent_via_api(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    exported = await client.post("/api/knowledge/export")
    assert exported.status_code == 200
    exported_bytes = exported.content

    first = await client.post("/api/knowledge/import", content=exported_bytes)
    assert first.status_code == 200
    assert first.json()["imported"] == 0  # nothing seeded -> 0 entries in export

    # Seed one finding, export again, import twice -> idempotent.
    await _seed(app)
    exported2 = await client.post("/api/knowledge/export")
    assert exported2.status_code == 200
    exported2_bytes = exported2.content

    r1 = await client.post("/api/knowledge/import", content=exported2_bytes)
    assert r1.status_code == 200
    assert r1.json()["imported"] == 1
    r2 = await client.post("/api/knowledge/import", content=exported2_bytes)
    assert r2.status_code == 200
    assert r2.json()["imported"] == 0  # already there -> skipped

    async with app.state.session_factory() as session:
        from sqlalchemy import select

        from metatracer.db.models import Finding as F

        rows = list((await session.exec(select(F))).scalars())
    # 1 original (seed) + 1 imported = 2; nothing duplicated by re-import.
    assert len(rows) == 2


async def test_import_without_body_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/knowledge/import")
    assert response.status_code == 422