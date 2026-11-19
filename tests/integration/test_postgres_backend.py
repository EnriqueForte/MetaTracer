"""TASK-23 (Eje B): PostgreSQL integration tests (skipped without a server).

These tests run against a real PostgreSQL + pgvector server, configurable via
``METATRACER_TEST_PG_URL`` (default: the local compose/db container URL).
When the server is unreachable every test in this module SKIPS — the CI
suite stays fully local (TASK-16 posture), and a developer with the
``pgvector/pgvector:pg17`` image running gets full backend coverage:

    docker run -d --name metatracer-pg17 -p 5432:5432 \
      -e POSTGRES_PASSWORD=metatracer -e POSTGRES_DB=metatracer \
      pgvector/pgvector:pg17
    python -m pytest tests/integration/test_postgres_backend.py -q

Each test uses its own scratch database (created and dropped per test) so
runs never interfere with each other or with a developer's local data.
"""

import os
import socket
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from metatracer.db.engine import create_db_engine, create_session_factory, init_db

TEST_PG_URL = os.environ.get(
    "METATRACER_TEST_PG_URL",
    "postgresql+asyncpg://postgres:metatracer@localhost:5432/metatracer",
)


def _server_reachable() -> bool:
    try:
        url = TEST_PG_URL.split("//", 1)[1]
        userpass, hostport_db = url.split("@", 1)
        hostport = hostport_db.split("/", 1)[0]
        host, port = hostport.split(":")
        with socket.create_connection((host, int(port)), timeout=1.0):
            return True
    except (OSError, ValueError):
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason="PostgreSQL test server not reachable (set METATRACER_TEST_PG_URL)",
)


@pytest.fixture()
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """A per-test scratch database running the full init_db path."""
    scratch_db = f"mt_test_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(TEST_PG_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        # CREATE/DROP DATABASE cannot run inside a transaction block.
        await conn.exec_driver_sql(f'CREATE DATABASE "{scratch_db}"')
    await admin.dispose()

    url = TEST_PG_URL.rsplit("/", 1)[0] + f"/{scratch_db}"
    engine = create_db_engine(url)
    yield engine
    await engine.dispose()
    admin = create_async_engine(TEST_PG_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        # terminate lingering connections, then drop
        await conn.exec_driver_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{scratch_db}' AND pid <> pg_backend_pid()"
        )
        await conn.exec_driver_sql(f'DROP DATABASE "{scratch_db}"')
    await admin.dispose()


