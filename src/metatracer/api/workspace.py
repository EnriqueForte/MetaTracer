"""Read-only workspace endpoints: assets, raw metadata and coverage (Fase 1).

Four routes, all ``GET`` and all scoped to one run:

- ``GET /api/runs/{run_id}/assets``                    inventory, keyset paged
- ``GET /api/runs/{run_id}/assets/{asset_id}/metadata`` one asset's fields
- ``GET /api/runs/{run_id}/metadata``                  run-wide field search
- ``GET /api/runs/{run_id}/coverage``                  what the run collected

Why these exist: ``RawMetadataItem`` has always been persisted, but no endpoint
read it, so everything outside the five finding types was invisible to the
analyst. Nothing here writes, scores or deduplicates — it is a read path over
rows the extractors already produced.

The router carries no business logic: filtering, pagination and mapping live in
:class:`metatracer.services.workspace.RunWorkspaceService`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from metatracer.core.exceptions import MetaTracerError
from metatracer.db.models import CorrelationKind, ExtractionStatus, SkipReason
from metatracer.services.correlation import groups_touching_run
from metatracer.services.workspace import (
    DEFAULT_ASSET_PAGE,
    DEFAULT_METADATA_PAGE,
    MAX_ASSET_PAGE,
    MAX_METADATA_PAGE,
    AssetSummary,
    CoverageSummary,
    MetadataEntry,
    RunWorkspaceService,
)

router = APIRouter(prefix="/api/runs", tags=["workspace"])


class AssetResponse(BaseModel):
    """One asset row of the inventory: no bytes, no metadata values."""

    id: str
    source_url: str
    final_url: str
    content_type: str
    file_hash_sha256: str
    file_size_bytes: int
    extraction_status: ExtractionStatus
    skip_reason: SkipReason | None
    error_message: str | None
    discovered_at: datetime
    metadata_fields: int
    findings: int

    @classmethod
    def from_summary(cls, asset: AssetSummary) -> AssetResponse:
        return cls(
            id=asset.id,
            source_url=asset.source_url,
            final_url=asset.final_url,
            content_type=asset.content_type,
            file_hash_sha256=asset.file_hash_sha256,
            file_size_bytes=asset.file_size_bytes,
            extraction_status=asset.extraction_status,
            skip_reason=asset.skip_reason,
            error_message=asset.error_message,
            discovered_at=asset.discovered_at,
            metadata_fields=asset.metadata_fields,
            findings=asset.findings,
        )


class AssetListResponse(BaseModel):
    """``total`` is the run-wide count; ``has_more``/``next_cursor`` page it."""

    run_id: str
    total: int
    assets: list[AssetResponse]
    has_more: bool = False
    next_cursor: str | None = None


class MetadataItemResponse(BaseModel):
    """One stored field. ``truncated`` reflects the extractor's marker."""

    id: int
    asset_id: str
    asset_url: str
    namespace: str
    key: str
    value: str
    truncated: bool

    @classmethod
    def from_entry(cls, entry: MetadataEntry) -> MetadataItemResponse:
        return cls(
            id=entry.id,
            asset_id=entry.asset_id,
            asset_url=entry.asset_url,
            namespace=entry.namespace,
            key=entry.key,
            value=entry.value,
            truncated=entry.truncated,
        )


class MetadataListResponse(BaseModel):
    run_id: str
    total: int
    items: list[MetadataItemResponse]
    has_more: bool = False
    next_cursor: str | None = None


