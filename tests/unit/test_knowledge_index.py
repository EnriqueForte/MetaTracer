"""KnowledgeIndex (TASK-14, v2.1+): FTS5 index rebuild + search + filters."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.agents.knowledge import KnowledgeIndex
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, Finding, FindingType, Run, Severity
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RunRepository,
)


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/knowledge-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


def _asset(run_id: str, name: str) -> Asset:
    return Asset(
        run_id=run_id,
        source_url=f"https://t.com/{name}.jpg",
        final_url=f"https://t.com/{name}.jpg",
        content_type="image/jpeg",
        file_hash_sha256=f"hash-{name}",
        file_size_bytes=1024,
        extraction_status="ok",
    )


def _finding(
    run_id: str,
    asset_id: str,
    finding_type: FindingType,
    snippet: str,
    *,
    severity: Severity | None,
    title: str | None = None,
) -> Finding:
    return Finding(
        run_id=run_id,
        asset_id=asset_id,
        finding_type=finding_type,
        field_source="EXIF:GPSInfo" if finding_type is FindingType.gps else "EXIF:Path",
        evidence_snippet=snippet,
        dedup_signature=f"sig-{snippet}",
        detector_method="rule",
        confidence="high",
        severity=severity,
        title=title,
    )


async def _seed(engine: AsyncEngine) -> None:
    """Two runs with one gps + one internal_path finding each."""
    async with create_session_factory(engine)() as session:
        run = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
        )
        run2 = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
        )
        asset = await AssetRepository(session).create(_asset(run.id, "a"))
        asset2 = await AssetRepository(session).create(_asset(run2.id, "b"))
        await FindingRepository(session).create_many(
            [
                _finding(
                    run.id,
                    asset.id,
                    FindingType.gps,
                    "Latitude: 41.6521, Longitude: -0.8809",
                    severity=Severity.high,
                    title="Public square GPS",
                ),
                _finding(
                    run.id,
                    asset.id,
                    FindingType.internal_path,
                    "/home/jane/private/config",
                    severity=Severity.medium,
                ),
                _finding(
                    run2.id,
                    asset2.id,
                    FindingType.gps,
                    "Latitude: 41.6521, Longitude: -0.8809",
                    severity=Severity.high,
                ),
            ]
        )


async def test_rebuild_then_search_returns_top_ranked(engine: AsyncEngine) -> None:
    await _seed(engine)
    index = KnowledgeIndex(engine, create_session_factory(engine))
    await index.rebuild()
    hits = await index.search("41.6521")
    assert len(hits) >= 1
    assert all(hit.finding_type is FindingType.gps for hit in hits)
    # same snippet in two runs -> the top hit is one of the GPS rows
    assert hits[0].severity is Severity.high


async def test_search_filters_by_finding_type(engine: AsyncEngine) -> None:
    await _seed(engine)
    index = KnowledgeIndex(engine, create_session_factory(engine))
    await index.rebuild()
    hits = await index.search(
        "jetsam ",
        finding_type=FindingType.internal_path,
    )
    assert all(hit.finding_type is FindingType.internal_path for hit in hits)
    assert all(hit.severity is Severity.medium for hit in hits)


async def test_search_excludes_finding_id(engine: AsyncEngine) -> None:
    await _seed(engine)
    index = KnowledgeIndex(engine, create_session_factory(engine))
    await index.rebuild()
    all_gps = await index.search("41.6521")
    assert len(all_gps) >= 2
    first_id = all_gps[0].finding_id
    rest = await index.search("41.6521", exclude_finding_id=first_id)
    assert all(hit.finding_id != first_id for hit in rest)


async def test_search_empty_index_is_noop(engine: AsyncEngine) -> None:
    # no findings seeded -> rebuild yields an empty index
    index = KnowledgeIndex(engine, create_session_factory(engine))
    await index.rebuild()
    assert await index.search("anything") == []


async def test_rebuild_is_idempotent(engine: AsyncEngine) -> None:
    await _seed(engine)
    index = KnowledgeIndex(engine, create_session_factory(engine))
    await index.rebuild()
    first = await index.search("41.6521")
    await index.rebuild()
    second = await index.search("41.6521")
    assert len(first) == len(second)