"""TASK-35 block 35.4: run comparison, severity trends and cross-run identity."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    Run,
    RunStatus,
    Severity,
)
from metatracer.detectors import dedup_signature
from metatracer.services.compare import compare_runs
from metatracer.services.dashboard import DashboardStatsService, build_trends
from metatracer.services.watch import DeltaReporter


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/task35.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def seed_run(
    session_factory,
    snippets: list[str],
    *,
    url: str = "https://acme.com/a.pdf",
    severity: Severity | None = Severity.medium,
    created_at: datetime | None = None,
) -> Run:
    """One run, one asset (fresh id per run, like a real scan) and its findings."""
    async with session_factory() as session:
        run = Run(
            target_input='["https://acme.com"]',
            allowed_scope='["acme.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
            total_findings=len(snippets),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        asset = Asset(
            run_id=run.id,
            source_url=url,
            final_url=url,
            content_type="application/pdf",
            file_hash_sha256="ab" * 32,
            file_size_bytes=10,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        for snippet in snippets:
            finding = Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet=snippet,
                dedup_signature=dedup_signature(asset.id, FindingType.email, snippet),
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=severity,
            )
            if created_at is not None:
                finding.created_at = created_at
            session.add(finding)
        await session.commit()
        return run


async def test_compare_splits_new_resolved_and_persistent(session_factory) -> None:
    a = await seed_run(session_factory, ["old@acme.com", "kept@acme.com"])
    b = await seed_run(session_factory, ["kept@acme.com", "fresh@acme.com"])
    result = await compare_runs(session_factory, a.id, b.id)
    assert [item.finding.evidence_snippet for item in result.new] == ["fresh@acme.com"]
    assert [item.finding.evidence_snippet for item in result.resolved] == ["old@acme.com"]
    assert [item.finding.evidence_snippet for item in result.persistent] == ["kept@acme.com"]
    assert result.persistent[0].finding.run_id == b.id


async def test_watch_delta_matches_findings_across_fresh_asset_ids(session_factory) -> None:
    await seed_run(session_factory, ["kept@acme.com"])
    second = await seed_run(session_factory, ["kept@acme.com", "fresh@acme.com"])
    delta = await DeltaReporter(session_factory).compute_delta(second.id)
    assert delta.new_findings == 1


async def test_same_snippet_on_another_asset_is_new(session_factory) -> None:
    a = await seed_run(session_factory, ["kept@acme.com"], url="https://acme.com/a.pdf")
    b = await seed_run(session_factory, ["kept@acme.com"], url="https://acme.com/b.pdf")
    result = await compare_runs(session_factory, a.id, b.id)
    assert len(result.new) == 1 and len(result.resolved) == 1 and result.persistent == []


def test_build_trends_fills_every_day() -> None:
    today = datetime(2026, 10, 5, 12, tzinfo=UTC)
    points = build_trends(
        [("2026-10-05", "high", 2), ("2026-10-04", None, 1), ("2026-01-01", "high", 9)],
        today,
        days=3,
    )
    assert [point["date"] for point in points] == ["2026-10-03", "2026-10-04", "2026-10-05"]
    assert points[2]["high"] == 2
    assert points[1]["unclassified"] == 1
    assert sum(point["high"] for point in points) == 2


async def test_stats_service_returns_a_30_day_trend(session_factory) -> None:
    now = datetime.now(UTC)
    await seed_run(session_factory, ["a@acme.com"], severity=Severity.high, created_at=now)
    await seed_run(
        session_factory, ["b@acme.com"], severity=Severity.low, created_at=now - timedelta(days=60)
    )
    stats = await DashboardStatsService(session_factory).build(now=now)
    assert len(stats.trends) == 30
    assert stats.trends[-1]["high"] == 1
    assert sum(point["low"] for point in stats.trends) == 0
