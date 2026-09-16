"""Multi-scope resolution in the orchestrator (TASK-21, v2.4).

A run launched with ``scope_ids`` persists the deduplicated union in
``Run.allowed_scope`` (snapshot, never a FK), an unknown id aborts with
``ScopeNotFoundError`` before any row, and the ScanRequest contract rejects
mixed/empty scope sources. Scopes are created directly through the
repo — resolution itself is local-only (zero HTTP).
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.core.exceptions import ScopeNotFoundError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Scope
from metatracer.db.repositories import RunRepository, ScopeRepository
from metatracer.services.orchestrator import ScanOrchestratorService, ScanRequest


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/multi-scope-test.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


async def _create_scope(session_factory, name: str, domains: list[str]) -> Scope:
    async with session_factory() as session:
        return await ScopeRepository(session).create(
            Scope(name=name, description="test", domains=json.dumps(domains))
        )


async def test_scope_ids_union_is_deduplicated_on_run(session_factory, tmp_path) -> None:
    """The run owns a snapshot of the union, deduplicated and stable-ordered."""
    scope_a = await _create_scope(session_factory, "a", ["target.com", "static.target.com"])
    scope_b = await _create_scope(session_factory, "b", ["static.target.com", "api.target.com"])

    request = ScanRequest(
        targets=["http://target.com/doc.pdf"],
        scope_ids=[scope_a.id, scope_b.id],
        scope_confirmed=True,
    )
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    run = await orchestrator._create_run(request)

    assert json.loads(run.allowed_scope) == [
        "target.com",
        "static.target.com",
        "api.target.com",
    ]
    # The snapshot survives deleting the scopes after the run.
    async with session_factory() as session:
        await ScopeRepository(session).delete(scope_a.id)
        await ScopeRepository(session).delete(scope_b.id)
    async with session_factory() as session:
        persisted = await RunRepository(session).get(run.id)
    assert persisted is not None
    assert json.loads(persisted.allowed_scope) == [
        "target.com",
        "static.target.com",
        "api.target.com",
    ]


async def test_scope_ids_unknown_id_raises_before_any_row(session_factory, tmp_path) -> None:
    """An unknown id in the union aborts resolution; no Run row is written."""
    scope_a = await _create_scope(session_factory, "a", ["target.com"])
    request = ScanRequest(
        targets=["http://target.com/doc.pdf"],
        scope_ids=[scope_a.id, "00000000-0000-0000-0000-000000000000"],
        scope_confirmed=True,
    )
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    with pytest.raises(ScopeNotFoundError):
        await orchestrator._create_run(request)

    async with session_factory() as session:
        assert await RunRepository(session).list_all() == []


async def test_scan_request_scope_id_normalizes_to_scope_ids() -> None:
    """The v2.0 wire contract (scope_id) keeps working as a 1-element union."""
    request = ScanRequest(
        targets=["http://target.com/doc.pdf"],
        scope_id="11111111-1111-1111-1111-111111111111",
        scope_confirmed=True,
    )
    assert request.scope_id is None
    assert request.scope_ids == ["11111111-1111-1111-1111-111111111111"]


def test_scan_request_rejects_mixed_scope_sources() -> None:
    """scope_domains + scope_ids together are ambiguous (contract 21.1)."""
    with pytest.raises(ValidationError):
        ScanRequest(
            targets=["http://target.com/doc.pdf"],
            scope_domains=["target.com"],
            scope_ids=["11111111-1111-1111-1111-111111111111"],
            scope_confirmed=True,
        )


def test_scan_request_rejects_empty_scope_ids() -> None:
    """An empty union is not an explicit scope source."""
    with pytest.raises(ValidationError):
        ScanRequest(
            targets=["http://target.com/doc.pdf"],
            scope_ids=[],
            scope_confirmed=True,
        )
    with pytest.raises(ValidationError):
        ScanRequest(
            targets=["http://target.com/doc.pdf"],
            scope_ids=["   "],
            scope_confirmed=True,
        )


def test_scan_request_still_requires_some_scope_source() -> None:
    """No scope source at all: the scope is never inferred (rule 1)."""
    with pytest.raises(ValidationError):
        ScanRequest(targets=["http://target.com/doc.pdf"], scope_confirmed=True)