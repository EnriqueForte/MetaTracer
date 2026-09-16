"""Watch mode: headless re-scan with deterministic delta reporting (TASK-22, v3.0 Eje A).

The platform v3.0 Eje A (features/12-platform-v3.md) turns a one-shot scan
into a continuous engagement: ``metatracer watch`` re-scans a saved scope on
a cadence and only reports *deltas* — findings that did not exist in any
prior run of the same scope.

Design contract:

- **Zero LLM, zero network**: the delta is a pure database comparison of
  ``dedup_signature`` sets. The signatures are already computed by the
  detectors (TASK-02), stable and indexed, so the comparison is deterministic.
- **Scope identity = the snapshot**: a Run persists ``allowed_scope`` as its
  own snapshot (TASK-10). The delta compares a run against every *other* run
  whose ``allowed_scope`` matches the same snapshot, so deleting/editing a
  Scope object never changes the historical baseline.
- **Rule 1 intact**: the watch never invents a scope. ``--scope <id>`` is the
  single source of scope, resolved by the exact same ``ScopeRepository`` the
  wizard uses; the pipeline's ``scope_confirmed`` gate is never bypassed.
- **Broken consumers never kill the scan** (inviolable rule 5): the delta is
  computed in the orchestrator's notify path inside a ``try/except``, and a
  failure degrades to ``new_findings=0`` (a missing delta is reported as
  "nothing new") instead of failing the scan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from metatracer.db.repositories import FindingRepository, RunRepository

logger = logging.getLogger("metatracer.services.watch")


@dataclass(slots=True)
class DeltaResult:
    """Outcome of a delta comparison; ``new_findings`` is 0 when nothing changed.

    ``None`` is never produced by :meth:`DeltaReporter.compute_delta` — that
    method either returns a result or raises. It is used as the default when
    the caller catches an error and cannot report a truthful number.
    """

    new_findings: int = 0
    # The signatures that are new in this run (useful for logging/debugging
    # only; never shipped to the webhook payload — the payload carries the
    # count, keeping PAYLOAD_KEYS scalar).
    new_signatures: list[str] = field(default_factory=list)


class DeltaReporter:
    """Computes deterministic finding deltas between runs of the same scope.

    ``session_factory`` is the same short-lived async session factory the
    rest of the app uses. The comparison is local-only and read-only.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def compute_delta(self, run_id: str) -> DeltaResult:
        """Return the findings of ``run_id`` that are new vs. earlier same-scope runs.

        Baseline = every run with the same ``allowed_scope`` snapshot EXCLUDING
        this run. ``new_signatures`` is the difference of the dedup sets:
        deterministic, no LLM, no network.
        """
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get(run_id)
            if run is None:
                # A vanished run cannot be compared; the caller degrades to
                # "unknown delta" instead of failing the watch loop.
                raise LookupError(f"run not found: {run_id}")
            scope_snapshot = run.allowed_scope
            finding_repo = FindingRepository(session)
            current = await finding_repo.list_by_run(run_id)
            current_signatures = {f.dedup_signature for f in current}

            # Historical runs with the same snapshot, excluding this one.
            history = await repo.list_recent(limit=None)
            baseline_runs = [
                r
                for r in history
                if r.allowed_scope == scope_snapshot and r.id != run_id
            ]
            baseline_signatures: set[str] = set()
            for prev in baseline_runs:
                prev_findings = await finding_repo.list_by_run(prev.id)
                baseline_signatures.update(f.dedup_signature for f in prev_findings)

        new_signatures = sorted(current_signatures - baseline_signatures)
        return DeltaResult(new_findings=len(new_signatures), new_signatures=new_signatures)