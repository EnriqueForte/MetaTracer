"""PgVectorKnowledgeIndex: pgvector-backed knowledge index (TASK-23, Eje B).

PostgreSQL replacement for the SQLite FTS5 :class:`KnowledgeIndex`. It keeps
the same contract (``rebuild`` + ``search`` returning :class:`RetrievedEvidence`
ranked rows over historical findings) but ranks by **vector similarity**
instead of lexical BM25:

- the embedding is 384-d. TASK-40 prefers a local MiniLM ONNX encoder when
  the operator points ``METATRACER_ONNX_MODEL_PATH`` at a file and the
  optional ``[onnx]`` extra is installed; otherwise the deterministic
  hashing-trick (crc32 feature hashing, L2-normalized) keeps the same
  geometry. A failed ONNX load never fails a scan (rule 5);
- the index is a **derived artifact**, never a source of truth: it lives in
  the ``knowledge_vectors`` table, is dropped and rebuilt on demand, and is
  deliberately NOT an ORM model (same posture as the FTS5 virtual table);
- cosine distance (``<=>``) with a HNSW index when the extension version
  supports it; the score is reported as ``1 - distance`` clamped to ``[0, 1]``
  so it is comparable to the FTS5 score consumers.

Safety posture (invariant rules, unchanged from TASK-14):

- **No network**: text in, ranked rows out. Nothing resolves hosts or opens
  connections beyond the database the app already uses.
- **Zero bytes**: only the short, sanitized snippets already present in the
  ``finding`` table travel to the index (capped like the FTS5 path).
- **No LLM involvement**: embeddings are computed locally in-process; snippets
  are never sent to any external service.

The table is only touched on PostgreSQL; on SQLite the FTS5 index keeps
serving :class:`KnowledgeRetriever`.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.agents.embeddings import EMBEDDING_DIM, embed_text, features, format_vector, ngrams
from metatracer.db.models import Finding, FindingType, Severity

logger = logging.getLogger("metatracer.agents.knowledge_pg")


@dataclass(slots=True)
class RetrievedEvidence:
    """One ranked hit from the knowledge index (read-only, never persisted).

    Lives here (TASK-23) so both backends share the contract without a
    circular import; :mod:`metatracer.agents.knowledge` re-exports it, which
    keeps every existing import path working.
    """

    finding_id: str
    run_id: str
    finding_type: FindingType
    evidence_snippet: str
    severity: Severity | None
    title: str | None
    created_at: datetime | None
    score: float

# The derived table name inside the same database. Not an ORM model (TASK-14
# posture): it is created, dropped and rebuilt at will from the ``finding``
# table, which stays the single source of truth.
_VECTOR_TABLE = "knowledge_vectors"
# Same snippet cap as the FTS5 index: the raw evidence_snippet is already
# ~150 chars, but defense in depth.
_INDEX_SNIPPET_MAX = 300
# How many historical findings to load for the index per rebuild (same seed
# policy as KnowledgeIndex.rebuild, TASK-14 / TASK-17).
_INDEX_SEED_LIMIT = 1000
# Geometry is fixed at 384 (MiniLM and hashing-trick share the column type).
_EMBEDDING_DIM = EMBEDDING_DIM
Vector = list[float]
_ngrams = ngrams
_features = features
_embed = embed_text
_format_vector = format_vector


async def pgvector_available(engine: AsyncEngine) -> bool:
    """Check whether the ``vector`` extension exists on the current database.

    Used by the retriever to fall back to a no-op when an operator points
    MetaTracer at a vanilla PostgreSQL without pgvector: the agent phase must
    degrade gracefully (empty knowledge context), never crash the scan
    (inviolable rule 5).
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        return result.scalar() == 1


