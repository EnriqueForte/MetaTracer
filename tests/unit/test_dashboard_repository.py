"""Dashboard aggregations (TASK-11): summary, top domains/evidence, agent usage."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.core.safety.scope import normalize_host
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    AgentLog,
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
from metatracer.db.repositories import DashboardRepository


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/dashboard-repo-test.db")
    yield engine
    await engine.dispose()


@pytest.fixture()
async def repo(engine: AsyncEngine) -> AsyncIterator[DashboardRepository]:
    await init_db(engine)
    async with create_session_factory(engine)() as session:
        yield DashboardRepository(session)


async def _seed(session_factory) -> None:
    """Two runs, several findings (incl. None severity), assets, one agent log."""
    async with session_factory() as session:
        run1 = Run(
            target_input='["http://target.com/a"]',
            allowed_scope='["target.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        run2 = Run(
            target_input='["http://other.com/b"]',
            allowed_scope='["other.com"]',
            scope_confirmed=True,
            status=RunStatus.failed,
        )
        session.add_all([run1, run2])
        await session.commit()
        await session.refresh(run1)
        await session.refresh(run2)

        asset1 = Asset(
            run_id=run1.id,
            source_url="http://target.com/a.pdf",
            final_url="http://target.com/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="aa" * 32,
            file_size_bytes=100,
            extraction_status=ExtractionStatus.ok,
        )
        asset2 = Asset(
            run_id=run2.id,
            source_url="http://other.com/b.jpg",
            final_url="http://other.com/b.jpg",
            content_type="image/jpeg",
            file_hash_sha256="bb" * 32,
            file_size_bytes=100,
            extraction_status=ExtractionStatus.failed,
        )
        session.add_all([asset1, asset2])
        await session.commit()
        await session.refresh(asset1)
        await session.refresh(asset2)

        findings = [
            Finding(
                run_id=run1.id,
                asset_id=asset1.id,
                finding_type=FindingType.gps,
                field_source="EXIF:GPSInfo",
                evidence_snippet="Lat 40, Lon -3",
                dedup_signature="sig-gps-1",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.high,
            ),
            Finding(
                run_id=run1.id,
                asset_id=asset1.id,
                finding_type=FindingType.email,
                field_source="PDF:Author",
                evidence_snippet="a@b.com",
                dedup_signature="sig-email-1",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=None,  # unclassified
            ),
        ]
        session.add_all(findings)
        # A second finding with the SAME dedup_signature, but on a DIFFERENT
        # asset: top_evidence must count it as ONE entry with occurrences=2.
        # (asset2 belongs to run2, so it also keeps the failed/issue counter.)
        session.add(
            Finding(
                run_id=run2.id,
                asset_id=asset2.id,
                finding_type=FindingType.email,
                field_source="PDF:Creator",
                evidence_snippet="a@b.com",
                dedup_signature="sig-email-1",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.medium,
            )
        )
        await session.commit()

        session.add(
            AgentLog(
                run_id=run1.id,
                finding_id=findings[0].id,
                prompt_tokens=10,
                completion_tokens=20,
                model_name="test-model",
                latency_ms=30,
                raw_response='{"severity": "high"}',
            )
        )
        await session.commit()


async def test_summary_counts(repo: DashboardRepository, engine: AsyncEngine) -> None:
    await _seed(create_session_factory(engine))
    summary = await repo.summary()
    assert summary["total_runs"] == 2
    assert summary["by_status"] == {"completed": 1, "failed": 1}
    assert summary["total_assets"] == 2
    assert summary["assets_with_issues"] == 1
    assert summary["total_findings"] == 3
    assert summary["by_severity"] == {"high": 1, "medium": 1}
    assert summary["by_type"] == {"gps": 1, "email": 2}
    assert summary["unclassified"] == 1


async def test_top_domains_normalizes_and_counts(
    repo: DashboardRepository, engine: AsyncEngine
) -> None:
    await _seed(create_session_factory(engine))
    result = dict(await repo.top_domains())
    # target.com appears in run1.allowed_scope AND asset1.final_url.
    assert result["target.com"] == 2
    assert result["other.com"] == 2  # run2 scope + asset2
    assert all(normalize_host(domain) == domain for domain in result)


async def test_top_evidence_groups_by_dedup_signature(
    repo: DashboardRepository, engine: AsyncEngine
) -> None:
    await _seed(create_session_factory(engine))
    entries = await repo.top_evidence()
    assert len(entries) == 2  # two distinct signatures, not three findings
    by_sig = {entry["signature"]: entry for entry in entries}
    assert by_sig["sig-email-1"]["occurrences"] == 2
    assert by_sig["sig-email-1"]["finding_type"] == "email"
    assert by_sig["sig-gps-1"]["occurrences"] == 1


async def test_agent_usage_sums(repo: DashboardRepository, engine: AsyncEngine) -> None:
    await _seed(create_session_factory(engine))
    usage = await repo.agent_usage()
    assert usage["calls"] == 1
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 30
    assert usage["latency_ms"] == 30


async def test_empty_database_returns_zeros(repo: DashboardRepository) -> None:
    summary = await repo.summary()
    assert summary["total_runs"] == 0
    assert summary["by_status"] == {}
    assert summary["total_assets"] == 0
    assert summary["assets_with_issues"] == 0
    assert summary["total_findings"] == 0
    assert summary["by_severity"] == {}
    assert summary["by_type"] == {}
    assert summary["unclassified"] == 0
    assert await repo.top_domains() == []
    assert await repo.top_evidence() == []
    assert await repo.agent_usage() == {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0,
    }