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
from metatracer.db.models import Asset, Finding, FindingType, Run
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
) -> Run:
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["https://t.com/a.jpg"]',
                allowed_scope=scope,
                scope_confirmed=True,
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


async def test_missing_run_raises_lookup_error(session_factory) -> None:
    import uuid

    with pytest.raises(LookupError):
        await DeltaReporter(session_factory).compute_delta(str(uuid.uuid4()))