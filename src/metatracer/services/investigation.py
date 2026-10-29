"""Investigation groups and triage suggestions (Fase 3).

An investigation groups runs. It does not hide them from the rest of the
install. A triage decision on one run is *suggested* on the same finding
(same final URL, type and normalized snippet) in another run of the group.
Nothing here writes ``triage_status``, ``severity`` or evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import InvestigationConflictError, MetaTracerError
from metatracer.db.models import Investigation, InvestigationStatus, Run, TriageStatus
from metatracer.db.repositories import FindingRepository, InvestigationRepository, RunRepository
from metatracer.detectors.consolidator import finding_identity

# ``open`` is the absence of a decision, so it is never suggested.
_DECISIVE = frozenset(
    {TriageStatus.confirmed, TriageStatus.false_positive, TriageStatus.fixed}
)


@dataclass(frozen=True, slots=True)
class TriageSuggestion:
    """A prior operator decision offered for one finding. Not yet applied."""

    status: TriageStatus
    from_run_id: str
    from_finding_id: str
    note: str | None
    triaged_at: datetime | None


async def create_investigation(
    session: AsyncSession, *, name: str, description: str | None
) -> Investigation:
    existing = await InvestigationRepository(session).get_by_name(name)
    if existing is not None:
        raise InvestigationConflictError(f"an investigation named {name!r} already exists")
    return await InvestigationRepository(session).create(
        Investigation(name=name, description=description, status=InvestigationStatus.open)
    )


async def attach_run(session: AsyncSession, investigation_id: str, run_id: str) -> Run:
    """Group ``run_id`` under the investigation. Refuses a second group."""
    investigation = await InvestigationRepository(session).get(investigation_id)
    if investigation is None:
        raise MetaTracerError("investigation not found")
    if investigation.status is InvestigationStatus.closed:
        raise InvestigationConflictError("a closed investigation does not take new runs")
    runs = RunRepository(session)
    run = await runs.get(run_id)
    if run is None:
        raise MetaTracerError("run not found")
    if run.investigation_id and run.investigation_id != investigation_id:
        raise InvestigationConflictError("run is already in another investigation")
    run.investigation_id = investigation_id
    return await runs.update(run)


async def detach_run(session: AsyncSession, investigation_id: str, run_id: str) -> Run:
    runs = RunRepository(session)
    run = await runs.get(run_id)
    if run is None or run.investigation_id != investigation_id:
        raise MetaTracerError("run not found in this investigation")
    run.investigation_id = None
    return await runs.update(run)


async def suggestions_for(
    session: AsyncSession,
    run: Run,
    rows: list[tuple[str, str, str, str]],
) -> dict[str, TriageSuggestion]:
    """Map finding id -> the latest decisive triage of the same identity.

    ``rows`` is ``(finding_id, asset_final_url, finding_type, evidence_snippet)``
    for the run being read. Runs outside the investigation are ignored, and
    this function does not update the findings it looks at.
    """
    if not run.investigation_id or not rows:
        return {}
    priors = await FindingRepository(session).decisive_triage_in_investigation(
        run.investigation_id, run.id
    )
    best: dict[str, tuple[datetime, TriageSuggestion]] = {}
    for finding, url in priors:
        status = TriageStatus(finding.triage_status)
        if status not in _DECISIVE:
            continue
        key = finding_identity(url, finding.finding_type, finding.evidence_snippet)
        suggestion = TriageSuggestion(
            status=status,
            from_run_id=finding.run_id,
            from_finding_id=finding.id,
            note=finding.triage_note,
            triaged_at=_as_utc(finding.triaged_at) if finding.triaged_at else None,
        )
        moment = _as_utc(finding.triaged_at or finding.created_at)
        current = best.get(key)
        if current is None or moment >= current[0]:
            best[key] = (moment, suggestion)
    found: dict[str, TriageSuggestion] = {}
    for finding_id, url, kind, snippet in rows:
        chosen = best.get(finding_identity(url, kind, snippet))
        if chosen is not None:
            found[finding_id] = chosen[1]
    return found


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
