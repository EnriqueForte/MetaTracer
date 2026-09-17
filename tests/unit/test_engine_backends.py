"""TASK-23 (Eje B): engine backend dispatch + URL validation (unit, no DB)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.db.engine import POSTGRES_DRIVER, create_db_engine


def test_sqlite_url_still_creates_engine(tmp_path) -> None:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    assert engine.url.get_backend_name() == "sqlite"
    assert engine.url.drivername == "sqlite+aiosqlite"


def test_postgres_asyncpg_url_creates_engine() -> None:
    engine = create_db_engine("postgresql+asyncpg://user:secret@localhost:5432/metatracer")
    assert engine.url.get_backend_name() == "postgresql"
    assert engine.url.drivername == POSTGRES_DRIVER


def test_bare_postgres_url_is_rejected() -> None:
    # A bare postgresql:// URL would resolve to the (uninstalled, sync)
    # psycopg2 dialect: fail fast with a clear error instead.
    with pytest.raises(ValueError, match="asyncpg driver"):
        create_db_engine("postgresql://user:secret@localhost:5432/metatracer")


def test_unsupported_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported database backend"):
        create_db_engine("mysql+aiomysql://user@localhost/db")


def test_other_async_drivers_are_rejected() -> None:
    with pytest.raises(ValueError, match="asyncpg driver"):
        create_db_engine("postgresql+psycopg://user:secret@localhost:5432/metatracer")


def test_engine_url_renders_real_password() -> None:
    # Regression guard for the masked-password bug found in TASK-23:
    # str(engine.url) hides the secret; render_as_string must not.
    engine = create_db_engine("postgresql+asyncpg://user:secret@localhost:5432/metatracer")
    rendered = engine.url.render_as_string(hide_password=False)
    assert "secret" in rendered
    assert isinstance(engine, AsyncEngine)
