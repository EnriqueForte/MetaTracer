"""Read-only comparison of two runs (TASK-35, block 35.4; Fase 3).

Same identity as the watch delta (:func:`finding_identity`): asset final URL,
finding type and normalized snippet. ``a`` is the baseline and ``b`` the run
being reviewed:

- ``new``: in ``b`` and not in ``a``, and not seen in an earlier run of the
  same investigation;
- ``reappeared``: in ``b``, absent from ``a``, and present in an earlier run
  of the investigation both runs belong to. Outside a shared investigation
  there is no history to consult, so the finding stays ``new``;
- ``resolved``: in ``a`` and not in ``b``. This is absence from ``b``, not
  proof the finding is gone — ``limits_hit_b`` and ``coverage_recorded_b``
  say whether the reviewed crawl was complete;
- ``persistent``: in both, with the same severity (``b``'s row);
- ``severity_changed``: in both, with a different severity (``b``'s row,
  ``previous_severity`` from ``a``).

No writes, no network, no LLM. Evidence travels unchanged (rule 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import RunNotFoundError
from metatracer.db.models import Finding, Run, Severity
from metatracer.db.repositories import FindingRepository, RunRepository
from metatracer.detectors.consolidator import finding_identity


@dataclass(slots=True)
class ComparedFinding:
    finding: Finding
    asset_url: str
    identity: str
    previous_severity: Severity | None = None
    prior_run_id: str | None = None


@dataclass(slots=True)
class RunComparison:
    a: Run
    b: Run
    new: list[ComparedFinding] = field(default_factory=list)
    resolved: list[ComparedFinding] = field(default_factory=list)
    persistent: list[ComparedFinding] = field(default_factory=list)
    reappeared: list[ComparedFinding] = field(default_factory=list)
    severity_changed: list[ComparedFinding] = field(default_factory=list)
    limits_hit_a: list[str] = field(default_factory=list)
    limits_hit_b: list[str] = field(default_factory=list)
    coverage_recorded_a: bool = False
    coverage_recorded_b: bool = False


def _index(rows: list[tuple[Finding, str]]) -> dict[str, ComparedFinding]:
    indexed: dict[str, ComparedFinding] = {}
    for finding, url in rows:
        identity = finding_identity(url, finding.finding_type, finding.evidence_snippet)
        indexed.setdefault(identity, ComparedFinding(finding, url, identity))
    return indexed


async def compare_runs(
    session_factory: async_sessionmaker[AsyncSession], a_id: str, b_id: str
) -> RunComparison:
    async with session_factory() as session:
        runs = RunRepository(session)
        a = await runs.get(a_id)
        b = await runs.get(b_id)
        if a is None or b is None:
            raise RunNotFoundError("run not found")
        repo = FindingRepository(session)
        left = _index(await repo.with_asset_url([a_id]))
        right = _index(await repo.with_asset_url([b_id]))
        earlier = await _earlier_identities(session, a, b)
    recorded_a, limits_a = _coverage(a)
    recorded_b, limits_b = _coverage(b)
    result = RunComparison(
        a=a,
        b=b,
        limits_hit_a=limits_a,
        limits_hit_b=limits_b,
        coverage_recorded_a=recorded_a,
        coverage_recorded_b=recorded_b,
    )
    for identity, item in right.items():
        if identity not in left:
            prior = earlier.get(identity)
            if prior is not None:
                item.prior_run_id = prior
                result.reappeared.append(item)
            else:
                result.new.append(item)
            continue
        baseline = left[identity]
        if _severity(baseline.finding) != _severity(item.finding):
            item.previous_severity = baseline.finding.severity
            result.severity_changed.append(item)
        else:
            result.persistent.append(item)
    result.resolved = [item for identity, item in left.items() if identity not in right]
    return result


async def _earlier_identities(
    session: AsyncSession, baseline: Run, reviewed: Run
) -> dict[str, str]:
    """Identity -> run id, for sightings before the baseline in the same group.

    A finding that returns is only ``reappeared`` inside one investigation.
    Two runs that are not in that same group have no shared history here.
    """
    group = baseline.investigation_id
    if not group or group != reviewed.investigation_id:
        return {}
    result = await session.exec(select(Run).where(Run.investigation_id == group))
    moment = _as_utc(baseline.started_at)
    earlier_ids = [
        run.id
        for run in result.all()
        if run.id not in {baseline.id, reviewed.id} and _as_utc(run.started_at) < moment
    ]
    if not earlier_ids:
        return {}
    found: dict[str, str] = {}
    for finding, url in await FindingRepository(session).with_asset_url(earlier_ids):
        key = finding_identity(url, finding.finding_type, finding.evidence_snippet)
        found.setdefault(key, finding.run_id)
    return found


def _coverage(run: Run) -> tuple[bool, list[str]]:
    """Whether the crawl budget was recorded, and which limits it hit.

    A missing snapshot is unknown, not "no limit was reached".
    """
    raw = run.ingestion_stats
    if not isinstance(raw, str) or not raw.strip():
        return False, []
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError:
        return False, []
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("budget"), dict):
        return False, []
    raw_limits = snapshot.get("limits_hit")
    if not isinstance(raw_limits, list):
        return True, []
    return True, [str(item) for item in raw_limits if isinstance(item, str)]


def _severity(finding: Finding) -> str | None:
    value = finding.severity
    if value is None:
        return None
    return value.value if isinstance(value, Severity) else str(value)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
