"""Local folder ingest (TASK-51): zero HTTP, same sniff/extractors."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import ExtractionStatus, Run, SkipReason
from metatracer.db.repositories import (
    AssetRepository,
    DiscoveryEdgeRepository,
    RawMetadataRepository,
    RunRepository,
)
from metatracer.extractors.ingest import IngestionPipeline
from metatracer.extractors.local import LOCAL_SOURCE, file_uri, list_local_entries
from metatracer.services.orchestrator import ScanRequest
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes

JPEG_BYTES = make_jpeg_bytes()
PDF_BYTES = make_pdf_bytes()


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "max_assets_per_run": 50,
        "max_file_bytes": 50 * 1024 * 1024,
        "rate_limit_rps": 1000.0,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/local-ingest.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _make_local_run(
    factory: async_sessionmaker[AsyncSession],
    paths: list[str],
    *,
    max_assets: int = 50,
) -> str:
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input=json.dumps([file_uri(Path(item)) for item in paths]),
                allowed_scope=json.dumps(["target.com"]),
                scope_confirmed=True,
                ingestion_stats=json.dumps(
                    {
                        "source": LOCAL_SOURCE,
                        "local_paths": paths,
                        "budget": {
                            "depth": 1,
                            "max_pages": 1,
                            "max_assets": max_assets,
                            "max_total_bytes": 200 * 1024 * 1024,
                            "max_seconds": 900,
                            "max_concurrency": 3,
                            "honor_robots": True,
                        },
                        "limits_hit": [],
                    }
                ),
            )
        )
        return run.id


@pytest.fixture()
def no_http(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    blocked = AsyncMock(side_effect=AssertionError("local ingest must not call HTTP"))
    monkeypatch.setattr("metatracer.extractors.ingest.safe_httpx_request", blocked)
    monkeypatch.setattr("metatracer.core.safety.http.safe_httpx_request", blocked)
    return blocked


@pytest.mark.asyncio
async def test_local_directory_extracts_without_http(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    no_http: AsyncMock,
) -> None:
    dump = tmp_path / "dump"
    dump.mkdir()
    (dump / "photo.jpg").write_bytes(JPEG_BYTES)
    (dump / "doc.pdf").write_bytes(PDF_BYTES)
    (dump / "readme.txt").write_text("ignored")
    (dump / "blob.zip").write_bytes(b"PK\x03\x04not-office")
    (dump / "page.html").write_text(
        '<html><head><title>Local</title></head><body><img src="https://evil.example/x.jpg"></body></html>'
    )
    run_id = await _make_local_run(session_factory, [str(dump)])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)
    assert no_http.await_count == 0
    assert summary.assets_ok >= 3
    async with session_factory() as session:
        assets = await AssetRepository(session).list_by_run(run_id)
        urls = {asset.final_url for asset in assets}
        assert all(url.startswith("file:") for url in urls)
        assert not any(asset.final_url.endswith(".zip") for asset in assets)
        assert not any(asset.final_url.endswith(".txt") for asset in assets)
        items = []
        for asset in assets:
            items.extend(await RawMetadataRepository(session).list_by_asset(asset.id))
        keys = {(item.namespace, item.key) for item in items}
        assert ("html", "title") in keys or any(item.value == "Local" for item in items)
        edges = await DiscoveryEdgeRepository(session).list_by_run(run_id)
        assert edges
        assert all(str(edge.kind) == "local" for edge in edges)
        root = file_uri(dump)
        assert all(edge.from_url == root for edge in edges)


@pytest.mark.asyncio
async def test_explicit_missing_path_fails_asset_not_run(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    no_http: AsyncMock,
) -> None:
    missing = tmp_path / "no-such.pdf"
    present = tmp_path / "ok.pdf"
    present.write_bytes(PDF_BYTES)
    run_id = await _make_local_run(session_factory, [str(missing), str(present)])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)
    assert summary.assets_failed >= 1
    assert summary.assets_ok >= 1
    async with session_factory() as session:
        assets = await AssetRepository(session).list_by_run(run_id)
        statuses = {asset.extraction_status for asset in assets}
        assert ExtractionStatus.failed in statuses
        assert ExtractionStatus.ok in statuses


@pytest.mark.asyncio
async def test_explicit_zip_is_unsupported(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    no_http: AsyncMock,
) -> None:
    archive = tmp_path / "dump.zip"
    archive.write_bytes(b"PK\x03\x04generic")
    run_id = await _make_local_run(session_factory, [str(archive)])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)
    assert summary.assets_ok == 0
    async with session_factory() as session:
        assets = await AssetRepository(session).list_by_run(run_id)
        assert assets[0].skip_reason is SkipReason.unsupported_type


def test_scan_request_local_paths_exclusive() -> None:
    req = ScanRequest(
        local_paths=["C:/export"],
        scope_domains=["target.com"],
        scope_confirmed=True,
    )
    assert req.targets == []
    assert req.local_paths == ["C:/export"]
    with pytest.raises(ValidationError):
        ScanRequest(
            targets=["https://target.com/a.pdf"],
            local_paths=["C:/export"],
            scope_domains=["target.com"],
            scope_confirmed=True,
        )


def test_list_local_entries_skips_directory_junk(tmp_path: Path) -> None:
    dump = tmp_path / "mix"
    dump.mkdir()
    (dump / "keep.pdf").write_bytes(PDF_BYTES)
    (dump / "skip.bin").write_bytes(b"xx")
    entries = list_local_entries([str(dump)])
    assert len(entries) == 1
    assert entries[0].path.name == "keep.pdf"
    assert entries[0].status is None
