"""KnowledgeIndex + KnowledgeRetriever: light RAG over historical findings (TASK-14, v2.1+).

Since TASK-23 (platform v3.0, Eje B) the retrieval layer dispatches by
backend: SQLite keeps this module's FTS5 index; PostgreSQL runs the pgvector
index in :mod:`metatracer.agents.knowledge_pg` behind the same
:class:`KnowledgeRetriever` interface (zero changes in AgentPipeline).

The agent layer (TASK-05) analyses one finding with only the current run's
payload plus same-type feedback examples (TASK-13). When an operator has
worked the same kind of target before, that learning lives in the rows of
``finding`` / ``finding_feedback`` of past runs but never reaches the prompt:
every run starts from zero.

This module builds a **full-text index (SQLite FTS5)** over historical
findings and retrieves the most similar ones (lexical match with the current
finding) to inject them as **external, non-authoritative context** into the
agent analysis:

- the current finding stays the source of truth; the retrieved rows are
  "this was seen before" hints, never evidence of the current finding;
- **zero new dependencies** (FTS5 ships inside SQLite) and **zero DB
  migration** — the index is a virtual table, rebuilt on demand over the
  existing tables;
- the retrieval layer sits behind :class:`KnowledgeRetriever` so a future
  PostgreSQL + pgvector switch replaces only this implementation.

Safety posture (invariant rules):

- **No network**: nothing here touches the network, reads files, or resolves
  hosts. Payload text in, ranked rows out.
- **Zero bytes**: the index stores only the short, sanitized snippets already
  present in the ``finding`` table (``evidence_snippet``, truncated to a cap
  before insertion).
- **No LLM text from other runs**: the snippets of *other* findings (e.g. GPS
  coordinates) travel to the agent prompt only for the *same operator* on
  their machine; they are never logged and never exported.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

# TASK-23: the dataclass moved to knowledge_pg (shared by both backends);
# re-exported here so every existing import path keeps working.
from metatracer.agents.knowledge_pg import (  # noqa: F401
    PgVectorKnowledgeIndex,
    RetrievedEvidence,
    pgvector_available,
)
from metatracer.agents.knowledge_pg import (
    _parse_created_at as _pg_parse_created_at,  # noqa: F401
)
from metatracer.db.models import Finding, FindingType, Severity

logger = logging.getLogger("metatracer.agents.knowledge")

# The virtual FTS5 table name inside the same SQLite file. The table is a
# derived artifact, never a source of truth: ``rebuild`` drops and recreates
# it. It is declared here (not in models.py) because it is not an ORM model.
_FTS_TABLE = "knowledge_fts"
# Cap the indexed snippet so the index never grows unbounded (the raw
# evidence_snippet is already ~150 chars, but defense in depth).
_INDEX_SNIPPET_MAX = 300
# How many historical findings to load for the index per rebuild.
_INDEX_SEED_LIMIT = 1000


@dataclass(slots=True)
class KnowledgeIndex:
    """FTS5 full-text index over historical findings (TASK-14).

    ``engine`` is the same async engine the app uses (so the virtual table
    lives in the same SQLite file, honoring ``PRAGMA foreign_keys`` and the
    single-writer discipline); ``session_factory`` provides short-lived ORM
    sessions for seeding. The index is a **derived artifact** — it can be
    dropped and rebuilt at any time and is never a source of truth.

    Rebuilds are guarded by an instance lock because SQLite has a single
    writer and the agent phase is sequential anyway (README known trap 6).
    """

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _ready: bool = field(default=False, init=False, repr=False)

    async def rebuild(self) -> None:
        """(Re)create the virtual FTS5 table and seed it from persisted findings.

        Idempotent: any previous index state is dropped first. Safe to call
        repeatedly — the body indexes the historical findings present at call
        time, so a new run reindexes because findings accumulate.
        """
        async with self._lock:
            async with self.engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {_FTS_TABLE}"))
                await conn.execute(
                    text(
                        f"CREATE VIRTUAL TABLE {_FTS_TABLE} USING fts5("
                        "finding_id UNINDEXED, run_id UNINDEXED, "
                        "finding_type UNINDEXED, evidence_snippet, "
                        "field_source, "
                        "severity UNINDEXED, title UNINDEXED, created_at UNINDEXED"
                        ")"
                    )
                )
            async with self.session_factory() as session:
                rows = await _load_seed_findings(session)
            async with self.engine.begin() as conn:
                for row in rows:
                    await conn.execute(
                        text(
                            f"INSERT INTO {_FTS_TABLE} "
                            "(finding_id, run_id, finding_type, evidence_snippet, "
                            "field_source, severity, title, created_at) VALUES "
                            "(:finding_id, :run_id, :finding_type, :evidence_snippet, "
                            ":field_source, :severity, :title, :created_at)"
                        ),
                        {
                            "finding_id": row.id,
                            "run_id": row.run_id,
                            "finding_type": str(row.finding_type),
                            "evidence_snippet": row.evidence_snippet[:_INDEX_SNIPPET_MAX],
                            "field_source": row.field_source[:_INDEX_SNIPPET_MAX],
                            "severity": str(row.severity) if row.severity else None,
                            "title": row.title,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                        },
                    )
            self._ready = True
            logger.info("knowledge index rebuilt with %d historical findings", len(rows))

    async def search(
        self,
        query: str,
        *,
        finding_type: FindingType | None = None,
        exclude_finding_id: str | None = None,
        limit: int = 5,
    ) -> list[RetrievedEvidence]:
        """Return the top-``limit`` ranked rows matching ``query``.

        The query is sanitized into FTS5-safe phrase terms (alphanumeric
        tokens joined with AND) because evidence snippets routinely contain
        FTS5 operator characters — ``.`` in coordinates, ``/`` in paths,
        ``@`` in emails — that would otherwise cause a syntax error.
        ``finding_type`` and ``exclude_finding_id`` are post-filters because
        FTS5 column filters would force per-column indexes; the volume here
        is small (~1k rows).
        """
        if not self._ready:
            await self.rebuild()
        query = query.strip()
        if not query:
            return []
        fts_query = _fts_safe_query(query)
        if not fts_query:
            return []
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT finding_id, run_id, finding_type, evidence_snippet, "
                    "severity, title, created_at, bm25(knowledge_fts) AS score "
                    "FROM knowledge_fts WHERE knowledge_fts MATCH :q "
                    "ORDER BY bm25(knowledge_fts) LIMIT :limit"
                ),
                {"q": fts_query, "limit": limit * 4},  # headroom for post-filters
            )
            results = [dict(row) for row in result.mappings()]
        rows: list[RetrievedEvidence] = []
        for raw in results:
            if exclude_finding_id is not None and raw["finding_id"] == exclude_finding_id:
                continue
            if finding_type is not None and raw["finding_type"] != str(finding_type):
                continue
            ftype = FindingType(raw["finding_type"])
            rows.append(
                RetrievedEvidence(
                    finding_id=raw["finding_id"],
                    run_id=raw["run_id"],
                    finding_type=ftype,
                    evidence_snippet=raw["evidence_snippet"] or "",
                    severity=Severity(raw["severity"]) if raw["severity"] else None,
                    title=raw["title"],
                    created_at=(
                        datetime.fromisoformat(raw["created_at"])
                        if isinstance(raw["created_at"], str)
                        else raw["created_at"]
                    ),
                    score=float(raw["score"]),
                )
            )
            if len(rows) >= limit:
                break
        return rows


async def _load_seed_findings(session: AsyncSession) -> list[Finding]:
    """Load a bounded seed of findings for the index (newest-first)."""
    result = await session.exec(
        select(Finding).order_by(Finding.created_at.desc()).limit(_INDEX_SEED_LIMIT)
    )
    return list(result.scalars()) or []


_FTS_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _fts_safe_query(raw: str, *, max_terms: int = 12) -> str:
    """Turn free text into an FTS5-safe AND-of-phrases MATCH expression.

    Evidence snippets contain FTS5 operators (``.`` ``/`` ``@`` etc.); a raw
    MATCH would raise `sqlite3.OperationalError: fts5: syntax error`. Tokenize
    into alphanumeric terms (FTS5's default unicode61 tokenizer splits on
    ``.`` ``/`` ``-`` ``@`` exactly like this regex, so ``41.6521`` becomes
    the two index tokens ``41`` and ``6521`` — matching the way the same
    snippet was indexed) and join with AND. Dedupes and caps the term count
    to bound the query size.
    """
    seen: list[str] = []
    for term in _FTS_TOKEN.findall(raw):
        if len(seen) >= max_terms:
            break
        if term not in seen:
            seen.append(term)
    if not seen:
        return ""
    return " AND ".join(f'"{term}"' for term in seen)


class KnowledgeRetriever:
    """Retrieves historical context for one finding (light RAG, TASK-14).

    ``retrieve`` builds the query from the **closed payload fields only**
    (evidence snippet + finding type + field source) — never from free-text
    operator input and never touching the network. An empty index is a no-op
    (returns ``[]``), keeping the agent phase byte-identical to v2.1 without
    RAG.

    Backend dispatch (TASK-23, Eje B): on PostgreSQL the retrieval runs on
    :class:`PgVectorKnowledgeIndex` (pgvector similarity); on SQLite it keeps
    the FTS5 :class:`KnowledgeIndex`. The interface (``retrieve(payload) ->
    [RetrievedEvidence]``) and the AgentPipeline contract are unchanged.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        limit: int = 5,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._limit = limit
        self._backend: KnowledgeIndex | PgVectorKnowledgeIndex | None = None

    async def retrieve(
        self,
        payload: dict[str, str],
        *,
        exclude_finding_id: str | None = None,
    ) -> list[RetrievedEvidence]:
        """Best-match historical findings for a closed payload.

        The query is built from the snippet only. ``field_source`` is
        deliberately NOT added to the MATCH: imported ports carry
        ``field_source='kb-import'`` (TASK-17), while native rows carry
        e.g. ``EXIF:GPSInfo``, so requiring it would make imported precedents
        unrecoverable. The snippet is the portable, source-independent key;
        ``finding_type`` remains a post-filter.
        """
        snippet = (payload.get("evidence_snippet") or "").strip()
        ftype_raw = payload.get("finding_type")

        if not snippet:
            return []
        ftype = FindingType(ftype_raw) if ftype_raw in FindingType.__members__ else None
        backend = await self._get_backend()
        return await backend.search(
            snippet,
            finding_type=ftype,
            exclude_finding_id=exclude_finding_id,
            limit=self._limit,
        )

    async def _get_backend(self) -> KnowledgeIndex | PgVectorKnowledgeIndex:
        """Lazily resolve the backend from the engine's dialect (once).

        PostgreSQL without the pgvector extension degrades to a no-op
        retriever (always ``[]``): the agent phase loses historical context
        but never crashes (inviolable rule 5).
        """
        if self._backend is not None:
            return self._backend
        if self._engine.url.get_backend_name() == "postgresql":
            if await pgvector_available(self._engine):
                self._backend = PgVectorKnowledgeIndex(self._engine, self._session_factory)
            else:
                logger.warning(
                    "PostgreSQL detected without the pgvector extension; "
                    "knowledge retrieval disabled (agent phase continues without "
                    "historical context)"
                )
                self._backend = _NoopBackend()
        else:
            self._backend = KnowledgeIndex(self._engine, self._session_factory)
        return self._backend


class _NoopBackend:
    """Stand-in backend for Postgres-without-pgvector: always returns []."""

    async def search(
        self,
        query: str,
        *,
        finding_type: FindingType | None = None,
        exclude_finding_id: str | None = None,
        limit: int = 5,
    ) -> list[RetrievedEvidence]:
        return []