class CoverageResponse(BaseModel):
    """What the run collected, split by extraction status.

    ``counters_recorded`` is ``false`` until the crawl budget is persisted
    (Fase 2): the UI must say "not recorded" rather than show a zero that looks
    like "nothing was found".
    """

    run_id: str
    status: str
    total_assets: int
    ok: int
    skipped: int
    failed: int
    bytes_downloaded: int
    metadata_fields: int
    findings: int
    by_skip_reason: dict[str, int]
    by_namespace: dict[str, int]
    counters_recorded: bool
    limits_hit: list[str]
    budget: dict[str, int]
    pages_crawled: int
    assets_queued: int
    elapsed_seconds: float
    # Null until a run records robots.txt courtesy. Zero is "consulted, nothing
    # omitted", which is a different claim from "not recorded".
    robots_checked: bool | None = None
    robots_omitted: int | None = None
    sitemaps_ignored: int | None = None
    sitemaps_truncated: bool | None = None

    @classmethod
    def from_summary(cls, coverage: CoverageSummary) -> CoverageResponse:
        return cls(
            run_id=coverage.run_id,
            status=coverage.status,
            total_assets=coverage.total_assets,
            ok=coverage.ok,
            skipped=coverage.skipped,
            failed=coverage.failed,
            bytes_downloaded=coverage.bytes_downloaded,
            metadata_fields=coverage.metadata_fields,
            findings=coverage.findings,
            by_skip_reason=coverage.by_skip_reason,
            by_namespace=coverage.by_namespace,
            counters_recorded=coverage.counters_recorded,
            limits_hit=list(coverage.limits_hit),
            budget=dict(coverage.budget),
            pages_crawled=coverage.pages_crawled,
            assets_queued=coverage.assets_queued,
            elapsed_seconds=coverage.elapsed_seconds,
            robots_checked=coverage.robots_checked,
            robots_omitted=coverage.robots_omitted,
            sitemaps_ignored=coverage.sitemaps_ignored,
            sitemaps_truncated=coverage.sitemaps_truncated,
        )


def _service(request: Request) -> RunWorkspaceService:
    return RunWorkspaceService(request.app.state.session_factory)


def _not_found(exc: MetaTracerError) -> HTTPException:
    """``run/asset not found`` is a 404, never a 500.

    The service raises ``MetaTracerError`` for a missing run or for an
    ``asset_id`` that exists but belongs to another run — both are "not here".
    """
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/{run_id}/assets", response_model=AssetListResponse)
async def list_assets(
    run_id: str,
    request: Request,
    status: Annotated[
        ExtractionStatus | None, Query(description="Filter by extraction status")
    ] = None,
    content_type: Annotated[
        str | None,
        Query(
            description="Content-type prefix, e.g. 'image/' or 'application/pdf'",
            max_length=100,
        ),
    ] = None,
    q: Annotated[str | None, Query(description="URL substring, case-insensitive")] = None,
    limit: Annotated[
        int, Query(ge=1, le=MAX_ASSET_PAGE, description="Page size")
    ] = DEFAULT_ASSET_PAGE,
    cursor: Annotated[str | None, Query(description="Opaque keyset anchor")] = None,
) -> AssetListResponse:
    """Inventory of the run's assets, oldest first, with field/finding counts."""
    try:
        page = await _service(request).list_assets(
            run_id,
            status=status,
            content_type=content_type,
            q=q,
            limit=limit,
            cursor=cursor,
        )
    except MetaTracerError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        # Malformed cursor: the anchor comes from this API, so a client cannot
        # legitimately invent one. 422, not 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssetListResponse(
        run_id=page.run_id,
        total=page.total,
        assets=[AssetResponse.from_summary(asset) for asset in page.assets],
        has_more=page.has_more,
        next_cursor=page.next_cursor,
    )


@router.get("/{run_id}/assets/{asset_id}/metadata", response_model=MetadataListResponse)
async def list_asset_metadata(
    run_id: str,
    asset_id: str,
    request: Request,
    namespace: Annotated[str | None, Query(description="Exact namespace", max_length=32)] = None,
    key: Annotated[str | None, Query(description="Exact field key", max_length=200)] = None,
    q: Annotated[
        str | None, Query(description="Substring of the value or the key")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_METADATA_PAGE)] = DEFAULT_METADATA_PAGE,
    cursor: Annotated[str | None, Query(description="Opaque keyset anchor")] = None,
) -> MetadataListResponse:
    """Every stored field of one asset, in insertion order."""
    return await _metadata(
        request,
        run_id,
        asset_id=asset_id,
        namespace=namespace,
        key=key,
        q=q,
        limit=limit,
        cursor=cursor,
    )


