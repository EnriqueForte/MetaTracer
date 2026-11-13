"""DeltaReporter: deterministic finding deltas between same-scope runs (TASK-22, v3.0 Eje A).

The delta is the set difference of ``dedup_signature`` between the current
run and every earlier run with the same ``allowed_scope`` snapshot. Pure
database read: no LLM, no network, nothing else touches the watch loop.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, Finding, FindingType, Run, RunStatus, Severity
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository
from metatracer.services.watch import DeltaReporter


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/watch-delta-test.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_run(
    session_factory,
    *,
    scope: str = '["t.com"]',
    signatures: list[str],
    status: RunStatus = RunStatus.pending,
    severity: Severity | None = None,
) -> Run:
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["https://t.com/a.jpg"]',
                allowed_scope=scope,
                scope_confirmed=True,
                status=status,
                total_findings=len(signatures),
            )
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
        for sig in signatures:
            await FindingRepository(session).create(
                Finding(
                    run_id=run.id,
                    asset_id=asset.id,
                    finding_type=FindingType.gps,
                    field_source="EXIF:GPSInfo",
                    evidence_snippet=f"snippet-{sig}",
                    dedup_signature=sig,
                    detector_method="rule",
                    confidence="high",
                    severity=severity,
                )
            )
    return run


async def test_first_run_reports_all_as_new(session_factory) -> None:
    run = await _seed_run(session_factory, signatures=["sig-1", "sig-2"])
    delta = await DeltaReporter(session_factory).compute_delta(run.id)
    assert delta.new_findings == 2
    assert set(delta.new_signatures) == {"sig-1", "sig-2"}


async def test_repeated_run_reports_zero_delta(session_factory) -> None:
    await _seed_run(session_factory, signatures=["sig-1"])
    second = await _seed_run(session_factory, signatures=["sig-1"])
    delta = await DeltaReporter(session_factory).compute_delta(second.id)
    assert delta.new_findings == 0
    assert delta.new_signatures == []


async def test_delta_only_reports_genuinely_new_signatures(session_factory) -> None:
    await _seed_run(session_factory, signatures=["sig-1", "sig-shared"])
    second = await _seed_run(session_factory, signatures=["sig-shared", "sig-2"])
    delta = await DeltaReporter(session_factory).compute_delta(second.id)
    assert delta.new_findings == 1
    assert delta.new_signatures == ["sig-2"]


async def test_delta_is_scoped_to_the_same_allowed_scope(session_factory) -> None:
    """A different scope's findings never count as this scope's baseline."""
    await _seed_run(session_factory, scope='["other.com"]', signatures=["sig-other"])
    mine = await _seed_run(session_factory, signatures=["sig-mine"])
    delta = await DeltaReporter(session_factory).compute_delta(mine.id)
    assert delta.new_findings == 1
    assert delta.new_signatures == ["sig-mine"]


async def test_first_run_has_zero_resolved_and_severity_up(session_factory) -> None:
    run = await _seed_run(session_factory, signatures=["sig-1"], status=RunStatus.completed)
    delta = await DeltaReporter(session_factory).compute_delta(run.id)
    assert delta.new_findings == 1
    assert delta.resolved_findings == 0
    assert delta.severity_up_count == 0
    assert delta.previous_run_id is None


async def test_resolved_counts_identities_absent_from_the_current_run(session_factory) -> None:
    first = await _seed_run(
        session_factory, signatures=["gone", "kept"], status=RunStatus.completed
    )
    second = await _seed_run(session_factory, signatures=["kept"], status=RunStatus.completed)
    delta = await DeltaReporter(session_factory).compute_delta(second.id)
    assert delta.new_findings == 0
    assert delta.resolved_findings == 1
    assert delta.severity_up_count == 0
    assert delta.previous_run_id == first.id


async def test_severity_up_counts_only_a_higher_contract_rank(session_factory) -> None:
    first = await _seed_run(
        session_factory,
        signatures=["same"],
        status=RunStatus.completed,
        severity=Severity.low,
    )
    raised = await _seed_run(
        session_factory,
        signatures=["same"],
        status=RunStatus.completed,
        severity=Severity.high,
    )
    delta = await DeltaReporter(session_factory).compute_delta(raised.id)
    assert delta.previous_run_id == first.id
    assert delta.new_findings == 0
    assert delta.resolved_findings == 0
    assert delta.severity_up_count == 1

    lowered = await _seed_run(
        session_factory,
        signatures=["same"],
        status=RunStatus.completed,
        severity=Severity.info,
    )
    down = await DeltaReporter(session_factory).compute_delta(lowered.id)
    assert down.severity_up_count == 0
    assert down.resolved_findings == 0


async def test_unclassified_severity_is_not_a_severity_up(session_factory) -> None:
    await _seed_run(
        session_factory, signatures=["same"], status=RunStatus.completed, severity=None
    )
    current = await _seed_run(
        session_factory,
        signatures=["same"],
        status=RunStatus.completed,
        severity=Severity.critical,
    )
    delta = await DeltaReporter(session_factory).compute_delta(current.id)
    assert delta.severity_up_count == 0


async def test_missing_run_raises_lookup_error(session_factory) -> None:
    import uuid

    with pytest.raises(LookupError):
        await DeltaReporter(session_factory).compute_delta(str(uuid.uuid4()))