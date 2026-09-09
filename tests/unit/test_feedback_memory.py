"""FeedbackMemory (TASK-13, v2.1+): few-shot loader and type-safe bucketing."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.agents.memory import FeedbackMemory, examples_to_payload
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    FeedbackVote,
    Finding,
    FindingFeedback,
    FindingType,
    Run,
    Severity,
)
from metatracer.db.repositories import (
    AssetRepository,
    FeedbackRepository,
    FindingRepository,
    RunRepository,
)


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/memory-test.db")
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session_factory(engine: AsyncEngine):
    await init_db(engine)
    return create_session_factory(engine)


async def test_load_filters_by_type_and_caps(
    session_factory, engine: AsyncEngine
) -> None:
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
        )
        asset2 = await AssetRepository(session).create(
            Asset(
                run_id=run.id,
                source_url="https://t.com/b.jpg",
                final_url="https://t.com/b.jpg",
                content_type="image/jpeg",
                file_hash_sha256="h-a2",
                file_size_bytes=10,
                extraction_status="ok",
            )
        )
        gps_findings = []
        for i in range(6):  # 6 distinct gps findings -> cap at 5
            asset = await AssetRepository(session).create(
                Asset(
                    run_id=run.id,
                    source_url=f"https://t.com/gps-{i}.jpg",
                    final_url=f"https://t.com/gps-{i}.jpg",
                    content_type="image/jpeg",
                    file_hash_sha256=f"h-gps-{i}",
                    file_size_bytes=10,
                    extraction_status="ok",
                )
            )
            gps_findings.append(
                await FindingRepository(session).create(
                    Finding(
                        run_id=run.id,
                        asset_id=asset.id,
                        finding_type=FindingType.gps,
                        field_source="EXIF:GPSInfo",
                        evidence_snippet=f"Latitude: 41.{i}",
                        dedup_signature=f"sig-gps-{i}",
                        detector_method="rule",
                        confidence="high",
                        severity=Severity.high,
                    )
                )
            )
        path = await FindingRepository(session).create(
            Finding(
                run_id=run.id,
                asset_id=asset2.id,
                finding_type=FindingType.internal_path,
                field_source="EXIF:Path",
                evidence_snippet="/home/jane",
                dedup_signature="sig-path-1",
                detector_method="rule",
                confidence="medium",
                severity=Severity.medium,
            )
        )
        repo = FeedbackRepository(session)
        for i, gps_finding in enumerate(gps_findings):  # one per finding, up to cap
            await repo.create(
                FindingFeedback(
                    finding_id=gps_finding.id,
                    run_id=run.id,
                    vote=FeedbackVote.down,
                    severity_before=Severity.high,
                    severity_after=Severity.medium,
                    reason=f"note {i}",
                )
            )
        await repo.create(
            FindingFeedback(
                finding_id=path.id,
                run_id=run.id,
                vote=FeedbackVote.up,
                severity_before=Severity.medium,
                severity_after=Severity.high,
            )
        )

    memory = FeedbackMemory(max_examples_per_type=5)
    await memory.load(session_factory)

    gps_examples = memory.examples_for(FindingType.gps)
    assert len(gps_examples) == 5  # capped
    assert all(e.finding_type is FindingType.gps for e in gps_examples)
    assert all(e.vote is FeedbackVote.down for e in gps_examples)
    # the note/reason must never travel with the example
    assert all(
        e.evidence_snippet.startswith("Latitude: 41.") for e in gps_examples
    )
    # other types are not polluted
    assert len(memory.examples_for(FindingType.internal_path)) == 1
    assert len(memory.examples_for(FindingType.email)) == 0
    assert len(memory.examples_for(FindingType.software_version)) == 0


async def test_load_without_rows_is_noop(session_factory) -> None:
    memory = FeedbackMemory()
    await memory.load(session_factory)
    for ftype in FindingType:
        assert memory.examples_for(ftype) == []


async def test_examples_to_payload_excludes_reason_and_caps_size() -> None:
    from metatracer.agents.memory import FeedbackExample

    examples = [
        FeedbackExample(
            finding_type=FindingType.gps,
            evidence_snippet="Lat: 41.65, Lon: -0.88",
            field_source="EXIF:GPSInfo",
            severity_before=Severity.high,
            severity_after=Severity.medium,
            vote=FeedbackVote.down,
        )
        for _ in range(3)
    ]
    payloads = examples_to_payload(examples, max_chars=200)
    # at least the first fits; never more than the input
    assert 1 <= len(payloads) <= 3
    first = payloads[0]
    assert "reason" not in first
    assert "finding_id" not in first
    assert first["vote"] == "down"
    assert first["severity_after"] == "medium"