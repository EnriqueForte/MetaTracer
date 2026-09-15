"""Portable scope import/export (TASK-19, v2.2).

TASK-10 created the persistent ``Scope`` entity (a named, reusable set of
authorized domains) with a CRUD API, but an operator can only add scopes by
hand, one at a time. The v2.2 *integrations* phase makes scopes **portable**:
a JSON file can carry one or more scopes — e.g. the domain list a client or
bounty program hands over, or a backup of an operator's scope management to
move between machines.

What leaves/enters the machine (and nothing else):

- For each scope: ``name`` (unique, case-insensitive), ``description``
  (nullable), ``domains`` (a non-empty list, normalized with
  ``normalize_host`` — lowercase, no scheme/port/path, ``*.`` wildcards kept).
- Deliberately absent: ids, timestamps, runs, assets, findings, raw metadata,
  bytes. ``format_version`` must be exactly ``1``.

Safety posture (invariant rules):

- **Zero file bytes**: the file is UTF-8 JSON of text only.
- **No network**: import/export are local file operations.
- **The import never invents**: names and every domain are validated with the
  same rules as ``ScopeCreate`` (TASK-10); invalid entries raise
  ``ValueError`` (never reassigned, never guessed).
- **Strict contract**: unknown fields anywhere in the file are rejected with a
  ``ValueError`` — a hostile or malformed payload can never smuggle extra keys
  (e.g. ids, flags) past validation.
- **Idempotent and non-destructive**: importing the same file twice never
  duplicates (a scope whose name already exists is skipped) and never deletes
  or overwrites an existing scope.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.safety.scope import normalize_host
from metatracer.db.models import Scope
from metatracer.db.repositories import ScopeRepository

logger = logging.getLogger("metatracer.scopes.portable")

FORMAT_VERSION = 1

# The only keys the portable contract accepts. Anything else is rejected
# (hardening): a scope import must never silently carry unknown payload.
_ROOT_KEYS = frozenset({"format_version", "exported_at", "scopes"})
_ENTRY_KEYS = frozenset({"name", "description", "domains"})


@dataclass(slots=True, frozen=True)
class ScopeEntry:
    """One validated scope from a portable file (domains already normalized)."""

    name: str
    description: str | None
    domains: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ScopeImportResult:
    """Outcome of a scope-file import (idempotent, non-destructive)."""

    imported: int
    skipped: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write the portable file (UTF-8, indented, text only)."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_name(raw: object, index: int) -> str:
    """Validate one scope name; raises ``ValueError`` on anything invalid."""
    if not isinstance(raw, str):
        raise ValueError(f"entry {index}: 'name' must be a string")
    name = raw.strip()
    if not 1 <= len(name) <= 64:
        raise ValueError(f"entry {index}: 'name' must be 1..64 characters")
    return name


def _parse_domains(raw: object, index: int) -> tuple[str, ...]:
    """Normalize a scope's domains; empty/invalid entries degrade to [].

    Raises ``ValueError`` if ``domains`` is missing, not a list, or leaves no
    valid host after normalization (an empty scope audits nothing).
    """
    if not isinstance(raw, list):
        raise ValueError(f"entry {index}: 'domains' must be a list of strings")
    cleaned: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            # Non-text entries are suspicious: reject rather than silently pass.
            raise ValueError(f"entry {index}: 'domains' must contain only strings")
        host = normalize_host(value)
        if host:
            cleaned.append(host)
    if not cleaned:
        raise ValueError(f"entry {index}: no valid domains after normalization")
    return tuple(cleaned)


def _entry_from_dict(raw: object, index: int) -> ScopeEntry:
    """Validate one scope entry; never reassigns and never invents values."""
    if not isinstance(raw, dict):
        raise ValueError(f"entry {index}: must be an object")
    extra = set(raw) - _ENTRY_KEYS
    if extra:
        raise ValueError(
            f"entry {index}: unexpected field(s) {sorted(extra)}; "
            f"allowed: {sorted(_ENTRY_KEYS)}"
        )
    name = _parse_name(raw.get("name"), index)
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(f"entry {index}: 'description' must be text or null")
    domains = _parse_domains(raw.get("domains"), index)
    return ScopeEntry(name=name, description=description, domains=domains)


def parse_scopes_file(source: Path) -> list[ScopeEntry]:
    """Read and validate a portable scopes JSON file.

    Raises ``ValueError`` with a descriptive message on a malformed file,
    unknown ``format_version``, invalid entry or duplicate name within the
    same file. Returns the validated entries (domains normalized).
    """
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read scopes file {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("scopes file must be a JSON object")
    extra = set(raw) - _ROOT_KEYS
    if extra:
        raise ValueError(
            f"unexpected top-level field(s) {sorted(extra)}; "
            f"allowed: {sorted(_ROOT_KEYS)}"
        )
    if raw.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"unsupported format_version {raw.get('format_version')!r}; "
            f"expected {FORMAT_VERSION}"
        )
    entries_raw = raw.get("scopes")
    if not isinstance(entries_raw, list):
        raise ValueError("scopes file must contain a 'scopes' list")
    entries = [_entry_from_dict(raw, i) for i, raw in enumerate(entries_raw)]
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        key = entry.name.lower()
        if key in seen:
            raise ValueError(f"entry {index}: duplicate name {entry.name!r}")
        seen.add(key)
    return entries


async def _scope_exists(session: AsyncSession, name: str) -> bool:
    """True if a scope with this (case-insensitive) name is persisted."""
    return await ScopeRepository(session).get_by_name(name) is not None


async def import_scopes(
    session_factory: async_sessionmaker[AsyncSession],
    source: Path,
) -> ScopeImportResult:
    """Import a portable scopes file; returns created/skipped counts.

    Idempotent by scope name (case-insensitive): existing scopes are skipped,
    nothing is overwritten or deleted. Invalid entries abort the parse (before
    any insert), so a malformed file never leaves a partial import.
    """
    entries = parse_scopes_file(source)
    imported = 0
    skipped = 0
    async with session_factory() as session:
        for entry in entries:
            if await _scope_exists(session, entry.name):
                skipped += 1
                continue
            await ScopeRepository(session).create(
                Scope(
                    name=entry.name,
                    description=entry.description,
                    domains=json.dumps(list(entry.domains)),
                )
            )
            imported += 1
    logger.info(
        "imported %d scopes, skipped %d from %s", imported, skipped, source
    )
    return ScopeImportResult(imported=imported, skipped=skipped)


async def export_scopes(
    session_factory: async_sessionmaker[AsyncSession],
    dest: Path,
) -> int:
    """Write all persisted scopes to a portable JSON file; returns the count.

    The complement of :func:`import_scopes` (round-trip portable). Only the
    contract fields leave the machine — never ids or timestamps.
    """
    async with session_factory() as session:
        scopes = await ScopeRepository(session).list_all()
        entries: list[dict[str, object]] = []
        for scope in scopes:
            try:
                domains = json.loads(scope.domains)
            except json.JSONDecodeError:  # pragma: no cover - corrupt row
                domains = []
            entries.append(
                {
                    "name": scope.name,
                    "description": scope.description,
                    "domains": [str(d) for d in domains],
                }
            )
    payload: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "exported_at": _utc_now().isoformat(),
        "scopes": entries,
    }
    _write_json(dest, payload)
    logger.info("exported %d scopes to %s", len(entries), dest)
    return len(entries)