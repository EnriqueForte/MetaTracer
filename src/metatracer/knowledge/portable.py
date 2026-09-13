"""Portable knowledge-base export/import (TASK-17, v2.2).

TASK-14 built the light-RAG FTS5 index over the *local* operator database:
that history ("this was seen before, and it was severe") stays tied to one
SQLite file. The portable KB moves the **historical precedent corpus** — the
same fields the RAG indexes — to a JSON file the operator owns, and can
re-import it into another database to repopulate the index without carrying
runs, assets, raw metadata or agent logs.

What leaves the machine (and nothing else):

- ``finding_id`` (stable, for idempotent import), ``finding_type``,
  ``evidence_snippet`` (already sanitized, ~150 chars), ``severity``
  (nullable), ``title`` (nullable), ``created_at``.
- Deliberately absent: ``run_id``, ``asset_id``, ``field_source``,
  ``dedup_signature``, URLs, raw metadata, file bytes.

Safety posture (invariant rules):

- **Zero file bytes**: only sanitized text snippets are ever written.
- **No network**: export/import are local file operations, like the RAG.
- **The import never invents**: ``finding_type``/``severity`` are validated
  against the closed enums and rejected on mismatch (never reassigned).
- **The import never deletes** and is idempotent by ``finding_id``: a re-run
  simply skips rows that already exist. It creates a fresh shadow run/asset
  per entry so foreign keys hold without dragging the origin run.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    Run,
    RunStatus,
    Severity,
)

logger = logging.getLogger("metatracer.knowledge.portable")

FORMAT_VERSION = 1
KB_NAME = "MetaTracer knowledge base export"
# Same seed cap as KnowledgeIndex.rebuild (TASK-14): newest findings first.
_DEFAULT_LIMIT = 1000
# Field source/identity assigned to imported rows: provenance of the import.
_IMPORT_FIELD_SOURCE = "kb-import"
#: evidence_snippet is already ~150 chars by contract; defensive cap at import/export.
_SNIPPET_MAX = 300


@dataclass(slots=True)
class KBEntry:
    """One portable precedent, mirroring RetrievalEvidence (TASK-14.14.1).

    ``finding_id`` is stable across exports so a re-import of the same file
    is idempotent; it is never the origin run's row id on the target side
    (a fresh shadow run/asset is created per entry on import).
    """

    finding_id: str
    finding_type: FindingType
    evidence_snippet: str
    severity: Severity | None
    title: str | None
    created_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write the portable file (UTF-8, indented, ASCII-safe text)."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, object]:
    """Read and parse the portable file; raises ``ValueError`` on bad JSON."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read knowledge-base file {path}: {exc}" ) from exc
    if not isinstance(raw, dict):
        raise ValueError("knowledge-base file must be a JSON object")
    return raw


def _entry_from_dict(raw: dict[str, object], index: int) -> KBEntry:
    """Validate one entry against the closed contracts; never reassigns."""
    ftype_raw = raw.get("finding_type")
    if ftype_raw not in FindingType.__members__:
        raise ValueError(
            f"invalid entry {index}: unknown finding_type {ftype_raw!r}"
        )
    sev_raw = raw.get("severity")
    if sev_raw is not None and sev_raw not in Severity.__members__:
        raise ValueError(f"invalid entry {index}: unknown severity {sev_raw!r}")
    if not isinstance(raw.get("evidence_snippet"), str) or not raw["evidence_snippet"].strip():
        raise ValueError(f"invalid entry {index}: evidence_snippet must be non-empty text")
    ftype = FindingType(ftype_raw)
    severity = Severity(sev_raw) if sev_raw is not None else None
    title = raw.get("title")
    if title is not None and not isinstance(title, str):
        raise ValueError(f"invalid entry {index}: title must be text or null")
    created_raw = raw.get("created_at")
    created_at: datetime | None = None
    if created_raw is not None:
        try:
            created_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"invalid entry {index}: created_at must be ISO-8601, got {created_raw!r}"
            ) from exc
    finding_id = raw.get("finding_id")
    if not isinstance(finding_id, str) or not finding_id:
        raise ValueError(f"invalid entry {index}: finding_id must be a non-empty string")
    return KBEntry(
        finding_id=finding_id,
        finding_type=ftype,
        evidence_snippet=str(raw["evidence_snippet"])[:_SNIPPET_MAX],
        severity=severity,
        title=title,
        created_at=created_at,
    )


