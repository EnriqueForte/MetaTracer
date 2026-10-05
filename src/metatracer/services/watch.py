"""Watch mode: headless re-scan with deterministic delta reporting (TASK-22, v3.0 Eje A).

The platform v3.0 Eje A (features/12-platform-v3.md) turns a one-shot scan
into a continuous engagement: ``metatracer watch`` re-scans a saved scope on
a cadence and only reports *deltas* — findings that did not exist in any
prior run of the same scope.

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
  failure degrades to ``new_findings=0`` (a missing delta is reported as
  "nothing new") instead of failing the scan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from metatracer.db.repositories import FindingRepository, RunRepository
from metatracer.detectors.consolidator import finding_identity

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
        this run. Deterministic, no LLM, no network.
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

        def identity(finding, url: str) -> str:
            return finding_identity(url, finding.finding_type, finding.evidence_snippet)

        known = {identity(finding, url) for finding, url in baseline}
        fresh = {
            finding.dedup_signature
            for finding, url in current
            if identity(finding, url) not in known
        }
        new_signatures = sorted(fresh)
        return DeltaResult(new_findings=len(new_signatures), new_signatures=new_signatures)
