"""Async engine factory and schema initialization."""

from pathlib import Path
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

# Keep in sync with the Settings.database_url default in metatracer.core.config.
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/metatracer.db"


def create_db_engine(database_url: str = DEFAULT_DATABASE_URL) -> AsyncEngine:
    """Create the async engine; on SQLite, foreign keys are enforced per connection."""
    engine = create_async_engine(database_url, echo=False)
    if engine.url.get_backend_name() == "sqlite":
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
    """Create all tables, indexes and constraints declared by the models.

    Existing tables get any *nullable* column the models declare but the
    database lacks (``ALTER TABLE ... ADD COLUMN``). That keeps a local
    database created by an earlier version usable without Alembic (out of
    scope for the MVP); non-nullable or constrained changes still need a real
    migration and are deliberately not handled here.
    """
    # Imported here so every model is registered in SQLModel.metadata before
    # create_all runs, without a package-level import cycle.
    from metatracer.db import models

    async with engine.begin() as connection:
        await connection.run_sync(models.SQLModel.metadata.create_all)
        await connection.run_sync(_add_missing_nullable_columns, models.SQLModel.metadata)


def _add_missing_nullable_columns(sync_connection: Any, metadata: Any) -> None:
    inspector = inspect(sync_connection)
    dialect = sync_connection.dialect
    for table in metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or not column.nullable or column.primary_key:
                continue
            column_type = column.type.compile(dialect=dialect)
            ddl = (
                f"ALTER TABLE {quote(dialect, table.name)} "
                f"ADD COLUMN {quote(dialect, column.name)} {column_type}"
            )
            sync_connection.exec_driver_sql(ddl)


def quote(dialect: Any, identifier: str) -> str:
    """Dialect-aware identifier quoting for the DDL above."""
    return dialect.identifier_preparer.quote(identifier)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory for the repositories; committed objects stay usable."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
