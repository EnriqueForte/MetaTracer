"""Read-only inspection of the light-RAG knowledge index (TASK-14, v2.1+).

Exposes ``GET /api/knowledge/search`` so an operator can see what the agent
would retrieve for a snippet (demo/debug). It is **read-only and local**: it
rebuilds the index lazily if needed and searches it; it never touches the
network, never writes business rows, and never exports findings outside the
local server.
"""

import os
from pathlib import Path
from tempfile import mkstemp

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from metatracer.agents.knowledge import KnowledgeRetriever, RetrievedEvidence
from metatracer.db.models import FindingType
from metatracer.knowledge.portable import export_kb, import_kb

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class SearchHit(BaseModel):
    """One ranked hit, surface-safe: no run_id, no raw ids beyond finding_id."""

    finding_id: str
    finding_type: str
    evidence_snippet: str
    severity: str | None
    title: str | None
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]


def _hit_from(retrieved: RetrievedEvidence) -> SearchHit:
    return SearchHit(
        finding_id=retrieved.finding_id,
        finding_type=str(retrieved.finding_type),
        evidence_snippet=retrieved.evidence_snippet,
        severity=str(retrieved.severity) if retrieved.severity else None,
        title=retrieved.title,
        score=round(retrieved.score, 3),
    )


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    request: Request,
    q: str = Query(..., min_length=1, description="evidence snippet or field source to match"),
    finding_type: str | None = Query(
        default=None,
        description="optional filter; one of the closed finding_type values",
    ),
    limit: int = Query(default=5, ge=1, le=20),
) -> SearchResponse:
    """Rank the historical findings most similar to ``q``.

    The retriever is built from the app's engine/factory on first use and
    reused for the life of the process. ``finding_type``, when given, must be
    a closed enum value; anything else is rejected with 422 by the Query
    dependency (FastAPI validates the Literal-style check below).
    """
    if finding_type is not None and finding_type not in FindingType.__members__:
        raise HTTPException(
            status_code=422,
            detail=f"finding_type must be one of {sorted(FindingType.__members__)}",
        )
    retriever: KnowledgeRetriever = getattr(request.app.state, "knowledge_retriever", None)
    if retriever is None:
        raise HTTPException(status_code=503, detail="knowledge index is not configured")
    hits = await retriever.retrieve(
        {
            "evidence_snippet": q,
            "field_source": q,
            "finding_type": finding_type or "",
        },
        exclude_finding_id=None,
    )
    truncated = hits[:limit]
    return SearchResponse(
        query=q,
        total=len(hits),
        hits=[_hit_from(hit) for hit in truncated],
    )


class ImportResponse(BaseModel):
    """Number of rows actually inserted by a portable-KB import (TASK-17)."""

    imported: int


@router.post("/export")
async def export_kb_endpoint(request: Request) -> FileResponse:
    """Export the historical precedents as a downloadable portable KB JSON.

    The writer streams to a temporary file (never persists a copy on the
    server); the operator downloads it and owns the file. Only the portable-KB
    contract fields leave the machine — never run/asset ids, raw metadata or
    bytes.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="knowledge index is not configured")
    fd, tmp_name = mkstemp(suffix=".json")
    os.close(fd)  # close the descriptor: FileResponse opens the path itself
    try:
        await export_kb(factory, Path(tmp_name))
        return FileResponse(
            tmp_name,
            media_type="application/json",
            filename="kb-export.json",
        )
    finally:
        # The FileResponse streams after this handler returns; schedule the
        # cleanup on the next loop tick so the download completes.
        import asyncio

        loop = asyncio.get_running_loop()
        loop.call_later(2.0, lambda: Path(tmp_name).unlink(missing_ok=True))


@router.post("/import", response_model=ImportResponse)
async def import_kb_endpoint(request: Request) -> ImportResponse:
    """Import a portable KB JSON into the local database (idempotent).

    Rows whose original finding id was already imported are skipped; nothing
    is deleted. ``finding_type``/``severity`` are validated against the
    closed enums and an invalid file is rejected with 422 (never reassigned).
    The body is the raw portable JSON (no multipart, keeping the dependency
    list closed).
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="knowledge index is not configured")

    # Defense in depth: the API-edge middleware already rejects oversized
    # Content-Length, but re-check here so a chunked/streamed body is bounded
    # even if the middleware wiring changes (v2.3 perf slice).
    from metatracer.core.ratelimit import enforce_body_limit

    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit():
        enforce_body_limit(
            int(content_length), int(getattr(request.app.state, "max_request_body_bytes", 0))
        )
    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="empty body: send the portable KB JSON")
    fd, tmp_name = mkstemp(suffix=".json")
    os.close(fd)
    try:
        with open(tmp_name, "wb") as fh:
            fh.write(body)
        try:
            imported = await import_kb(factory, Path(tmp_name))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ImportResponse(imported=imported)
    finally:
        Path(tmp_name).unlink(missing_ok=True)