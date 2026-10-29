"""REST endpoints for runs (TASK-06, subtask 6.3).

Every endpoint delegates to the shared services: the orchestrator owns the
pipeline and the single-scan lock, the ReportBuilder owns the finding order
(the same one the CLI table and the exported reports use). No business logic
lives in this layer.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.api.auth import CurrentUser, get_current_user
from metatracer.api.schemas import (
    FindingResponse,
    FindingsResponse,
    RunCreatedResponse,
    RunListItem,
    RunListResponse,
    RunStatusResponse,
    TriageRequest,
    TriageResponse,
    TriageSuggestionResponse,
    _encode_cursor,
)
from metatracer.core.exceptions import (
    MetaTracerError,
    RunActiveError,
    RunNotAbortableError,
    RunNotFoundError,
    ScanAlreadyRunningError,
    ScopeNotConfirmedError,
    ScopeNotFoundError,
)
from metatracer.db.models import Confidence, FindingType, RunStatus, Severity, TriageStatus
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    InvestigationRepository,
    RunRepository,
)
from metatracer.reports.builder import ReportBuilder
from metatracer.reports.filters import filter_findings
from metatracer.services.investigation import suggestions_for
from metatracer.services.orchestrator import (
    TOTAL_STEPS,
    ExportFormat,
    ProgressEvent,
    ProgressStage,
    ScanRequest,
)
from metatracer.services.progress import TERMINAL_STAGES
from metatracer.services.retention import delete_run as delete_persisted_run

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


async def _investigation_name(session: AsyncSession, investigation_id: str | None) -> str | None:
    if not investigation_id:
        return None
    row = await InvestigationRepository(session).get(investigation_id)
    return row.name if row is not None else None


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> RunStatusResponse:
    """Status, counters, timestamps and the failed/skipped asset issues."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        assets = await AssetRepository(session).list_by_run(run_id)
        investigation_name = await _investigation_name(session, run.investigation_id)
    return RunStatusResponse.from_models(
        run, assets, investigation_name=investigation_name
    )


@router.delete("/{run_id}", status_code=204)
async def remove_run(run_id: str, request: Request) -> Response:
    """Delete a terminal run and the personal data that belongs to it (TASK-30).

    Operator + CSRF come from the router. 404 if the run does not exist,
    409 if it is still pending or running. Exported reports for this run
    are removed from the reports directory.
    """
    try:
        await delete_persisted_run(
            request.app.state.session_factory,
            run_id,
            reports_dir=request.app.state.reports_dir,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except RunActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/{run_id}/abort")
async def abort_run(run_id: str, request: Request) -> RunStatusResponse:
    """Stop a pending or running scan (TASK-28). Operator + CSRF via the router.

    404 when the run does not exist, 409 when it is already terminal.
    The SSE stream receives a terminal ``aborted`` event from the orchestrator.
    """
    orchestrator = request.app.state.orchestrator
    try:
        await orchestrator.abort(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except RunNotAbortableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        assets = await AssetRepository(session).list_by_run(run_id)
        investigation_name = await _investigation_name(session, run.investigation_id)
    return RunStatusResponse.from_models(
        run, assets, investigation_name=investigation_name
    )


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
    # History was evicted (or this process never saw the scan) and the row is
    # already terminal: emit one synthetic event and close. Subscribing would
    # wait forever for a publish that will not come (TASK-33).
    if run.status.value in {stage.value for stage in TERMINAL_STAGES} and not bus.has_history(
        run_id
    ):
        event = ProgressEvent(
            run_id=run_id,
            stage=ProgressStage(run.status.value),
            current_step=TOTAL_STEPS,
            total_steps=TOTAL_STEPS,
            message=run.error_message or run.status.value,
        )

        async def terminal_only() -> AsyncIterator[str]:
            yield f"data: {event.model_dump_json()}\n\n"

        return StreamingResponse(
            terminal_only(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
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
    triage_status: Annotated[
        TriageStatus | None, Query(description="Filter by operator triage status")
    ] = None,
) -> FindingsResponse:
    """Findings in report order (critical -> info, unclassified last).

    Filters are exploration-only. The list includes false positives with their
    ``triage_status`` (the UI hides them by default); exports leave them out.
    Invalid enum values are rejected by FastAPI with 422.
    """
    builder = ReportBuilder(request.app.state.session_factory)
    try:
        data = await builder.build(run_id, include_false_positives=True)
    except MetaTracerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    filtered = filter_findings(
        data.findings,
        severity=severity,
        finding_type=finding_type,
        confidence=confidence,
        q=q,
        triage=triage_status,
    )
    findings = [FindingResponse.from_report(entry) for entry in filtered]
    async with request.app.state.session_factory() as session:
        run = await RunRepository(session).get(run_id)
        if run is not None and run.investigation_id:
            suggested = await suggestions_for(
                session,
                run,
                [
                    (item.id, item.asset_final_url, item.finding_type.value, item.evidence_snippet)
                    for item in findings
                ],
            )
            findings = [
                item.model_copy(
                    update={
                        "triage_suggestion": (
                            TriageSuggestionResponse(
                                status=suggested[item.id].status,
                                from_run_id=suggested[item.id].from_run_id,
                                from_finding_id=suggested[item.id].from_finding_id,
                                note=suggested[item.id].note,
                                triaged_at=suggested[item.id].triaged_at,
                            )
                            if item.id in suggested
                            else None
                        )
                    }
                )
                for item in findings
            ]
    return FindingsResponse(run_id=run_id, total=len(findings), findings=findings)


@router.put("/{run_id}/findings/{finding_id}/triage", response_model=TriageResponse)
async def triage_finding(
    run_id: str,
    finding_id: str,
    body: TriageRequest,
    request: Request,
    user: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> TriageResponse:
    """Operator triage (CSRF + operator via the router's mutation dependencies).

    Changes ``triage_status`` and the note only. Severity and evidence stay
    exactly as stored (rule 6); the agent never calls this.
    """
    note = body.note.strip() if body.note else None
    async with request.app.state.session_factory() as session:
        finding = await FindingRepository(session).set_triage(
            run_id,
            finding_id,
            status=body.status,
            note=note,
            by=user.id if user is not None else "local",
        )
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return TriageResponse(
        finding_id=finding.id,
        triage_status=finding.triage_status,
        triage_note=finding.triage_note,
        triaged_by=finding.triaged_by,
        triaged_at=finding.triaged_at,
        severity=finding.severity,
        evidence_snippet=finding.evidence_snippet,
    )


@router.get("/{run_id}/export")
async def export_run(
    run_id: str,
    request: Request,
    format: Annotated[
        Literal["md", "json", "html", "csv", "bounty"], Query(description="Report format")
    ],
    include_false_positives: Annotated[
        bool, Query(description="Keep findings triaged as false_positive (default: excluded)")
    ] = False,
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
            include_false_positives=include_false_positives,
        )
    except MetaTracerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = paths[format]
    return FileResponse(path, media_type=_EXPORT_MEDIA_TYPES[format], filename=path.name)