def serialize_entry(entry: KBEntry) -> dict[str, object]:
    """Turn a KBEntry into the portable wire dict (fixed key set)."""
    return {
        "finding_type": str(entry.finding_type),
        "evidence_snippet": entry.evidence_snippet,
        "severity": str(entry.severity) if entry.severity else None,
        "title": entry.title,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


async def _load_seed_findings(
    session: AsyncSession, *, limit: int
) -> list[Finding]:
    """Newest-first findings, same seed as KnowledgeIndex.rebuild (TASK-14)."""
    result = await session.exec(
        select(Finding).order_by(Finding.created_at.desc()).limit(limit)
    )
    return list(result.scalars()) or []


async def export_kb(
    session_factory: async_sessionmaker[AsyncSession],
    dest: Path,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> int:
    """Write the newest ``limit`` findings as a portable KB JSON file.

    Returns the number of entries written (0 is valid: ``entries: []``).
    """
    async with session_factory() as session:
        findings = await _load_seed_findings(session, limit=limit)
        entries = [
            {
                "finding_id": finding.id,
                **serialize_entry(
                    KBEntry(
                        finding_id=finding.id,
                        finding_type=finding.finding_type,
                        evidence_snippet=finding.evidence_snippet,
                        severity=finding.severity,
                        title=finding.title,
                        created_at=finding.created_at,
                    )
                ),
            }
            for finding in findings
        ]
    payload: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "kb_name": KB_NAME,
        "exported_at": _utc_now().isoformat(),
        "entries": entries,
    }
    _write_json(dest, payload)
    logger.info("exported %d knowledge entries to %s", len(entries), dest)
    return len(entries)


async def _imported_signature_exists(session: AsyncSession, original_id: str) -> bool:
    """True if this original export row was already imported.

    The import gives each row a FRESH finding id (never the origin's, to avoid
    colliding with an existing row), so idempotency is tracked on the original
    id embedded in the dedup signature — not on the primary key.
    """
    result = await session.exec(
        select(Finding).where(Finding.dedup_signature == f"kb-import:{original_id}")
    )
    return result.first() is not None


async def import_kb(
    session_factory: async_sessionmaker[AsyncSession],
    source: Path,
) -> int:
    """Import a portable KB file; returns the number of rows inserted.

    Idempotent by the ORIGINAL finding id (embedded in each imported row's
    dedup signature): existing imports are skipped, nothing is deleted. Each
    imported row gets a fresh finding id + shadow run/asset so foreign keys
    hold without dragging the origin run (invariant: the export carries no
    run/asset provenance and re-using the origin id would collide with a
    present row).
    """
    payload = _read_json(source)
    if payload.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"unsupported format_version {payload.get('format_version')!r}; "
            f"expected {FORMAT_VERSION}"
        )
    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, list):
        raise ValueError("knowledge-base file must contain an 'entries' list")
    entries = [_entry_from_dict(raw, i) for i, raw in enumerate(entries_raw)]

    inserted = 0
    async with session_factory() as session:
        for entry in entries:
            if await _imported_signature_exists(session, entry.finding_id):
                continue  # idempotent import: this original row was imported
            shadow_run = Run(
                target_input="[]",
                allowed_scope="[]",
                scope_confirmed=False,
                status=RunStatus.completed,
            )
            session.add(shadow_run)
            await session.flush()
            shadow_asset = Asset(
                run_id=shadow_run.id,
                source_url=f"kb-import://{entry.finding_id}",
                final_url=f"kb-import://{entry.finding_id}",
                content_type="application/x-metatracer-kb-import",
                file_hash_sha256=f"kb-import-{entry.finding_id}",
                file_size_bytes=0,
                extraction_status=ExtractionStatus.ok,
            )
            session.add(shadow_asset)
            await session.flush()
            finding = Finding(
                # Fresh id: never the origin's, so a present row can't collide.
                id=str(uuid.uuid4()),
                run_id=shadow_run.id,
                asset_id=shadow_asset.id,
                finding_type=entry.finding_type,
                field_source=_IMPORT_FIELD_SOURCE,
                evidence_snippet=entry.evidence_snippet,
                # The original export id is the idempotency key, embedded here.
                dedup_signature=f"kb-import:{entry.finding_id}",
                detector_method=DetectorMethod.heuristic,
                confidence=Confidence.medium,
                severity=entry.severity,
                title=entry.title,
                created_at=entry.created_at or _utc_now(),
            )
            session.add(finding)
            inserted += 1
        await session.commit()
    logger.info("imported %d knowledge entries from %s", inserted, source)
    return inserted