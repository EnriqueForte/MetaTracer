"""
KnowledgeRetriever (TASK-14, v2.1+): builds the query from the payload;
no-op without an index.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, Finding, FindingType, Run, Severity
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/knowledge-retriever-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


async def _seed_gps(engine: AsyncEngine) -> str:
    """Seed one GPS finding; returns its id for exclusion checks."""
    async with create_session_factory(engine)() as session:
        run = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
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
        f = await FindingRepository(session).create(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.gps,
                field_source="EXIF:GPSInfo",
                evidence_snippet="Latitude: 41.6521, Longitude: -0.8809",
                dedup_signature="sig-gps-a",
                detector_method="rule",
                confidence="high",
                severity=Severity.high,
            )
        )
        return f.id


async def test_retrieve_builds_query_from_payload(engine: AsyncEngine) -> None:
    await _seed_gps(engine)
    retriever = KnowledgeRetriever(engine, create_session_factory(engine))
    hits = await retriever.retrieve(
        {
            "evidence_snippet": "Latitude: 41.6521, Longitude: -0.8809",
            "finding_type": "gps",
            "field_source": "EXIF:GPSInfo",
        }
    )
    assert len(hits) == 1
    assert hits[0].finding_type is FindingType.gps
    assert hits[0].severity is Severity.high


async def test_retrieve_empty_payload_is_noop(engine: AsyncEngine) -> None:
    retriever = KnowledgeRetriever(engine, create_session_factory(engine))
    assert (
        await retriever.retrieve({"evidence_snippet": "", "finding_type": "gps"}) == []
    )


async def test_retrieve_empty_index_is_noop(engine: AsyncEngine) -> None:
    retriever = KnowledgeRetriever(engine, create_session_factory(engine))
    # nothing seeded -> rebuild produces an empty index -> no hits
    assert (
        await retriever.retrieve(
            {"evidence_snippet": "anything at all", "finding_type": "gps"}
        )
        == []
    )


async def test_retrieve_excludes_current_finding(engine: AsyncEngine) -> None:
    gps_id = await _seed_gps(engine)
    retriever = KnowledgeRetriever(engine, create_session_factory(engine))
    hits = await retriever.retrieve(
        {
            "evidence_snippet": "Latitude: 41.6521, Longitude: -0.8809",
            "finding_type": "gps",
        },
        exclude_finding_id=gps_id,
    )
    assert hits == []  # the only matching row is the excluded one


async def test_retrieve_no_double_sanitization_regression(engine: AsyncEngine) -> None:
    """The retriever must pass the RAW snippet to search() (TASK-17).

    Regression for the double-sanitization bug: pre-sanitizing in the
    retriever produced ``"..." AND "AND" ...`` (the word AND became a term),
    which never matched. The snippet with FTS5-special characters (``:`` ``-``)
    must still retrieve the row.
    """
    await _seed_gps(engine)
    retriever = KnowledgeRetriever(engine, create_session_factory(engine))
    hits = await retriever.retrieve(
        {
            "evidence_snippet": "Latitude: 41.6521, Longitude: -0.8809",
            "finding_type": "gps",
        }
    )
    assert len(hits) == 1
    assert hits[0].finding_type is FindingType.gps
    assert hits[0].severity is Severity.high