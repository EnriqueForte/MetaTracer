"""ClassificationPipeline: persist heuristic severities for a run (TASK-03).

For every finding of the run whose ``severity`` is still NULL, the pipeline
re-anchors the evidence against the asset's ``RawMetadataItem`` rows (rule
3.2.1: empty, unanchored or type-mismatched evidence is forced to ``info``),
runs the deterministic heuristic classifier and writes severity plus the
English template prose onto the finding. Findings already classified are
left untouched, so re-running the phase is a no-op.

Like the detection phase, this stage does no network I/O and never opens the
original files; sessions are sequential (SQLite has a single writer in the
MVP). ``agent_model_used`` stays empty: TASK-05 fills it, or sets
``heuristic-fallback`` when the agent path fails.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.classification.anchor import evidence_is_anchored
from metatracer.classification.classifier import (
    HeuristicRiskClassifier,
    apply_assessment,
    unanchored_assessment,
)
from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log, set_run_context
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)

logger = logging.getLogger("metatracer.classification.pipeline")


@dataclass(frozen=True, slots=True)
class ClassificationSummary:
    """Counts of one classification phase, for the run log and future UI."""

    run_id: str
    findings_classified: int
    findings_already_classified: int
    by_severity: dict[str, int] = field(default_factory=dict)


class ClassificationPipeline:
    """Runs the TASK-03 heuristic classification phase for one persisted Run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        classifier: HeuristicRiskClassifier | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._classifier = classifier if classifier is not None else HeuristicRiskClassifier()

    async def execute(self, run_id: str) -> ClassificationSummary:
        """Classify every finding of the run whose severity is still NULL."""
        set_run_context(run_id)
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")

        async with self._session_factory() as session:
            findings = await FindingRepository(session).list_by_run(run_id)

        by_severity: dict[str, int] = {}
        classified = 0
        already = 0
        for finding in findings:
            if finding.severity is not None:
                already += 1  # never re-baseline: TASK-05 may have refined it
                continue
            async with self._session_factory() as session:
                asset = await AssetRepository(session).get(finding.asset_id)
                items = await RawMetadataRepository(session).list_by_asset(finding.asset_id)
            if evidence_is_anchored(finding, items):
                assessment = self._classifier.classify(finding, asset)
            else:
                assessment = unanchored_assessment(finding, asset)
            apply_assessment(finding, assessment)
            async with self._session_factory() as session:
                await FindingRepository(session).update(finding)
            by_severity[str(assessment.severity)] = by_severity.get(str(assessment.severity), 0) + 1
            classified += 1

        summary = ClassificationSummary(
            run_id=run_id,
            findings_classified=classified,
            findings_already_classified=already,
            by_severity=by_severity,
        )
        logger.info(
            "classification finished: %d findings classified, %d already classified (%s)",
            classified,
            already,
            by_severity or "no pending findings",
        )
        return summary
