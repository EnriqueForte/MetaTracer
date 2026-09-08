"""Persistence of named scopes (TASK-10, v2.0): CRUD, uniqueness, ordering."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Scope
from metatracer.db.repositories import ScopeRepository


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/scope-test.db")
    yield engine
    await engine.dispose()


@pytest.fixture()
async def repo(engine: AsyncEngine) -> AsyncIterator[ScopeRepository]:
    await init_db(engine)
    async with create_session_factory(engine)() as session:
        yield ScopeRepository(session)


def _scope(name: str = "acme-2026", modules: str = '["target.com", "static.target.com"]') -> Scope:
    return Scope(name=name, description="engagement scope", domains=modules)


async def test_create_and_get(repo: ScopeRepository) -> None:
    created = await repo.create(_scope())
    assert created.id
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.name == "acme-2026"
    assert fetched.domains == '["target.com", "static.target.com"]'
    assert fetched.description == "engagement scope"


async def test_get_by_name_case_insensitive(repo: ScopeRepository) -> None:
    await repo.create(_scope("Acme-2026"))
    assert (await repo.get_by_name("acme-2026")) is not None
    assert (await repo.get_by_name("ACME-2026")) is not None
    assert (await repo.get_by_name("other")) is None


async def test_duplicate_name_violates_unique_constraint(repo: ScopeRepository) -> None:
    await repo.create(_scope("acme-2026"))
    with pytest.raises(IntegrityError):
        await repo.create(_scope("acme-2026"))


async def test_update(repo: ScopeRepository) -> None:
    created = await repo.create(_scope())
    created.domains = '["api.target.com"]'
    updated = await repo.update(created)
    assert updated.domains == '["api.target.com"]'
    assert (await repo.get(created.id)).domains == '["api.target.com"]'


async def test_delete(repo: ScopeRepository) -> None:
    created = await repo.create(_scope())
    assert await repo.delete(created.id) is True
    assert await repo.get(created.id) is None
    assert await repo.delete(created.id) is False


async def test_list_all_newest_first(repo: ScopeRepository) -> None:
    first = await repo.create(_scope("first"))
    second = await repo.create(_scope("second"))
    third = await repo.create(_scope("third"))
    names = [s.name for s in await repo.list_all()]
    assert names == ["third", "second", "first"]  # created_at.desc()
    assert [s.id for s in await repo.list_all()][:0] == []
    assert {s.id for s in await repo.list_all()} == {first.id, second.id, third.id}