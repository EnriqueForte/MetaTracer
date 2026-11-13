"""DashboardStatsService (TASK-11): zero rows and seeded data end-to-end."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.services.dashboard import DashboardStatsService


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/dashboard-service-test.db")
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session_factory(engine: AsyncEngine):
    await init_db(engine)
    return create_session_factory(engine)


async def test_build_with_zero_rows(session_factory) -> None:
    stats = await DashboardStatsService(session_factory).build()
    assert stats.runs == {"total": 0}
    assert stats.assets == {"total": 0, "with_issues": 0}
    assert stats.findings["total"] == 0
    assert stats.findings["unclassified"] == 0
    assert stats.findings["severity_breakdown"] == {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
        "unclassified": 0,
    }
    assert stats.findings["by_type"] == {
        "gps": 0,
        "email": 0,
        "internal_path": 0,
        "software_version": 0,
        "debug_comment": 0,
        "secret": 0,
        "internal_endpoint": 0,
        "cloud_storage": 0,
    }
    assert stats.top_domains == []
    assert stats.top_evidence == []
    assert stats.agent_usage == {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0,
    }


async def test_build_with_seeded_data(session_factory) -> None:
    # Reuse the well-tested seed from the repository test.
    from tests.unit.test_dashboard_repository import _seed

    await _seed(session_factory)

    stats = await DashboardStatsService(session_factory).build()
    assert stats.runs["total"] == 2
    assert stats.runs.get("completed") == 1
    assert stats.runs.get("failed") == 1
    assert stats.assets["total"] == 2
    assert stats.assets["with_issues"] == 1
    assert stats.findings["total"] == 3
    assert stats.findings["severity_breakdown"]["high"] == 1
    assert stats.findings["severity_breakdown"]["unclassified"] == 1
    assert stats.findings["by_type"]["email"] == 2
    assert stats.top_domains  # non-empty after seeding
    assert any(entry["finding_type"] == "email" for entry in stats.top_evidence)
    assert stats.agent_usage["calls"] == 1
    assert stats.agent_usage["total_tokens"] == 30