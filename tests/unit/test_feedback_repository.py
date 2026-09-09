"""Persistence of operator feedback (TASK-13, v2.1+): CRUD + upsert semantics."""

from collections.abc import AsyncIterator

import pytest
import sqlalchemy.exc
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    FeedbackVote,
    Finding,
    FindingFeedback,
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
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/feedback-test.db")
    yield engine
    await engine.dispose()


@pytest.fixture()
async def run_row(engine: AsyncEngine) -> Run:
    await init_db(engine)
    async with create_session_factory(engine)() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.com"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
            )
        )
        return run


@pytest.fixture()
async def finding(engine: AsyncEngine, run_row: Run) -> Finding:
    async with create_session_factory(engine)() as session:
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run_row.id,
                source_url="https://target.com/photo.jpg",
                final_url="https://target.com/photo.jpg",
                content_type="image/jpeg",
                file_hash_sha256="hash-a1",
                file_size_bytes=1024,
                extraction_status="ok",
            )
        )
        f = await FindingRepository(session).create(
            Finding(
                run_id=run_row.id,
                asset_id=asset.id,
                finding_type="internal_path",
                field_source="EXIF:Path",
                evidence_snippet="/home/jane/private",
                dedup_signature="sig-1",
                detector_method="rule",
                confidence="high",
                severity=Severity.high,
            )
        )
        return f


@pytest.fixture()
async def repo(engine: AsyncEngine) -> AsyncIterator[FeedbackRepository]:
    await init_db(engine)
    async with create_session_factory(engine)() as session:
        yield FeedbackRepository(session)


def _feedback(finding_id: str, run_id: str) -> FindingFeedback:
    return FindingFeedback(
        finding_id=finding_id,
        run_id=run_id,
        vote=FeedbackVote.down,
        severity_before=Severity.high,
        severity_after=Severity.medium,
        reason="public office, not a home",
    )


async def test_create_and_get(repo: FeedbackRepository, finding: Finding, run_row: Run) -> None:
    created = await repo.create(_feedback(finding.id, run_row.id))
    assert created.id
    fetched = await repo.get_by_finding(finding.id)
    assert fetched is not None
    assert fetched.vote is FeedbackVote.down
    assert fetched.severity_before is Severity.high
    assert fetched.severity_after is Severity.medium
    assert fetched.reason == "public office, not a home"
    assert fetched.created_at is not None


async def test_get_by_finding_absent(repo: FeedbackRepository) -> None:
    assert await repo.get_by_finding("nope") is None


async def test_upsert_replaces_not_duplicates(
    repo: FeedbackRepository, finding: Finding, run_row: Run
) -> None:
    first = await repo.upsert_by_finding(_feedback(finding.id, run_row.id))
    second = await repo.upsert_by_finding(
        FindingFeedback(
            finding_id=finding.id,
            run_id=run_row.id,
            vote=FeedbackVote.up,
            severity_before=Severity.medium,
            severity_after=Severity.high,
            reason="re-checked: internal server",
        )
    )
    assert second.id != first.id  # replacement, not the same row
    fetched = await repo.get_by_finding(finding.id)
    assert fetched is not None
    assert fetched.vote is FeedbackVote.up
    assert fetched.severity_after is Severity.high
    assert fetched.reason == "re-checked: internal server"
    # exactly one row for this finding remains
    rows = await repo.list_recent()
    assert [r.finding_id for r in rows].count(finding.id) == 1


async def test_unique_constraint_blocks_duplicate_rows(
    engine: AsyncEngine, finding: Finding, run_row: Run
) -> None:
    """Defense in depth: the DB itself enforces one active feedback per finding.

    The repository-level upsert is race-safe only for a single writer; the
    unique(finding_id) constraint guarantees the contract even if two
    sessions insert concurrently (TASK-13 contract: never duplicate memory).
    """
    await init_db(engine)
    async with create_session_factory(engine)() as session:
        repo = FeedbackRepository(session)
        await repo.create(_feedback(finding.id, run_row.id))

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await repo.create(_feedback(finding.id, run_row.id))


async def test_delete(repo: FeedbackRepository, finding: Finding, run_row: Run) -> None:
    await repo.create(_feedback(finding.id, run_row.id))
    assert await repo.delete(finding.id) is True
    assert await repo.get_by_finding(finding.id) is None
    assert await repo.delete(finding.id) is False


async def test_list_recent_newest_first(
    engine: AsyncEngine, finding: Finding, run_row: Run
) -> None:
    await init_db(engine)
    async with create_session_factory(engine)() as session:
        repo = FeedbackRepository(session)
        await repo.create(_feedback(finding.id, run_row.id))
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run_row.id,
                source_url="https://target.com/2.jpg",
                final_url="https://target.com/2.jpg",
                content_type="image/jpeg",
                file_hash_sha256="hash-a2",
                file_size_bytes=2048,
                extraction_status="ok",
            )
        )
        other = await FindingRepository(session).create(
            Finding(
                run_id=run_row.id,
                asset_id=asset.id,
                finding_type="email",
                field_source="EXIF:Contact",
                evidence_snippet="jane@target.com",
                dedup_signature="sig-2",
                detector_method="rule",
                confidence="high",
                severity=Severity.low,
            )
        )
        await repo.create(
            FindingFeedback(
                finding_id=other.id,
                run_id=run_row.id,
                vote=FeedbackVote.up,
                severity_before=Severity.low,
                severity_after=Severity.medium,
            )
        )
    async with create_session_factory(engine)() as session:
        rows = await FeedbackRepository(session).list_recent()
    assert len(rows) == 2
    # newest first (upsert of `other` happened after `finding`'s)
    assert rows[0].finding_id == other.id
    assert rows[1].finding_id == finding.id