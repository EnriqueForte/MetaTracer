"""Shared values group assets. They do not assert a common identity."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Confidence,
    CorrelationKind,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    RawMetadataItem,
    Run,
    RunStatus,
    Severity,
)
from metatracer.detectors.consolidator import dedup_signature
from metatracer.detectors.correlate import collect_observations
from metatracer.detectors.pipeline import DetectionPipeline
from metatracer.services.correlation import groups_touching_run


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/correlation.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _asset(session, run_id: str, url: str) -> Asset:
    asset = Asset(
        run_id=run_id,
        source_url=url,
        final_url=url,
        content_type="image/jpeg",
        file_hash_sha256=(url[-8:] + "ab" * 28)[:64],
        file_size_bytes=10,
        extraction_status=ExtractionStatus.ok,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


def test_placeholders_and_tool_names_are_not_correlated() -> None:
    items = [
        RawMetadataItem(asset_id="a", namespace="exif", key="BodySerialNumber", value="0"),
        RawMetadataItem(asset_id="a", namespace="exif", key="CreatorTool", value="Adobe Photoshop"),
        RawMetadataItem(asset_id="a", namespace="pdfinfo", key="Author", value="Ada Lovelace"),
    ]
    observations = collect_observations(items, [])
    assert [item.kind for item in observations] == [CorrelationKind.author_string]
    assert observations[0].value_norm == "ada lovelace"


async def test_the_same_serial_on_two_photos_is_one_shared_value(session_factory) -> None:
    async with session_factory() as session:
        run = Run(
            target_input='["https://acme.com"]',
            allowed_scope='["acme.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        first = await _asset(session, run.id, "https://acme.com/one.jpg")
        second = await _asset(session, run.id, "https://acme.com/two.jpg")
        for asset in (first, second):
            session.add(
                RawMetadataItem(
                    asset_id=asset.id,
                    namespace="exif",
                    key="BodySerialNumber",
                    value="SN-88421",
                )
            )
        await session.commit()
        run_id = run.id

    summary = await DetectionPipeline(session_factory).execute(run_id)
    assert summary.findings_new == 0

    async with session_factory() as session:
        groups = await groups_touching_run(session, run_id)
    assert len(groups) == 1
    group = groups[0]
    assert group.kind is CorrelationKind.device_serial
    assert group.value_norm == "sn-88421"
    assert group.occurrences == 2
    assert group.notice == "Shared value across 2 assets — not proof of common identity."
    assert {member.asset_url for member in group.members} == {
        "https://acme.com/one.jpg",
        "https://acme.com/two.jpg",
    }

    # A second detection pass must not double the asset count.
    await DetectionPipeline(session_factory).execute(run_id)
    async with session_factory() as session:
        again = await groups_touching_run(session, run_id)
    assert again[0].occurrences == 2


async def test_an_email_finding_correlates_without_becoming_an_author_finding(
    session_factory,
) -> None:
    async with session_factory() as session:
        run = Run(
            target_input='["https://acme.com"]',
            allowed_scope='["acme.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        asset = await _asset(session, run.id, "https://acme.com/a.pdf")
        session.add(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="Ada@Acme.test",
                dedup_signature=dedup_signature(asset.id, FindingType.email, "Ada@Acme.test"),
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.low,
            )
        )
        await session.commit()
        other = await _asset(session, run.id, "https://acme.com/b.pdf")
        session.add(
            Finding(
                run_id=run.id,
                asset_id=other.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="ada@acme.test",
                dedup_signature=dedup_signature(other.id, FindingType.email, "ada@acme.test"),
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.low,
            )
        )
        await session.commit()
        run_id = run.id

    await DetectionPipeline(session_factory).execute(run_id)
    async with session_factory() as session:
        groups = await groups_touching_run(session, run_id)
        findings = await session.exec(select(Finding).where(Finding.run_id == run_id))
        kinds = {FindingType(row.finding_type) for row in findings.all()}
    email_groups = [group for group in groups if group.kind is CorrelationKind.email]
    assert len(email_groups) == 1
    assert email_groups[0].value_norm == "ada@acme.test"
    assert email_groups[0].occurrences == 2
    assert kinds == {FindingType.email}
