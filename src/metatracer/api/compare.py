"""GET /api/compare?a=&b=: read-only comparison of two runs (TASK-35, block 35.4)."""

from fastapi import APIRouter, HTTPException, Query, Request

from metatracer.api.schemas import (
    ComparedFindingResponse,
    ComparedRun,
    RunComparisonResponse,
    _json_str_list,
)
from metatracer.core.exceptions import RunNotFoundError
from metatracer.db.models import Run
from metatracer.services.compare import ComparedFinding, compare_runs

router = APIRouter(prefix="/api/compare", tags=["runs"])


def _run(run: Run) -> ComparedRun:
    targets = _json_str_list(run.target_input)
    return ComparedRun(
        run_id=run.id,
        target=targets[0] if targets else "unknown",
        status=run.status,
        started_at=run.started_at,
        total_findings=run.total_findings,
    )


def _finding(item: ComparedFinding) -> ComparedFindingResponse:
    return ComparedFindingResponse(
        finding_id=item.finding.id,
        run_id=item.finding.run_id,
        finding_type=item.finding.finding_type,
        severity=item.finding.severity,
        evidence_snippet=item.finding.evidence_snippet,
        asset_url=item.asset_url,
        triage_status=item.finding.triage_status,
    )


@router.get("", response_model=RunComparisonResponse)
async def compare(
    request: Request,
    a: str = Query(..., min_length=1, max_length=64, description="Baseline run id"),
    b: str = Query(..., min_length=1, max_length=64, description="Run under review"),
) -> RunComparisonResponse:
    """Findings new in ``b``, resolved since ``a`` and present in both."""
    try:
        result = await compare_runs(request.app.state.session_factory, a, b)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return RunComparisonResponse(
        a=_run(result.a),
        b=_run(result.b),
        new=[_finding(item) for item in result.new],
        resolved=[_finding(item) for item in result.resolved],
        persistent=[_finding(item) for item in result.persistent],
    )