@router.get("/{run_id}/metadata", response_model=MetadataListResponse)
async def list_run_metadata(
    run_id: str,
    request: Request,
    namespace: Annotated[str | None, Query(description="Exact namespace", max_length=32)] = None,
    key: Annotated[str | None, Query(description="Exact field key", max_length=200)] = None,
    q: Annotated[
        str | None, Query(description="Substring of the value or the key")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_METADATA_PAGE)] = DEFAULT_METADATA_PAGE,
    cursor: Annotated[str | None, Query(description="Opaque keyset anchor")] = None,
) -> MetadataListResponse:
    """Cross-asset field search for the whole run (the metadata explorer)."""
    return await _metadata(
        request,
        run_id,
        asset_id=None,
        namespace=namespace,
        key=key,
        q=q,
        limit=limit,
        cursor=cursor,
    )


class CorrelationMemberResponse(BaseModel):
    asset_id: str
    asset_url: str
    run_id: str
    namespace: str
    key: str


class CorrelationGroupResponse(BaseModel):
    """One shared value. ``notice`` is the product sentence: not an identity."""

    kind: CorrelationKind
    value_norm: str
    occurrences: int
    first_seen_run_id: str
    notice: str
    members: list[CorrelationMemberResponse]
    members_truncated: bool


class CorrelationListResponse(BaseModel):
    run_id: str
    total: int
    groups: list[CorrelationGroupResponse]


@router.get("/{run_id}/correlations", response_model=CorrelationListResponse)
async def list_correlations(run_id: str, request: Request) -> CorrelationListResponse:
    """Shared values that touch this run. A shared value is not a shared identity."""
    service = _service(request)
    try:
        async with request.app.state.session_factory() as session:
            await service._run(session, run_id)
            groups = await groups_touching_run(session, run_id)
    except MetaTracerError as exc:
        raise _not_found(exc) from exc
    return CorrelationListResponse(
        run_id=run_id,
        total=len(groups),
        groups=[
            CorrelationGroupResponse(
                kind=group.kind,
                value_norm=group.value_norm,
                occurrences=group.occurrences,
                first_seen_run_id=group.first_seen_run_id,
                notice=group.notice,
                members_truncated=group.members_truncated,
                members=[
                    CorrelationMemberResponse(
                        asset_id=member.asset_id,
                        asset_url=member.asset_url,
                        run_id=member.run_id,
                        namespace=member.namespace,
                        key=member.key,
                    )
                    for member in group.members
                ],
            )
            for group in groups
        ],
    )


@router.get("/{run_id}/coverage", response_model=CoverageResponse)
async def get_coverage(run_id: str, request: Request) -> CoverageResponse:
    """Counters of what the run stored, with the honest limits caveat."""
    try:
        coverage = await _service(request).coverage(run_id)
    except MetaTracerError as exc:
        raise _not_found(exc) from exc
    return CoverageResponse.from_summary(coverage)


async def _metadata(
    request: Request,
    run_id: str,
    *,
    asset_id: str | None,
    namespace: str | None,
    key: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> MetadataListResponse:
    """Shared body of the two metadata routes (asset-scoped and run-wide)."""
    try:
        page = await _service(request).list_metadata(
            run_id,
            asset_id=asset_id,
            namespace=namespace,
            key=key,
            q=q,
            limit=limit,
            cursor=cursor,
        )
    except MetaTracerError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MetadataListResponse(
        run_id=page.run_id,
        total=page.total,
        items=[MetadataItemResponse.from_entry(item) for item in page.items],
        has_more=page.has_more,
        next_cursor=page.next_cursor,
    )
