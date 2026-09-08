"""DetectionPipeline: from persisted raw metadata to persisted findings (TASK-02).

For every asset of the run whose extraction succeeded, the registry runs the
five detectors over its ``RawMetadataItem`` rows, the consolidator dedups the
drafts and the new findings are inserted. Re-running detection on the same run
inserts nothing: existing ``dedup_signature`` values are pre-filtered before
the insert — a portable way to "insert ignoring unique-constraint conflicts"
that works on SQLite and PostgreSQL alike, with the
``uq_finding_asset_dedup`` constraint kept as defense in depth.

This stage does no network I/O (scope is irrelevant here) and never opens the
original files: only structured metadata rows are read. ``severity`` stays
NULL on every inserted finding; ``Run.total_findings`` is recomputed at the
end. Sequential per-asset sessions, like the ingestion pipeline: SQLite has a
single writer in the MVP.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log, set_run_context
from metatracer.db.models import ExtractionStatus
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)
from metatracer.detectors.consolidator import consolidate_drafts
from metatracer.detectors.registry import DetectorRegistry

logger = logging.getLogger("metatracer.detectors.pipeline")


@dataclass(frozen=True, slots=True)
class DetectionSummary:
    """Counts of one detection phase, for the run log and future UI progress."""

    run_id: str
    assets_processed: int
    findings_new: int
    findings_total: int


class DetectionPipeline:
    """Runs the TASK-02 detection phase for one persisted Run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: DetectorRegistry | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry if registry is not None else DetectorRegistry()

    async def execute(self, run_id: str) -> DetectionSummary:
        """Detect findings on every successfully extracted asset of the run."""
        set_run_context(run_id)
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")

        async with self._session_factory() as session:
            assets = await AssetRepository(session).list_by_run(run_id)

        assets_processed = 0
        findings_new = 0
        for asset in assets:
            # Only successfully extracted assets have metadata worth scanning;
            # failed/skipped ones carry no RawMetadataItem rows by contract.
            if asset.extraction_status is not ExtractionStatus.ok:
                continue
            assets_processed += 1
            async with self._session_factory() as session:
                items = await RawMetadataRepository(session).list_by_asset(asset.id)
            drafts = self._registry.detect_all(items)
            findings = consolidate_drafts(run_id, asset.id, drafts)
            if not findings:
                continue
            async with self._session_factory() as session:
                repo = FindingRepository(session)
                existing = {f.dedup_signature for f in await repo.list_by_asset(asset.id)}
                fresh = [f for f in findings if f.dedup_signature not in existing]
                if fresh:
                    await repo.create_many(fresh)
                    findings_new += len(fresh)

        findings_total = await self._finalize_run(run_id)
        summary = DetectionSummary(
            run_id=run_id,
            assets_processed=assets_processed,
            findings_new=findings_new,
            findings_total=findings_total,
        )
        logger.info(
            "detection finished: %d assets processed, %d new findings (%d total)",
            assets_processed,
            findings_new,
            findings_total,
        )
        return summary

    async def _finalize_run(self, run_id: str) -> int:
        """Recompute Run.total_findings once the detection phase ends."""
        async with self._session_factory() as session:
            run_repo = RunRepository(session)
            total = len(await FindingRepository(session).list_by_run(run_id))
            run = await run_repo.get(run_id)
            if run is None:  # pragma: no cover - defensive; the run exists
                raise MetaTracerError("run vanished during detection")
            run.total_findings = total
            await run_repo.update(run)
            return total
