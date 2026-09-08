"""DetectionPipeline DB tests (TASK-02 subtask 2.6 and DoD).

Persistence-level guarantees: findings land in the database with severity
NULL, ``Run.total_findings`` is recomputed, re-running detection inserts
nothing (unique-constraint conflicts are ignored), failed/skipped assets are
not scanned and a clean asset yields zero findings while staying ``ok``.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, ExtractionStatus, RawMetadataItem, Run
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)
from metatracer.detectors import DetectionPipeline

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture()
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/detect-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session_factory(engine: AsyncEngine) -> SessionFactory:
    return create_session_factory(engine)


async def _run(factory: SessionFactory) -> str:
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input=json.dumps(["http://target.com"]),
                allowed_scope=json.dumps(["target.com"]),
                scope_confirmed=True,
            )
        )
        return run.id


async def _asset(
    factory: SessionFactory,
    run_id: str,
    status: ExtractionStatus = ExtractionStatus.ok,
    file_hash: str = "ab" * 32,
) -> str:
    async with factory() as session:
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run_id,
                source_url="http://target.com/a.pdf",
                final_url="http://target.com/a.pdf",
                content_type="application/pdf",
                file_hash_sha256=file_hash,
                file_size_bytes=128,
                extraction_status=status,
            )
        )
        return asset.id


async def _items(factory: SessionFactory, asset_id: str, fields: list[tuple[str, str]]) -> None:
    async with factory() as session:
        await RawMetadataRepository(session).create_many(
            [
                RawMetadataItem(asset_id=asset_id, namespace="pdfinfo", key=key, value=value)
                for key, value in fields
            ]
        )


async def test_pipeline_persists_findings_with_null_severity(
    session_factory: SessionFactory,
) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    await _items(
        session_factory,
        asset_id,
        [
            ("Author", "jane.doe@target.corp"),
            ("Creator", "jane.doe@target.corp"),  # same evidence: dedup merges
            ("Producer", "Microsoft Word"),  # no version: no finding
            ("Title", "Quarterly report"),
        ],
    )

    summary = await DetectionPipeline(session_factory).execute(run_id)

    assert summary.assets_processed == 1
    assert summary.findings_new == 1
    assert summary.findings_total == 1
    async with session_factory() as session:
        findings = await FindingRepository(session).list_by_run(run_id)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.finding_type == "email"
        assert finding.evidence_snippet == "jane.doe@target.corp"
        assert finding.field_source == "pdfinfo:Author | pdfinfo:Creator"
        assert finding.severity is None
        assert finding.detector_method == "rule"
        run = await RunRepository(session).get(run_id)
        assert run is not None
        assert run.total_findings == 1


async def test_pipeline_is_idempotent_on_rerun(session_factory: SessionFactory) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    await _items(session_factory, asset_id, [("Author", "jane.doe@target.corp")])

    first = await DetectionPipeline(session_factory).execute(run_id)
    second = await DetectionPipeline(session_factory).execute(run_id)

    assert first.findings_new == 1
    assert second.findings_new == 0  # unique-constraint conflicts ignored
    assert second.findings_total == 1
    async with session_factory() as session:
        assert len(await FindingRepository(session).list_by_run(run_id)) == 1


async def test_pipeline_skips_assets_without_ok_extraction(session_factory: SessionFactory) -> None:
    run_id = await _run(session_factory)
    failed_id = await _asset(session_factory, run_id, status=ExtractionStatus.failed)
    await _items(session_factory, failed_id, [("Author", "jane.doe@target.corp")])

    summary = await DetectionPipeline(session_factory).execute(run_id)

    assert summary.assets_processed == 0
    assert summary.findings_new == 0
    async with session_factory() as session:
        assert await FindingRepository(session).list_by_run(run_id) == []


async def test_pipeline_clean_asset_stays_ok_with_zero_findings(
    session_factory: SessionFactory,
) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    await _items(
        session_factory,
        asset_id,
        [("Author", "Jane Doe"), ("Producer", "Microsoft Word"), ("Title", "Quarterly report")],
    )

    summary = await DetectionPipeline(session_factory).execute(run_id)

    assert summary.assets_processed == 1
    assert summary.findings_new == 0
    async with session_factory() as session:
        asset = await AssetRepository(session).get(asset_id)
        assert asset is not None
        assert asset.extraction_status is ExtractionStatus.ok
        run = await RunRepository(session).get(run_id)
        assert run is not None
        assert run.total_findings == 0


async def test_pipeline_unknown_run_raises(session_factory: SessionFactory) -> None:
    from metatracer.core.exceptions import MetaTracerError

    with pytest.raises(MetaTracerError):
        await DetectionPipeline(session_factory).execute("no-such-run")