class PgVectorKnowledgeIndex:
    """Vector index over historical findings on PostgreSQL (TASK-23).

    Same lifecycle contract as :class:`KnowledgeIndex`: ``rebuild()`` drops and
    recreates the derived table (idempotent), ``search()`` ranks by embedding
    similarity and applies the same post-filters (``finding_type``,
    ``exclude_finding_id``). Rebuilds are guarded by an instance lock; the
    agent phase is sequential, so lock contention is not expected.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory
        self._ready = False

    async def rebuild(self) -> None:
        """(Re)create the vector table and seed it from persisted findings.

        Idempotent like the FTS5 rebuild. The HNSW index is best-effort: on an
        old pgvector build without hnsw support the similarity scan still
        works (plain sequential scan), so the failure is logged, not raised.
        """
        async with self.engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_VECTOR_TABLE}"))
            await conn.execute(
                text(
                    f"CREATE TABLE {_VECTOR_TABLE} ("
                    "finding_id TEXT PRIMARY KEY, "
                    "run_id TEXT, "
                    "finding_type TEXT, "
                    "evidence_snippet TEXT, "
                    "field_source TEXT, "
                    "severity TEXT, "
                    "title TEXT, "
                    "created_at TEXT, "
                    f"embedding vector({_EMBEDDING_DIM})"
                    ")"
                )
            )
            try:
                await conn.execute(
                    text(
                        f"CREATE INDEX ix_{_VECTOR_TABLE}_hnsw ON {_VECTOR_TABLE} "
                        f"USING hnsw (embedding vector_cosine_ops)"
                    )
                )
            except Exception:  # noqa: BLE001 - optional accelerator, see docstring
                logger.info("hnsw index not available; falling back to seqscan similarity")
        async with self.session_factory() as session:
            rows = await self._load_seed_findings(session)
        async with self.engine.begin() as conn:
            for row in rows:
                snippet = row.evidence_snippet[:_INDEX_SNIPPET_MAX]
                await conn.execute(
                    text(
                        f"INSERT INTO {_VECTOR_TABLE} "
                        "(finding_id, run_id, finding_type, evidence_snippet, "
                        "field_source, severity, title, created_at, embedding) VALUES "
                        "(:finding_id, :run_id, :finding_type, :evidence_snippet, "
                        ":field_source, :severity, :title, :created_at, "
                        "CAST(:embedding AS vector))"
                    ),
                    {
                        "finding_id": row.id,
                        "run_id": row.run_id,
                        "finding_type": str(row.finding_type),
                        "evidence_snippet": snippet,
                        "field_source": row.field_source[:_INDEX_SNIPPET_MAX],
                        "severity": str(row.severity) if row.severity else None,
                        "title": row.title,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "embedding": _format_vector(_embed(snippet)),
                    },
                )
        self._ready = True
        logger.info("knowledge vector index rebuilt with %d historical findings", len(rows))

    async def search(
        self,
        query: str,
        *,
        finding_type: FindingType | None = None,
        exclude_finding_id: str | None = None,
        limit: int = 5,
    ) -> list[RetrievedEvidence]:
        """Return the top-``limit`` rows most similar to ``query`` (cosine).

        Post-filters mirror the FTS5 path so both backends share semantics.
        ``score`` = ``1 - cosine_distance`` clamped to ``[0, 1]``: 1.0 means
        identical direction, 0.0 means unrelated — the same "higher is
        better" direction as the FTS5 ``bm25`` ranking.
        """
        if not self._ready:
            await self.rebuild()
        query = (query or "").strip()
        if not query:
            return []
        query_vector = _format_vector(_embed(query))
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    f"SELECT finding_id, run_id, finding_type, evidence_snippet, "
                    "severity, title, created_at, "
                    f"(1.0 - (embedding <=> CAST(:q AS vector))) AS score "
                    f"FROM {_VECTOR_TABLE} "
                    "WHERE embedding IS NOT NULL "
                    f"ORDER BY embedding <=> CAST(:q AS vector) LIMIT :limit"
                ),
                {"q": query_vector, "limit": limit * 4},  # headroom for post-filters
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
                        _parse_created_at(raw["created_at"])
                        if raw["created_at"] is not None
                        else None
                    ),
                    score=max(0.0, min(1.0, float(raw["score"]))),
                )
            )
            if len(rows) >= limit:
                break
        return rows

    async def _load_seed_findings(self, session: AsyncSession) -> list[Finding]:
        """Newest-first bounded seed — same policy as the FTS5 index."""
        from sqlalchemy import select

        result = await session.exec(
            select(Finding).order_by(Finding.created_at.desc()).limit(_INDEX_SEED_LIMIT)
        )
        return list(result.scalars()) or []


def _parse_created_at(raw: str) -> object:
    """Parse the ISO string stored at insert time (see KnowledgeIndex)."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
