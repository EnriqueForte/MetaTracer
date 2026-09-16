"""REST endpoints for runs (TASK-06, subtask 6.3).

Every endpoint delegates to the shared services: the orchestrator owns the
pipeline and the single-scan lock, the ReportBuilder owns the finding order
(the same one the CLI table and the exported reports use). No business logic
lives in this layer.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from metatracer.api.schemas import (
    FindingResponse,
    FindingsResponse,
    RunCreatedResponse,
    RunListItem,
    RunListResponse,
    RunStatusResponse,
    _encode_cursor,
)
from metatracer.core.exceptions import (
    MetaTracerError,
    ScanAlreadyRunningError,
    ScopeNotConfirmedError,
    ScopeNotFoundError,
)
from metatracer.db.models import Confidence, FindingType, RunStatus, Severity
from metatracer.db.repositories import AssetRepository, RunRepository
from metatracer.reports.builder import ReportBuilder
from metatracer.reports.filters import filter_findings
from metatracer.services.orchestrator import ExportFormat, ScanRequest
from metatracer.services.progress import TERMINAL_STAGES

router = APIRouter(prefix="/api/runs", tags=["runs"])

# SSE keep-alive cadence: a comment line EventSource ignores, so proxies and
# browsers never mistake an idle stream for a dead one.
_SSE_KEEPALIVE_SECONDS = 15

_EXPORT_MEDIA_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "html": "text/html; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "bounty": "text/plain; charset=utf-8",
}

_MAX_HISTORY = 200


@router.get("")
async def list_runs(
    request: Request,
    status: Annotated[RunStatus | None, Query(description="Filter by run status")] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_HISTORY, description="Newest N runs")] = 50,
    cursor: Annotated[
        str | None,
        Query(
            description="Opaque keyset anchor from a previous page's next_cursor "
            "(<started_at_iso>_<run_id>)"
        ),
    ] = None,
) -> RunListResponse:
    """Local run history, newest first (TASK-08). Not a multi-tenant dashboard.

    TASK-21 (v2.4): cursor pagination. The repo fetches ``limit + 1`` rows so
    ``has_more`` needs no extra query; ``next_cursor`` is the last row's
    ``(started_at, id)`` anchor when more rows exist. Keyset stays stable when
    a new run lands between two pages — nothing is duplicated or dropped.
    ``limit`` remains bounded by ``_MAX_HISTORY``.
    """
    session_factory = request.app.state.session_factory
    try:
        async with session_factory() as session:
            repo = RunRepository(session)
            runs = await repo.list_recent(status=status, limit=limit, cursor=cursor)
            total = await repo.count(status=status)
    except ValueError as exc:
        # Malformed cursor (not <started_at_iso>_<run_id>): the keyset anchor
        # comes back from the API itself, so a client cannot legitimately
        # invent one — answer 422, not 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    has_more = len(runs) > limit
    page = runs[:limit]
    items = [RunListItem.from_run(run) for run in page]
    next_cursor = _encode_cursor(page[-1].started_at, page[-1].id) if has_more else None
    return RunListResponse.from_page(
        total=total, runs=items, has_more=has_more, next_cursor=next_cursor
    )


@router.post("", status_code=202)
async def create_run(payload: ScanRequest, request: Request) -> RunCreatedResponse:
    """Start a scan in the background; the run_id is known immediately.

    The scope gate and the single-scan lock live in the orchestrator and raise
    synchronously inside :meth:`ScanOrchestratorService.start_scan`, so the
    403/409 answers happen within this request — never after a 202.
    """
    orchestrator = request.app.state.orchestrator
    bus = request.app.state.bus
    try:
        run_id = await orchestrator.start_scan(
            payload,
            formats=ExportFormat.all,
            output_dir=request.app.state.reports_dir,
            on_progress=bus.publish,
        )
    except ScopeNotConfirmedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ScanAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunCreatedResponse(run_id=run_id)


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> RunStatusResponse:
    """Status, counters, timestamps and the failed/skipped asset issues."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        assets = await AssetRepository(session).list_by_run(run_id)
    return RunStatusResponse.from_models(run, assets)


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    """Server-sent events stream of ProgressEvent (one JSON object per event).

    The bus replays the run's full history into the subscriber queue, so a
    client connecting late or reconnecting still sees every stage; the stream
    closes after the terminal ``completed``/``failed`` event.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    bus = request.app.state.bus
    queue = bus.subscribe(run_id)

    async def events() -> AsyncIterator[str]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), _SSE_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {event.model_dump_json()}\n\n"
                if event.stage in TERMINAL_STAGES:
                    break
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/findings")
async def list_findings(
    run_id: str,
    request: Request,
    severity: Annotated[Severity | None, Query(description="Filter by severity")] = None,
    finding_type: Annotated[
        FindingType | None, Query(description="Filter by finding type")
    ] = None,
    confidence: Annotated[
        Confidence | None, Query(description="Filter by confidence")
    ] = None,
    q: Annotated[str | None, Query(description="Case-insensitive substring search")] = None,
) -> FindingsResponse:
    """Findings in report order (critical -> info, unclassified last).

    Filters are exploration-only: exported reports stay complete. Invalid enum
    values are rejected by FastAPI with 422.
    """
    builder = ReportBuilder(request.app.state.session_factory)
    try:
        data = await builder.build(run_id)
    except MetaTracerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    filtered = filter_findings(
        data.findings,
        severity=severity,
        finding_type=finding_type,
        confidence=confidence,
        q=q,
    )
    findings = [FindingResponse.from_report(entry) for entry in filtered]
    return FindingsResponse(run_id=run_id, total=len(findings), findings=findings)


@router.get("/{run_id}/export")
async def export_run(
    run_id: str,
    request: Request,
    format: Annotated[
        Literal["md", "json", "html", "csv", "bounty"], Query(description="Report format")
    ],
) -> FileResponse:
    """Regenerate the report from the database and serve it as an attachment.

    The file name comes from the exporter (sanitized slug + run id +
    timestamp), never from raw user input.
    """
    orchestrator = request.app.state.orchestrator
    try:
        paths = await orchestrator.export_report(
            run_id,
            formats=ExportFormat(format),
            output_dir=request.app.state.reports_dir,
        )
    except MetaTracerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = paths[format]
    return FileResponse(path, media_type=_EXPORT_MEDIA_TYPES[format], filename=path.name)
