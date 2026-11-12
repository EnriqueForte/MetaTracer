"""GET /api/search — global findings and metadata (TASK-46)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from metatracer.core.exceptions import MetaTracerError
from metatracer.db.models import FindingType, Severity, TriageStatus
from metatracer.db.repositories import _UNSET
from metatracer.services.search import (
    NAMESPACES,
    GlobalSearchService,
    ScopeLookupError,
    SearchKind,
    SearchMode,
)

router = APIRouter(prefix="/api/search", tags=["search"])

_MAX_Q = 200


class FindingSearchHit(BaseModel):
    kind: Literal["finding"] = "finding"
    id: str
    run_id: str
    asset_id: str
    asset_url: str
    finding_type: FindingType
    type_label: str
    title: str | None = None
    field_source: str
    evidence_snippet: str
    severity: Severity | None = None
    triage_status: TriageStatus
    created_at: datetime
    score: float | None = None


class MetadataSearchHit(BaseModel):
    kind: Literal["metadata"] = "metadata"
    id: int
    run_id: str
    asset_id: str
    asset_url: str
    namespace: str
    key: str
    value: str


class SearchPageFindings(BaseModel):
    total: int
    items: list[FindingSearchHit]
    has_more: bool = False
    next_cursor: str | None = None


class SearchPageMetadata(BaseModel):
    total: int
    items: list[MetadataSearchHit]
    has_more: bool = False
    next_cursor: str | None = None


class GlobalSearchResponse(BaseModel):
    query: str
    kind: SearchKind
    mode: SearchMode
    findings: SearchPageFindings
    metadata: SearchPageMetadata


def _service(request: Request) -> GlobalSearchService:
    return GlobalSearchService(
        request.app.state.session_factory,
        retriever=getattr(request.app.state, "knowledge_retriever", None),
    )


@router.get("", response_model=GlobalSearchResponse)
async def global_search(
    request: Request,
    q: Annotated[
        str, Query(min_length=1, max_length=_MAX_Q, description="Substring or similar seed")
    ],
    kind: Annotated[SearchKind, Query()] = "all",
    mode: Annotated[SearchMode, Query()] = "lexical",
    run_id: Annotated[str | None, Query()] = None,
    scope_id: Annotated[str | None, Query()] = None,
    finding_type: Annotated[FindingType | None, Query()] = None,
    namespace: Annotated[str | None, Query(max_length=32)] = None,
    severity: Annotated[str | None, Query(description="closed severity or unclassified")] = None,
    triage_status: Annotated[TriageStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    findings_cursor: Annotated[str | None, Query()] = None,
    metadata_cursor: Annotated[str | None, Query()] = None,
) -> GlobalSearchResponse:
    """Search stored findings and raw metadata. Never crawls. Never reads bodies."""
    if namespace is not None and namespace not in NAMESPACES:
        raise HTTPException(
            status_code=422,
            detail=f"namespace must be one of {sorted(NAMESPACES)}",
        )
    severity_filter: object = _UNSET
    if severity is not None:
        if severity == "unclassified":
            severity_filter = None
        elif severity in Severity.__members__:
            severity_filter = Severity(severity)
        else:
            raise HTTPException(status_code=422, detail="invalid severity")
    try:
        result = await _service(request).search(
            q.strip(),
            kind=kind,
            mode=mode,
            run_id=run_id,
            scope_id=scope_id,
            finding_type=finding_type,
            namespace=namespace,
            severity=severity_filter,
            triage_status=triage_status,
            limit=limit,
            findings_cursor=findings_cursor,
            metadata_cursor=metadata_cursor,
        )
    except ScopeLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MetaTracerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GlobalSearchResponse(
        query=result.query,
        kind=result.kind,
        mode=result.mode,
        findings=SearchPageFindings(
            total=result.findings.total,
            items=[
                FindingSearchHit(
                    id=hit.id,
                    run_id=hit.run_id,
                    asset_id=hit.asset_id,
                    asset_url=hit.asset_url,
                    finding_type=hit.finding_type,
                    type_label=hit.type_label,
                    title=hit.title,
                    field_source=hit.field_source,
                    evidence_snippet=hit.evidence_snippet,
                    severity=hit.severity,
                    triage_status=hit.triage_status,
                    created_at=hit.created_at,
                    score=hit.score,
                )
                for hit in result.findings.items
            ],
            has_more=result.findings.has_more,
            next_cursor=result.findings.next_cursor,
        ),
        metadata=SearchPageMetadata(
            total=result.metadata.total,
            items=[
                MetadataSearchHit(
                    id=hit.id,
                    run_id=hit.run_id,
                    asset_id=hit.asset_id,
                    asset_url=hit.asset_url,
                    namespace=hit.namespace,
                    key=hit.key,
                    value=hit.value,
                )
                for hit in result.metadata.items
            ],
            has_more=result.metadata.has_more,
            next_cursor=result.metadata.next_cursor,
        ),
    )
