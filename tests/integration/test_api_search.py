"""GET /api/search (TASK-46): lexical hits, filters, cursor, viewer read."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import (
    Asset,
    Finding,
    FindingType,
    RawMetadataItem,
    Run,
    Scope,
    Severity,
)
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-search-test.db",
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


async def _seed(app: FastAPI) -> tuple[str, str]:
    async with app.state.session_factory() as session:
        run = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
        )
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run.id,
                source_url="https://t.com/photo.jpg",
                final_url="https://t.com/photo.jpg",
                content_type="image/jpeg",
                file_hash_sha256="h-search",
                file_size_bytes=10,
                extraction_status="ok",
            )
        )
        await FindingRepository(session).create(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="ops@acme-corp.internal",
                dedup_signature="sig-search-email",
                detector_method="rule",
                confidence="high",
                severity=Severity.medium,
            )
        )
        await RawMetadataRepository(session).create(
            RawMetadataItem(
                asset_id=asset.id,
                namespace="pdfinfo",
                key="Author",
                value="ops@acme-corp.internal",
            )
        )
        other = await RunRepository(session).create(
            Run(target_input='["other.test"]', allowed_scope='["other.test"]', scope_confirmed=True)
        )
        other_asset = await AssetRepository(session).create(
            Asset(
                run_id=other.id,
                source_url="https://other.test/a.pdf",
                final_url="https://other.test/a.pdf",
                content_type="application/pdf",
                file_hash_sha256="h-other",
                file_size_bytes=8,
                extraction_status="ok",
            )
        )
        await FindingRepository(session).create(
            Finding(
                run_id=other.id,
                asset_id=other_asset.id,
                finding_type=FindingType.gps,
                field_source="EXIF:GPSInfo",
                evidence_snippet="Latitude: 1.0, Longitude: 2.0",
                dedup_signature="sig-search-gps",
                detector_method="rule",
                confidence="high",
                severity=Severity.high,
            )
        )
        return run.id, other.id


async def test_search_finds_email_across_runs(app: FastAPI, client: httpx.AsyncClient) -> None:
    await _seed(app)
    response = await client.get("/api/search", params={"q": "acme-corp", "kind": "all"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "acme-corp"
    assert body["mode"] == "lexical"
    assert body["findings"]["total"] == 1
    assert body["findings"]["items"][0]["evidence_snippet"] == "ops@acme-corp.internal"
    assert body["metadata"]["total"] == 1
    assert body["metadata"]["items"][0]["key"] == "Author"


async def test_search_filters_by_type_and_run(app: FastAPI, client: httpx.AsyncClient) -> None:
    run_id, other_id = await _seed(app)
    typed = await client.get(
        "/api/search", params={"q": "Latitude", "kind": "findings", "finding_type": "gps"}
    )
    assert typed.status_code == 200
    assert typed.json()["findings"]["total"] == 1
    scoped = await client.get(
        "/api/search", params={"q": "acme", "kind": "findings", "run_id": other_id}
    )
    assert scoped.json()["findings"]["total"] == 0
    same = await client.get(
        "/api/search", params={"q": "acme", "kind": "findings", "run_id": run_id}
    )
    assert same.json()["findings"]["total"] == 1


async def test_search_wildcard_is_literal(app: FastAPI, client: httpx.AsyncClient) -> None:
    await _seed(app)
    response = await client.get("/api/search", params={"q": "acme%", "kind": "findings"})
    assert response.status_code == 200
    assert response.json()["findings"]["total"] == 0


async def test_search_rejects_bad_cursor_and_namespace(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    await _seed(app)
    bad_ns = await client.get("/api/search", params={"q": "a", "namespace": "nope"})
    assert bad_ns.status_code == 422
    bad_cur = await client.get(
        "/api/search", params={"q": "acme", "kind": "findings", "findings_cursor": "not-a-cursor"}
    )
    assert bad_cur.status_code == 422


async def test_search_scope_id_filters_domains(app: FastAPI, client: httpx.AsyncClient) -> None:
    await _seed(app)
    async with app.state.session_factory() as session:
        from metatracer.db.repositories import ScopeRepository

        scope = await ScopeRepository(session).create(
            Scope(name="acme-eng", domains='["t.com"]')
        )
    hit = await client.get(
        "/api/search", params={"q": "acme", "kind": "findings", "scope_id": scope.id}
    )
    assert hit.status_code == 200
    assert hit.json()["findings"]["total"] == 1
    missing = await client.get(
        "/api/search", params={"q": "acme", "scope_id": "00000000-0000-4000-8000-000000000000"}
    )
    assert missing.status_code == 404


async def test_search_similar_falls_back_to_lexical(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    await _seed(app)
    response = await client.get(
        "/api/search", params={"q": "acme-corp", "kind": "findings", "mode": "similar"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["findings"]["total"] >= 1
    assert body["mode"] in {"lexical", "similar"}


async def test_search_v1_alias(app: FastAPI, client: httpx.AsyncClient) -> None:
    await _seed(app)
    response = await client.get("/api/v1/search", params={"q": "acme-corp", "kind": "findings"})
    assert response.status_code == 200
    assert response.json()["findings"]["total"] == 1
