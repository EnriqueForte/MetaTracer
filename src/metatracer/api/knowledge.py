"""Read-only inspection of the light-RAG knowledge index (TASK-14, v2.1+).

Exposes ``GET /api/knowledge/search`` so an operator can see what the agent
would retrieve for a snippet (demo/debug). It is **read-only and local**: it
rebuilds the index lazily if needed and searches it; it never touches the
network, never writes business rows, and never exports findings outside the
local server.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from metatracer.agents.knowledge import KnowledgeRetriever, RetrievedEvidence
from metatracer.db.models import FindingType

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