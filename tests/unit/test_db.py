"""Persistence: schema creation, constraints, FK enforcement, nullable severity."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.core.exceptions import AmbiguousRunError, RunNotFoundError
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
)
from metatracer.db.repositories import FindingRepository, RunRepository

_TABLES = {"run", "asset", "raw_metadata_item", "finding", "agent_log", "scope", "discovery_edge"}


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/metatracer-test.db")
    yield engine
    await engine.dispose()


def _run() -> Run:
    return Run(
        target_input='["http://target.com"]',
        allowed_scope='["target.com"]',
        scope_confirmed=True,
    )


def _asset(run_id: str, file_hash: str = "ab" * 32) -> Asset:
    return Asset(
        run_id=run_id,
        source_url="http://target.com/a.pdf",
        final_url="http://target.com/a.pdf",
        content_type="application/pdf",
        file_hash_sha256=file_hash,
        file_size_bytes=128,
        extraction_status=ExtractionStatus.ok,
    )


def _finding(run_id: str, asset_id: str, signature: str = "sig") -> Finding:
    return Finding(
        run_id=run_id,
        asset_id=asset_id,
        finding_type=FindingType.gps,
        field_source="EXIF:GPSInfo",
        evidence_snippet="Latitude: 40.416775, Longitude: -3.703790",
        dedup_signature=signature,
        detector_method=DetectorMethod.rule,
        confidence=Confidence.high,
    )


async def test_init_db_creates_all_tables(engine: AsyncEngine) -> None:
    await init_db(engine)
    async with engine.connect() as connection:
        rows = await connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        assert _TABLES <= {row[0] for row in rows.fetchall()}


async def test_engine_creates_missing_sqlite_directory(tmp_path) -> None:
    """A fresh clone has no ./data/: the engine must create the parent directory."""
    nested = tmp_path / "fresh" / "data"
    assert not nested.exists()
    engine = create_db_engine(f"sqlite+aiosqlite:///{nested}/metatracer.db")
    try:
        assert nested.is_dir()
        await init_db(engine)
        assert (nested / "metatracer.db").is_file()
    finally:
        await engine.dispose()


async def test_init_db_adds_nullable_columns_to_an_older_database(tmp_path) -> None:
    """A database created before `Run.executive_summary` / `Finding.title` keeps working."""
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/old.db")
    try:
        await init_db(engine)
        async with engine.begin() as connection:
            # Simulate the pre-audit schema by dropping the two newer columns.
            await connection.exec_driver_sql("ALTER TABLE run DROP COLUMN executive_summary")
            await connection.exec_driver_sql("ALTER TABLE finding DROP COLUMN title")
        await init_db(engine)  # second start-up on the older schema
        async with engine.connect() as connection:
            run_cols = {r[1] for r in (await connection.exec_driver_sql("PRAGMA table_info(run)"))}
            finding_cols = {
                r[1] for r in (await connection.exec_driver_sql("PRAGMA table_info(finding)"))
            }
        assert "executive_summary" in run_cols
        assert "title" in finding_cols

        factory = create_session_factory(engine)
        async with factory() as session:
            run = await RunRepository(session).create(_run())
        async with factory() as session:
            loaded = await RunRepository(session).get(run.id)
        assert loaded is not None and loaded.executive_summary is None
    finally:
        await engine.dispose()


async def test_in_memory_sqlite_needs_no_directory() -> None:
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    try:
        await init_db(engine)
    finally:
        await engine.dispose()


async def test_init_db_creates_composite_index(engine: AsyncEngine) -> None:
    await init_db(engine)
    async with engine.connect() as connection:
        rows = await connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
        assert "ix_asset_run_id_file_hash_sha256" in {row[0] for row in rows.fetchall()}


async def test_foreign_keys_enforced_per_connection(engine: AsyncEngine) -> None:
    await init_db(engine)
    async with engine.connect() as connection:
        rows = await connection.exec_driver_sql("PRAGMA foreign_keys")
        assert rows.scalar() == 1


async def test_orphan_asset_rejected_by_fk(engine: AsyncEngine) -> None:
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        session.add(_asset(run_id="no-such-run"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_finding_severity_is_nullable(engine: AsyncEngine) -> None:
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        run = await RunRepository(session).create(_run())
        asset = _asset(run.id)
        session.add(asset)
        await session.commit()
        await session.refresh(asset)

        findings = FindingRepository(session)
        finding = await findings.create(_finding(run.id, asset.id))
        assert finding.severity is None

        fetched = await findings.get(finding.id)
        assert fetched is not None
        assert fetched.severity is None


async def test_dedup_signature_unique_per_asset(engine: AsyncEngine) -> None:
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        run = await RunRepository(session).create(_run())
        asset = _asset(run.id)
        other_asset = _asset(run.id, file_hash="cd" * 32)
        session.add_all([asset, other_asset])
        await session.commit()
        await session.refresh(asset)
        await session.refresh(other_asset)
        # Capture ids up front: the rollback below expires the ORM objects, and
        # touching an expired attribute would trigger IO outside a greenlet.
        run_id = run.id
        asset_id = asset.id
        other_asset_id = other_asset.id

        findings = FindingRepository(session)
        await findings.create(_finding(run_id, asset_id, signature="dup"))

        # Same (asset_id, dedup_signature) is rejected...
        with pytest.raises(IntegrityError):
            await findings.create(_finding(run_id, asset_id, signature="dup"))
        await session.rollback()

        # ...but the same signature on a different asset is allowed.
        await findings.create(_finding(run_id, other_asset_id, signature="dup"))


async def test_run_repository_crud(engine: AsyncEngine) -> None:
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        repo = RunRepository(session)
        run = await repo.create(_run())

        fetched = await repo.get(run.id)
        assert fetched is not None
        assert fetched.status == RunStatus.pending

        run.status = RunStatus.running
        await repo.update(run)
        refetched = await repo.get(run.id)
        assert refetched is not None
        assert refetched.status == RunStatus.running

        assert len(await repo.list_all()) == 1
        resolved = await repo.resolve(run.id[:8])
        assert resolved.id == run.id
        with pytest.raises(RunNotFoundError):
            await repo.resolve("zzzzzzzz")
        assert await repo.delete(run.id) is True
        assert await repo.get(run.id) is None


async def test_resolve_ambiguous_prefix(engine: AsyncEngine) -> None:
    await init_db(engine)
    factory = create_session_factory(engine)
    async with factory() as session:
        repo = RunRepository(session)
        first = _run()
        first.id = "aaaaaaaa-1111-4111-8111-111111111111"
        second = _run()
        second.id = "aaaaaaaa-2222-4222-8222-222222222222"
        await repo.create(first)
        await repo.create(second)
        with pytest.raises(AmbiguousRunError):
            await repo.resolve("aaaaaaaa")
