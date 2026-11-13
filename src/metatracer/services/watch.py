"""Watch mode: headless re-scan with deterministic delta reporting (TASK-22 / TASK-50).

The platform v3.0 Eje A (features/12-platform-v3.md) turns a one-shot scan
into a continuous engagement: ``metatracer watch`` re-scans a saved scope on
a cadence and reports *deltas*.

Design contract:

- **Zero LLM, zero network**: the delta is a pure database comparison.
- **Run-independent identity** (TASK-35): ``dedup_signature`` embeds the
  asset id, which is new in every run, so findings are compared by
  :func:`finding_identity` (asset final URL + type + normalized snippet).
  ``new_signatures`` still reports the current run's ``dedup_signature``.
- **Scope identity = the snapshot**: a Run persists ``allowed_scope`` as its
  own snapshot (TASK-10). The delta compares a run against every *other* run
  whose ``allowed_scope`` matches the same snapshot, so deleting/editing a
  Scope object never changes the historical baseline.
- **Rule 1 intact**: the watch never invents a scope. ``--scope <id>`` is the
  single source of scope, resolved by the exact same ``ScopeRepository`` the
  wizard uses; the pipeline's ``scope_confirmed`` gate is never bypassed.
- **Broken consumers never kill the scan** (inviolable rule 5): the delta is
  computed in the orchestrator's notify path inside a ``try/except``, and a
  failure degrades to zeros (a missing delta is reported as "nothing new")
  instead of failing the scan.
- **TASK-50**: ``new_findings`` stays first-seen vs the union of earlier
  same-scope runs. ``resolved_findings`` and ``severity_up_count`` are vs the
  latest *completed* same-scope run. Webhook values stay scalar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from metatracer.db.models import Finding, severity_rank
from metatracer.db.repositories import FindingRepository, RunRepository
from metatracer.detectors.consolidator import finding_identity

logger = logging.getLogger("metatracer.services.watch")


@dataclass(slots=True)
class DeltaResult:
    """Outcome of a delta comparison; counters are 0 when nothing changed.

    ``None`` is never produced by :meth:`DeltaReporter.compute_delta` — that
    method either returns a result or raises. It is used as the default when
    the caller catches an error and cannot report a truthful number.
    """

    new_findings: int = 0
    resolved_findings: int = 0
    severity_up_count: int = 0
    # The signatures that are new in this run (useful for logging/debugging
    # only; never shipped to the webhook payload — the payload carries the
    # count, keeping PAYLOAD_KEYS scalar).
    new_signatures: list[str] = field(default_factory=list)
    previous_run_id: str | None = None


class DeltaReporter:
    """Computes deterministic finding deltas between runs of the same scope.

    ``session_factory`` is the same short-lived async session factory the
    rest of the app uses. The comparison is local-only and read-only.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def compute_delta(self, run_id: str) -> DeltaResult:
        """Return new / resolved / severity-up counts for ``run_id``.

        Baseline for *new* = every other run with the same ``allowed_scope``.
        Pairwise snapshot for *resolved* and *severity_up* = latest completed
        run of that snapshot excluding this one. Deterministic, no LLM.
        """
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get(run_id)
            if run is None:
                # A vanished run cannot be compared; the caller degrades to
                # "unknown delta" instead of failing the watch loop.
                raise LookupError(f"run not found: {run_id}")
            finding_repo = FindingRepository(session)
            current = await finding_repo.with_asset_url([run_id])
            baseline_ids = await repo.ids_with_scope(run.allowed_scope, exclude_id=run_id)
            baseline = await finding_repo.with_asset_url(baseline_ids)
            previous_id = await repo.latest_completed_id_with_scope(
                run.allowed_scope, exclude_id=run_id
            )
            previous = (
                await finding_repo.with_asset_url([previous_id]) if previous_id else []
            )

            current_map = _index(current)
            known = set(_index(baseline))
            previous_map = _index(previous)

            fresh = {
                finding.dedup_signature
                for finding, url in current
                if _identity(finding, url) not in known
            }
            new_signatures = sorted(fresh)
            resolved = sum(1 for ident in previous_map if ident not in current_map)
            severity_up = sum(
                1
                for ident, prior in previous_map.items()
                if ident in current_map and _is_severity_up(prior, current_map[ident])
            )
            return DeltaResult(
                new_findings=len(new_signatures),
                resolved_findings=resolved,
                severity_up_count=severity_up,
                new_signatures=new_signatures,
                previous_run_id=previous_id,
            )


def _identity(finding: Finding, url: str) -> str:
    return finding_identity(url, finding.finding_type, finding.evidence_snippet)


def _index(rows: list[tuple[Finding, str]]) -> dict[str, Finding]:
    indexed: dict[str, Finding] = {}
    for finding, url in rows:
        indexed.setdefault(_identity(finding, url), finding)
    return indexed


def _is_severity_up(previous: Finding, current: Finding) -> bool:
    if previous.severity is None or current.severity is None:
        return False
    return severity_rank(current.severity) > severity_rank(previous.severity)