async def test_init_db_runs_migrations_and_is_idempotent(pg_engine: AsyncEngine) -> None:
    from metatracer.db.engine import init_db

    await init_db(pg_engine)
    await init_db(pg_engine)  # second call must be a no-op
    async with pg_engine.connect() as conn:
        tables = {
            row[0]
            for row in await conn.exec_driver_sql(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        }
        assert {
            "run",
            "asset",
            "raw_metadata_item",
            "finding",
            "agent_log",
            "scope",
            "webhook_config",
            "webhook_delivery",
            "finding_feedback",
            "alembic_version",
        } <= tables
        version = (await conn.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar()
        assert version  # migrated to a real head


async def test_postgres_enforces_foreign_keys(pg_engine: AsyncEngine) -> None:
    from sqlalchemy.exc import IntegrityError

    from metatracer.db.engine import init_db
    from metatracer.db.models import Asset

    await init_db(pg_engine)
    factory = create_session_factory(pg_engine)
    async with factory() as session:
        session.add(
            Asset(
                run_id="nonexistent-run",
                source_url="https://t.example/a.jpg",
                final_url="https://t.example/a.jpg",
                content_type="image/jpeg",
                file_hash_sha256="ab" * 32,
                file_size_bytes=1,
                extraction_status="ok",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_pgvector_retriever_end_to_end(pg_engine: AsyncEngine) -> None:
    from datetime import UTC, datetime

    from metatracer.agents.knowledge import KnowledgeRetriever
    from metatracer.db.engine import init_db
    from metatracer.db.models import (
        Asset,
        Confidence,
        DetectorMethod,
        Finding,
        FindingType,
        Run,
        Severity,
    )

    await init_db(pg_engine)
    factory = create_session_factory(pg_engine)
    run_id, asset_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        session.add(
            Run(
                id=run_id,
                run_ref="pgtest01",
                target_input='["example.com"]',
                allowed_scope='["example.com"]',
                scope_confirmed=True,
                status="completed",
            )
        )
        await session.flush()  # Postgres enforces FKs: Run must exist first
        session.add(
            Asset(
                id=asset_id,
                run_id=run_id,
                source_url="https://example.com/p.jpg",
                final_url="https://example.com/p.jpg",
                content_type="image/jpeg",
                file_hash_sha256="cd" * 32,
                file_size_bytes=2,
                extraction_status="ok",
            )
        )
        await session.flush()
        session.add(
            Finding(
                id=str(uuid.uuid4()),
                run_id=run_id,
                asset_id=asset_id,
                finding_type=FindingType.gps,
                field_source="EXIF:GPSInfo",
                evidence_snippet="Latitude: 40.416775, Longitude: -3.703790",
                dedup_signature=str(uuid.uuid4()),
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.high,
                title="GPS coordinates in image metadata",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    retriever = KnowledgeRetriever(pg_engine, factory)
    hits = await retriever.retrieve(
        {"evidence_snippet": "Latitude: 40.416775, Longitude: -3.703790", "finding_type": "gps"}
    )
    assert len(hits) == 1
    assert hits[0].finding_type == FindingType.gps
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)
    assert hits[0].title == "GPS coordinates in image metadata"

    # The email-typed filter excludes the GPS row.
    none = await retriever.retrieve(
        {"evidence_snippet": "Latitude: 40.416775, Longitude: -3.703790", "finding_type": "email"}
    )
    assert none == []


async def test_pgvector_index_rebuild_is_idempotent(pg_engine: AsyncEngine) -> None:
    from metatracer.agents.knowledge_pg import PgVectorKnowledgeIndex
    from metatracer.db.engine import init_db

    await init_db(pg_engine)
    factory = create_session_factory(pg_engine)
    index = PgVectorKnowledgeIndex(pg_engine, factory)
    await index.rebuild()
    await index.rebuild()  # drop/create path must be repeatable
    hits = await index.search("anything")
    assert hits == []  # empty findings table -> empty index, no crash


async def test_knowledge_search_api_page_over_postgres(pg_engine: AsyncEngine) -> None:
    """The API knowledge endpoint answers over the pgvector backend (smoke)."""
    from metatracer.agents.knowledge import KnowledgeRetriever

    await init_db(pg_engine)
    # The app wiring resolves the backend from the engine's dialect; a full
    # API smoke lives in the e2e tier — here we assert the retriever reports
    # an empty-but-functional index (no 503 path, no crash).
    retriever = KnowledgeRetriever(pg_engine, create_session_factory(pg_engine))
    assert await retriever.retrieve({"evidence_snippet": "x"}) == []


async def test_delete_cascade_leaves_no_orphans_on_postgres(pg_engine: AsyncEngine) -> None:
    from sqlalchemy import text

    from metatracer.agents.knowledge_pg import PgVectorKnowledgeIndex
    from metatracer.db.models import (
        Asset,
        AssetValue,
        Confidence,
        CorrelationKind,
        DetectorMethod,
        DiscoveryEdge,
        DiscoveryEdgeKind,
        ExtractionStatus,
        Finding,
        FindingType,
        Run,
        RunStatus,
        ValueEntity,
    )
    from metatracer.db.repositories import RunRepository
    from metatracer.services.retention import delete_run

    await init_db(pg_engine)
    factory = create_session_factory(pg_engine)
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.example"]',
                allowed_scope='["target.example"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
        asset = Asset(
            run_id=run.id,
            source_url="https://target.example/a.pdf",
            final_url="https://target.example/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="cd" * 32,
            file_size_bytes=8,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        session.add(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="ada@target.example",
                dedup_signature="pg-sig",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
            )
        )
        entity = ValueEntity(
            kind=CorrelationKind.email,
            value_hash="c" * 64,
            value_norm="ada@target.example",
            first_seen_run_id=run.id,
            occurrences=1,
        )
        session.add(entity)
        await session.commit()
        await session.refresh(entity)
        session.add(
            AssetValue(
                asset_id=asset.id,
                entity_id=entity.id,
                namespace="pdfinfo",
                key="Author",
            )
        )
        session.add(
            DiscoveryEdge(
                run_id=run.id,
                from_url="https://target.example/",
                to_url="https://target.example/a.pdf",
                kind=DiscoveryEdgeKind.document,
            )
        )
        await session.commit()
        run_id = run.id
    await PgVectorKnowledgeIndex(pg_engine, factory).rebuild()
    await delete_run(factory, run_id)
    async with pg_engine.connect() as conn:
        findings = (
            await conn.execute(
                text("SELECT COUNT(*) FROM finding WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        ).scalar_one()
        vectors = (
            await conn.execute(
                text("SELECT COUNT(*) FROM knowledge_vectors WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        ).scalar_one()
        runs = (
            await conn.execute(
                text("SELECT COUNT(*) FROM run WHERE id = :run_id"),
                {"run_id": run_id},
            )
        ).scalar_one()
        edges = (
            await conn.execute(
                text("SELECT COUNT(*) FROM discovery_edge WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        ).scalar_one()
        values = (await conn.execute(text("SELECT COUNT(*) FROM asset_value"))).scalar_one()
        entities = (
            await conn.execute(
                text("SELECT COUNT(*) FROM value_entity WHERE first_seen_run_id = :run_id"),
                {"run_id": run_id},
            )
        ).scalar_one()
    assert findings == 0
    assert vectors == 0
    assert runs == 0
    assert edges == 0
    assert values == 0
    assert entities == 0
