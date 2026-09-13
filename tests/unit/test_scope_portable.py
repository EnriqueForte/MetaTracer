"""Portable scopes (TASK-19, v2.2): parse/import/export contract, validation, idempotency."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Scope
from metatracer.db.repositories import ScopeRepository
from metatracer.scopes.portable import (
    FORMAT_VERSION,
    export_scopes,
    import_scopes,
    parse_scopes_file,
)


@pytest.fixture()
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/scope-portable-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


def _write(tmp_path: Path, payload: dict, name: str = "scopes.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


_VALID = {
    "format_version": 1,
    "scopes": [
        {
            "name": "acme-2026",
            "description": "Acme Corp engagement",
            "domains": ["target.com", "*.target.com", "static.Target.com:8080"],
        }
    ],
}


async def _seed(engine: AsyncEngine, name: str = "existing", domain: str = "x.com") -> Scope:
    async with create_session_factory(engine)() as session:
        return await ScopeRepository(session).create(
            Scope(name=name, description="seeded", domains=json.dumps([domain]))
        )


def test_parse_normalizes_domains(tmp_path: Path) -> None:
    entries = parse_scopes_file(_write(tmp_path, _VALID))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "acme-2026"
    assert entry.description == "Acme Corp engagement"
    # Scheme/port/path removed, wildcard kept, case lowered. The explicit
    # subdomain stays explicit: normalization strips scheme/port, not labels.
    assert entry.domains == ("target.com", "*.target.com", "static.target.com")


def test_parse_drops_empty_domains_but_keeps_valid_ones(tmp_path: Path) -> None:
    payload = {
        "format_version": 1,
        "scopes": [
            {
                "name": "mixed",
                "description": None,
                "domains": ["target.com", "   ", ".//"],
            }
        ],
    }
    entries = parse_scopes_file(_write(tmp_path, payload))
    assert entries[0].domains == ("target.com",)


def test_parse_rejects_entry_with_no_valid_domains(tmp_path: Path) -> None:
    payload = {
        "format_version": 1,
        "scopes": [{"name": "empty", "description": None, "domains": []}],
    }
    with pytest.raises(ValueError, match="no valid domains"):
        parse_scopes_file(_write(tmp_path, payload))


def test_parse_rejects_unknown_format_version(tmp_path: Path) -> None:
    payload = {"format_version": 99, "scopes": []}
    with pytest.raises(ValueError, match="format_version"):
        parse_scopes_file(_write(tmp_path, payload))


def test_parse_rejects_duplicate_name_in_same_file(tmp_path: Path) -> None:
    payload = {
        "format_version": 1,
        "scopes": [
            {"name": "Acme", "description": None, "domains": ["a.com"]},
            {"name": "acme", "description": None, "domains": ["b.com"]},
        ],
    }
    with pytest.raises(ValueError, match="duplicate name"):
        parse_scopes_file(_write(tmp_path, payload))


def test_parse_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read scopes file"):
        parse_scopes_file(path)


async def test_import_inserts_normalized_scopes(engine: AsyncEngine, tmp_path: Path) -> None:
    result = await import_scopes(create_session_factory(engine), _write(tmp_path, _VALID))
    assert result.imported == 1
    assert result.skipped == 0

    async with create_session_factory(engine)() as session:
        scopes = await ScopeRepository(session).list_all()
    assert len(scopes) == 1
    assert scopes[0].name == "acme-2026"
    assert json.loads(scopes[0].domains) == ["target.com", "*.target.com", "static.target.com"]


async def test_import_is_idempotent(engine: AsyncEngine, tmp_path: Path) -> None:
    factory = create_session_factory(engine)
    path = _write(tmp_path, _VALID)
    first = await import_scopes(factory, path)
    second = await import_scopes(factory, path)
    assert first.imported == 1
    assert second.imported == 0
    assert second.skipped == 1

    async with create_session_factory(engine)() as session:
        scopes = await ScopeRepository(session).list_all()
    assert len(scopes) == 1  # no duplicate row


async def test_import_skips_existing_scope_does_not_overwrite(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    await _seed(engine, name="acme-2026", domain="not-the-import.com")
    result = await import_scopes(create_session_factory(engine), _write(tmp_path, _VALID))
    assert result.imported == 0
    assert result.skipped == 1

    async with create_session_factory(engine)() as session:
        scope = await ScopeRepository(session).get_by_name("acme-2026")
    assert scope is not None
    # The existing row was not overwritten with the imported domains.
    assert json.loads(scope.domains) == ["not-the-import.com"]


async def test_import_aborts_on_invalid_file_leaves_nothing(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"format_version": 1, "scopes": [{"name": "ok", "domains": ["a.com"]}, '
        '{"name": "bad", "domains": []}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no valid domains"):
        await import_scopes(create_session_factory(engine), bad)

    async with create_session_factory(engine)() as session:
        scopes = await ScopeRepository(session).list_all()
    assert len(scopes) == 0  # parse failed before any insert


async def test_export_round_trips_contract(engine: AsyncEngine, tmp_path: Path) -> None:
    await _seed(engine, name="acme", domain="target.com")
    await _seed(engine, name="other", domain="api.other.com")
    dest = tmp_path / "out.json"
    n = await export_scopes(create_session_factory(engine), dest)
    assert n == 2

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["format_version"] == FORMAT_VERSION
    assert "exported_at" in payload
    scopes = payload["scopes"]
    assert len(scopes) == 2
    for entry in scopes:
        # Only the contract keys leave the machine.
        assert set(entry) == {"name", "description", "domains"}
        assert "id" not in entry
        assert "created_at" not in entry


async def test_export_empty_db_is_valid(engine: AsyncEngine, tmp_path: Path) -> None:
    dest = tmp_path / "out.json"
    n = await export_scopes(create_session_factory(engine), dest)
    assert n == 0
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["scopes"] == []