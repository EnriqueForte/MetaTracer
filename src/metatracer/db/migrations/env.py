"""Alembic environment for the packaged, programmatic migrations (TASK-23).

This project never ships an ``alembic.ini``: :mod:`metatracer.db.engine` builds
the Alembic ``Config`` programmatically (script location + ``sqlalchemy.url``),
so the standard ``alembic upgrade`` CLI is not the supported entry point. The
environment honors the injected URL and works with an async engine (asyncpg),
reusing the project's own declarative metadata for autogenerate diffs.
"""

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# The models are the single source of truth: importing them registers every
# table in SQLModel.metadata (no package-level import cycle concerns here —
# the migrations package is only scanned by Alembic at runtime).
from metatracer.db import models  # noqa: F401 (import for metadata side effect)

config = context.config

target_metadata = models.SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DBAPI connection (documenting only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Drive the migrations over an async engine (asyncpg)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio_run(run_async_migrations())


def asyncio_run(coro):  # noqa: ANN001, ANN201 - tiny shim, see note below
    """``asyncio.run`` with a fallback for reentrant loop edge cases.

    The migration runner always executes inside ``asyncio.to_thread`` (no
    running loop in that thread), so the plain call is the normal path. The
    ``Runner`` fallback keeps the helper robust if a future caller drives the
    config from a loop-owning thread.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with asyncio.Runner() as runner:  # Python >= 3.11 (guaranteed by requires-python)
        return runner.run(coro)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
