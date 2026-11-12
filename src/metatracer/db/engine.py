"""Async engine factory and schema initialization."""

import asyncio
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import event, inspect, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

# Keep in sync with the Settings.database_url default in metatracer.core.config.
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/metatracer.db"

# TASK-23 (Eje B): the supported PostgreSQL backend is asyncpg. A bare
# ``postgresql://`` URL would silently resolve to the psycopg2 dialect (not a
# dependency, and a sync driver) — fail fast with a clear message instead.
POSTGRES_DRIVER = "postgresql+asyncpg"


def create_db_engine(database_url: str = DEFAULT_DATABASE_URL) -> AsyncEngine:
    """Create the async engine for SQLite or PostgreSQL (TASK-23, Eje B).

    On SQLite, foreign keys are enforced per connection and the parent
    directory of the database file is created if missing. On PostgreSQL the
    server enforces foreign keys, so there is nothing to install per
    connection; the driver is pinned to ``asyncpg`` (see POSTGRES_DRIVER).
    """
    url = make_url(database_url)
    backend = url.get_backend_name()
    if backend == "postgresql":
        if url.drivername != POSTGRES_DRIVER:
            raise ValueError(
                f"PostgreSQL URLs must use the asyncpg driver ({POSTGRES_DRIVER}://...); "
                f"got {url.drivername!r}"
            )
    elif backend != "sqlite":
        raise ValueError(
            f"unsupported database backend {backend!r}: expected sqlite or "
            f"{POSTGRES_DRIVER}"
        )
    engine = create_async_engine(database_url, echo=False)
    if backend == "sqlite":
        # A file-backed SQLite database cannot be created in a missing directory
        # (the default ./data/ is git-ignored, so a fresh clone lacks it).
        _ensure_sqlite_directory(engine.url.database)
        # PRAGMA foreign_keys is per-connection in SQLite, so it must be set on
        # every new connection, not once at init time.
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _ensure_sqlite_directory(database: str | None) -> None:
    """Create the parent directory of a file-backed SQLite URL (no-op for ``:memory:``)."""
    if not database or database == ":memory:" or database.startswith("file:"):
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def init_db(engine: AsyncEngine) -> None:
    """Initialize the schema for the configured backend (TASK-23, Eje B).

    **PostgreSQL** runs the packaged Alembic migrations to ``head`` (the
    declarative models are the source of truth; the initial migration was
    generated with ``alembic revision --autogenerate``). ``CREATE EXTENSION
    vector`` runs first, idempotently, so the pgvector-based knowledge index
    (TASK-23) can build its derived table on demand.

    **SQLite** keeps the legacy bootstrap (``create_all`` + additive
    ``ALTER TABLE ... ADD COLUMN`` for missing nullable/defaulted columns) so
    existing local databases stay upgradeable without Alembic (TASK-13
    posture). Non-nullable/constrained changes without a default still need a
    real migration and are deliberately not handled there.

    ``Run.run_ref`` (TASK-15) is the notable SQLite case: it is NOT NULL in the
    model with a Python ``default_factory``, but SQLite cannot ALTER-add a NOT
    NULL column without a constant default (and has no ``nanoid()`` SQL). The
    hook therefore adds it as **nullable**, leaving the Python default to fill
    every new insert; an optional offline backfill normalizes pre-existing
    NULL rows (see TASK-15 docs).
    """
    if engine.url.get_backend_name() == "postgresql":
        await _init_postgres(engine)
        return
    # Imported here so every model is registered in SQLModel.metadata before
    # create_all runs, without a package-level import cycle.
    from metatracer.db import models

    async with engine.begin() as connection:
        await connection.run_sync(models.SQLModel.metadata.create_all)
        await connection.run_sync(_add_missing_columns, models.SQLModel.metadata)
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_run_started_at_id "
            "ON run (started_at DESC, id DESC)"
        )
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_finding_triage_status ON finding (triage_status)"
        )
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_finding_finding_type ON finding (finding_type)"
        )
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_finding_created_at_id "
            "ON finding (created_at DESC, id DESC)"
        )
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_raw_metadata_item_namespace "
            "ON raw_metadata_item (namespace)"
        )
        await connection.exec_driver_sql(
            "INSERT OR IGNORE INTO concurrency_gate (id) VALUES (1)"
        )


async def _init_postgres(engine: AsyncEngine) -> None:
    """Postgres bootstrap: pgvector extension, then Alembic to head.

    The extension is created here (not inside a migration) so it stays
    idempotent and runs before any ``vector`` column can exist. The Alembic
    command runs in a worker thread because Alembic's async template drives
    its own event loop with ``asyncio.run`` — there is no running loop in a
    worker thread, while ``init_db`` is always awaited inside one.
    """
    async with engine.begin() as connection:
        await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    # NOTE: str(engine.url) MASKS the password ("***") in SQLAlchemy 2.x and
    # would hand Alembic an invalid URL; render_as_string(hide_password=False)
    # is the correct way to rebuild the connectable URL.
    await asyncio.to_thread(_run_migrations, engine.url.render_as_string(hide_password=False))


def _run_migrations(database_url: str) -> None:
    """Run the packaged Alembic migrations to head (sync context)."""
    command.upgrade(_alembic_config(database_url), "head")


def _alembic_config(database_url: str) -> AlembicConfig:
    """Programmatic Alembic config pointing at the packaged migrations."""
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _add_missing_columns(sync_connection: Any, metadata: Any) -> None:
    """Add missing columns: nullable ones, plus NOT NULL with a Python default.

    A missing **nullable** column is added directly (standard ALTER). A missing
    **NOT NULL** column with a ``default_factory`` (TASK-15 ``Run.run_ref``)
    needs a constant server-side default for the ALTER on a non-empty table;
    SQLite has no nanoid() SQL function, so instead the column is added as a
    **nullable** column here — the Python ``default_factory`` covers every new
    insert, and an optional offline backfill (see the task docs) can normalize
    the pre-existing NULL values. Keeping existing databases upgradeable
    without Alembic is the documented posture (TASK-13); a NOT NULL column
    without any default is skipped entirely.
    """
    inspector = inspect(sync_connection)
    dialect = sync_connection.dialect
    for table in metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or column.primary_key:
                continue
            server_default = _constant_server_default(column)
            if not column.nullable and column.default is None and server_default is None:
                continue
            column_type = column.type.compile(dialect=dialect)
            ddl = (
                f"ALTER TABLE {quote(dialect, table.name)} "
                f"ADD COLUMN {quote(dialect, column.name)} {column_type}"
            )
            if server_default is not None:
                # A constant default lets SQLite add a NOT NULL column to a
                # non-empty table (TASK-35 Finding.triage_status).
                literal = server_default.replace("'", "''")
                not_null = "" if column.nullable else " NOT NULL"
                ddl += f"{not_null} DEFAULT '{literal}'"
            sync_connection.exec_driver_sql(ddl)


def _constant_server_default(column: Any) -> str | None:
    """The string literal of a constant ``server_default``, else None."""
    default = column.server_default
    arg = getattr(default, "arg", None)
    if isinstance(arg, str):
        return arg
    text = getattr(arg, "text", None)
    return text if isinstance(text, str) else None


def quote(dialect: Any, identifier: str) -> str:
    """Dialect-aware identifier quoting for the DDL above."""
    return dialect.identifier_preparer.quote(identifier)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory for the repositories; committed objects stay usable."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
