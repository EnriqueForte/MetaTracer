"""REST endpoints for operator feedback (TASK-13, v2.1+).

Each endpoint delegates to the shared repositories: the Finding rows belong
to the detection/classification/agent pipeline, and the feedback rows are the
operator's few-shot memory for future runs. No business logic lives here.

Contract notes (TASK-13):

- one active feedback per ``finding_id`` — ``PUT`` upserts (create or
  replace) so correcting the same finding twice never duplicates memory;
- ``vote`` direction must match ``severity_after`` against the finding's
  current severity; a same-severity "correction" is a 422;
- the ``reason`` is operator context only, truncated to ~150 chars, and never
  travels to the LLM (the few-shot examples carry structured fields only);
- feedback never touches ``evidence_snippet``/``finding_type`` and never
  triggers network I/O — it is read/write of local rows only.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from metatracer.db.models import (
    FeedbackVote,
    FindingFeedback,
    Severity,
    severity_rank,
)
from metatracer.db.repositories import FeedbackRepository, FindingRepository

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# Defense in depth: the memory rows feed future prompts; a competing reason
# must not bloat them. Mirrors the raw-metadata truncation strategy.
_MAX_REASON_CHARS = 150


class FeedbackCreate(BaseModel):
    """PUT body: the operator's correction of one finding's severity."""

    vote: FeedbackVote
    severity_after: Severity
    reason: str | None = Field(default=None)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped[: _MAX_REASON_CHARS] or None


class FeedbackResponse(BaseModel):
    """One persisted feedback row, returned on GET/PUT."""

    finding_id: str
    run_id: str
    vote: FeedbackVote
    severity_before: Severity
    severity_after: Severity
    reason: str | None
    created_at: datetime


def _validate_vote_direction(
    vote: FeedbackVote, before: Severity | None, after: Severity
) -> None:
    """Raise a 422 when the correction is not in the vote's direction.

    ``before`` may be None for an unclassified finding: there is nothing to
    correct yet, so any vote is refused (the operator should run the
    classifier first). Otherwise severity must move strictly in the vote's
    direction (up raises, down lowers) — a no-op correction is not feedback.
    """
    if before is None:
        raise HTTPException(
            status_code=422,
            detail="finding has no severity yet; classify it before giving feedback",
        )
    before_rank = severity_rank(before)
    after_rank = severity_rank(after)
    moves_up = after_rank > before_rank
    moves_down = after_rank < before_rank
    if not (moves_up if vote is FeedbackVote.up else moves_down):
        direction = "higher" if vote is FeedbackVote.up else "lower"
        raise HTTPException(
            status_code=422,
            detail=(
                f"vote '{vote}' requires severity_after to be strictly {direction} "
                f"than the current severity ({before})"
            ),
        )


def _response_from(feedback: FindingFeedback) -> FeedbackResponse:
    return FeedbackResponse(
        finding_id=feedback.finding_id,
        run_id=feedback.run_id,
        vote=feedback.vote,
        severity_before=feedback.severity_before,
        severity_after=feedback.severity_after,
        reason=feedback.reason,
        created_at=feedback.created_at,
    )


@router.put("/{finding_id}", status_code=200)
async def upsert_feedback(
    finding_id: str, payload: FeedbackCreate, request: Request
) -> FeedbackResponse:
    """Create, or replace, the operator feedback for one finding.

    The current severity of the finding at vote time is recorded as
    ``severity_before`` so the few-shot example stays truthful even if the
    finding is re-classified later.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        finding = await FindingRepository(session).get(finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail="finding not found")
        before = finding.severity
        feedback_repo = FeedbackRepository(session)
        existing = await feedback_repo.get_by_finding(finding_id)
        if existing is not None:
            # Operational corrections form a chain: the vote is validated
            # against the last corrected severity, so up/down can alternate
            # (high -> medium, then medium -> high) without inventing a step.
            before = existing.severity_after
        _validate_vote_direction(payload.vote, before, payload.severity_after)
        feedback = await feedback_repo.upsert_by_finding(
            FindingFeedback(
                finding_id=finding_id,
                run_id=finding.run_id,
                vote=payload.vote,
                severity_before=before,
                severity_after=payload.severity_after,
                reason=payload.reason,
            )
        )
    return _response_from(feedback)


@router.get("/{finding_id}")
async def get_feedback(finding_id: str, request: Request) -> FeedbackResponse:
    """Return the active feedback of one finding, if any."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        feedback = await FeedbackRepository(session).get_by_finding(finding_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="no feedback for finding")
    return _response_from(feedback)


@router.delete("/{finding_id}", status_code=204)
async def delete_feedback(finding_id: str, request: Request) -> None:
    """Remove the operator feedback (the memory forgets that finding)."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        deleted = await FeedbackRepository(session).delete(finding_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="no feedback for finding")