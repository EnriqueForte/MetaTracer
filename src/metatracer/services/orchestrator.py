"""ScanOrchestratorService: the single pipeline entry point for CLI and API (TASK-06, 6.1).

Both interfaces drive the same fixed stage sequence over one persisted Run::

    scope_validation -> discovery -> downloading -> extraction -> detection
    -> ai_analysis -> report_generation -> completed | failed

Two consumption styles, one pipeline:

- :meth:`scan` (CLI) runs the pipeline to completion and returns the
  :class:`ScanResult`.
- :meth:`start_scan` (API) applies the same gates, creates the Run and
  schedules the pipeline as a background asyncio task, returning the run_id
  immediately so ``POST /api/runs`` can answer 202. The terminal state is
  persisted on the Run row and published through ``on_progress`` exactly like
  the synchronous path — the interfaces can never diverge.

Stage-to-pipeline mapping (documented decisions):

- ``discovery`` / ``downloading`` / ``extraction`` all map to the atomic
  ``IngestionPipeline`` (TASK-01, not modified in this slice): the orchestrator
  emits ``discovery`` when ingestion starts and ``downloading`` / ``extraction``
  when it returns, carrying the real ``IngestionSummary`` counters. Per-asset
  progress (``current_asset``) stays ``None`` until the pipelines expose
  callbacks of their own.
- ``ai_analysis`` covers the heuristic classification (TASK-03) plus the agent
  phase (TASK-05, heuristic fallback included — it never fails the run).

Failure semantics:

- ``scope_confirmed=False`` raises :class:`ScopeNotConfirmedError` BEFORE the
  Run row exists: no database write, no network traffic (inviolable rule 1).
  The scope is never inferred from the targets.
- A scan when every concurrency slot is busy raises
  :class:`ScanAlreadyRunningError` (default limit 1 = the historical single
  lock; since TASK-23 Eje B the limit is ``METATRACER_MAX_CONCURRENT_RUNS``).
  The API maps it to HTTP 409.
- Once the Run exists, safety exceptions (``ScopeNotConfirmedError``,
  ``SecurityViolationError``) and any unexpected orchestration error do NOT
  propagate: the run is finalized as ``failed`` with a sanitized
  ``error_message`` and a :class:`ScanResult` carrying the failure is returned,
  so the CLI/API can point the operator at the persisted run. Per-asset
  failures never reach this layer (inviolable rule 5).
- If persisting the Run itself fails (e.g. database unreachable) the exception
  propagates: there is no row to finalize and nothing to report against.

Progress: ``on_progress`` is a plain synchronous callback invoked with each
:class:`ProgressEvent`; the CLI renders it with Rich and the API bridges it to
an ``asyncio.Queue`` for SSE (see ``services/progress.py``). A misbehaving
callback is logged and swallowed — a rendering bug must never kill a scan.
Messages are English and built only from counters and enum values; any future
target-controlled value MUST go through ``sanitize_for_log`` before landing in
``message``/``current_asset`` (threat 13, log/console injection).
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.agents.pipeline import AgentPipeline, AgentSummary
from metatracer.classification.pipeline import ClassificationPipeline, ClassificationSummary
from metatracer.core.config import Settings
from metatracer.core.exceptions import (
    MetaTracerError,
    RunNotAbortableError,
    RunNotFoundError,
    ScanAlreadyRunningError,
    ScopeNotConfirmedError,
    ScopeNotFoundError,
    SecurityViolationError,
)
from metatracer.core.logging import sanitize_for_log, set_run_context
from metatracer.core.safety.scope import assert_registrable_scope
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import ExtractionStatus, ReasoningDepth, Run, RunStatus
from metatracer.db.repositories import AssetRepository, RunRepository
from metatracer.detectors.pipeline import DetectionPipeline
from metatracer.extractors.budget import CrawlBudget
from metatracer.extractors.ingest import _EXTRACTION_INCOMPLETE, IngestionPipeline
from metatracer.reports.bounty import BountyExporter
from metatracer.reports.builder import DEFAULT_REPORTS_DIR, ReportBuilder
from metatracer.reports.csv_exporter import CsvReportExporter
from metatracer.reports.disclosure import Redaction, apply_redaction
from metatracer.reports.html import HtmlReportExporter
from metatracer.reports.json_exporter import JsonReportExporter
from metatracer.reports.markdown import MarkdownReportExporter
from metatracer.services.notifications import NotificationBus, NotificationEvent

logger = logging.getLogger("metatracer.services.orchestrator")

# Exact strings persisted on Run.error_message (TASK-28). Recovery is the
# restart case; the other two are operator abort and process shutdown.
INTERRUPTED_MESSAGE = "interrupted: process restarted"
OPERATOR_ABORT_MESSAGE = "aborted by operator"
SHUTDOWN_ABORT_MESSAGE = "aborted: server shutting down"
_ABORTED_ASSET_MESSAGE = "aborted before extraction finished"
_TERMINAL_STATUSES = frozenset(
    {RunStatus.completed, RunStatus.failed, RunStatus.aborted}
)


class ProgressStage(StrEnum):
    """Ordered stages of one scan; ``completed``/``failed``/``aborted`` are terminal.

    StrEnum per the repo convention (ruff UP042); values are the lowercase
    strings of the task contract. ``aborted`` is a terminal stream event
    distinct from ``failed`` (TASK-28): the persisted ``Run.status`` and the
    SSE stage use the same word.
    """

    scope_validation = "scope_validation"
    discovery = "discovery"
    downloading = "downloading"
    extraction = "extraction"
    detection = "detection"
    ai_analysis = "ai_analysis"
    report_generation = "report_generation"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


# The work stages in execution order; ``completed``/``failed`` are terminal
# events, not steps. ``current_step`` of a terminal event is the step the run
# reached (TOTAL_STEPS for ``completed``, the failing step for ``failed``).
_PIPELINE_STAGES: tuple[ProgressStage, ...] = (
    ProgressStage.scope_validation,
    ProgressStage.discovery,
    ProgressStage.downloading,
    ProgressStage.extraction,
    ProgressStage.detection,
    ProgressStage.ai_analysis,
    ProgressStage.report_generation,
)
TOTAL_STEPS = len(_PIPELINE_STAGES)
_STEP_NUMBER = {stage: index + 1 for index, stage in enumerate(_PIPELINE_STAGES)}


class ProgressEvent(BaseModel):
    """One progress tick, shared verbatim by the CLI renderer and the SSE stream."""

    run_id: str
    stage: ProgressStage
    current_step: int
    total_steps: int
    message: str
    current_asset: str | None = None


class ExportFormat(StrEnum):
    """Report formats the orchestrator can write (``all`` = md + json + html + csv + bounty)."""

    md = "md"
    json = "json"
    html = "html"
    csv = "csv"
    bounty = "bounty"
    all = "all"


class ScanRequest(BaseModel):
    """Validated scan parameters; also the exact POST /api/runs body (6.3).

    At least one target and one confirmed scope source are required, and the
    scope is a deliberate operator input — it is never derived from the
    targets. The scope source is exactly one of: manual `scope_domains`
    (v1.x), a single saved `scope_id` (TASK-10, v2.0) or the union of many
    saved scopes `scope_ids` (TASK-21, v2.4); never a mix. `scope_id` is
    kept as an alias of ``scope_ids=[scope_id]`` at the boundary, so none of
    the v2.0-v2.3 clients break. Export options are NOT part of this
    contract: they are parameters of
    :meth:`ScanOrchestratorService.scan`, so the API request body stays
    exactly this model.
    """

    targets: list[str] = Field(min_length=1)
    # Optional now: when scope_id/scope_ids is set, scope_domains must be
    # absent, and the resolver supplies the domains. A request with neither
    # is invalid.
    scope_domains: list[str] | None = None
    scope_confirmed: bool
    reasoning_depth: ReasoningDepth = ReasoningDepth.standard
    # TASK-10 (v2.0): optional reference to a single persisted named scope.
    # When set, the orchestrator resolves it to its domains and ignores
    # scope_domains; exactly one of {scope_domains, scope_id, scope_ids} is
    # allowed per request. Kept for wire compatibility with v2.0-v2.3.
    scope_id: str | None = None
    # TASK-21 (v2.4): multi-engagement — optional union of many persisted
    # named scopes, resolved by the orchestrator into one deduplicated
    # allowed_scope snapshot. Never mixed with scope_domains/scope_id.
    scope_ids: list[str] | None = None
    # TASK-22 (v3.0, Eje A): marks this scan as a headless watch iteration.
    # The orchestrator then computes the deterministic finding delta (vs.
    # earlier runs of the same scope) and carries ``new_findings`` on the
    # terminal webhook payload. Pipeline stages and safety gates are
    # identical; only the notification gains the delta counter.
    watch: bool = False
    # Fase 2: explicit crawl limits. Absent (None) keeps the historical
    # behaviour — one page, the configured asset cap — and is the reason an
    # existing client keeps working unchanged. The resolved snapshot is
    # persisted on the Run so the coverage view can say which limit stopped it.
    budget: CrawlBudget | None = None

    @field_validator("targets", "scope_domains")
    @classmethod
    def _non_blank_entries(cls, values: list[str] | None) -> list[str] | None:
        """Strip entries and reject blank ones (whitespace is not a target).

        ``None`` passes through unchanged: a request that uses ``scope_id``/
        ``scope_ids`` legitimately ships ``scope_domains=None``.
        """
        if values is None:
            return None
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("entries must be non-blank strings")
        return cleaned

    @field_validator("scope_domains")
    @classmethod
    def _scope_domains_are_registrable(cls, values: list[str] | None) -> list[str] | None:
        """Reject one-label bases (``com``, ``*.com``) at request time."""
        if values is None:
            return None
        for value in values:
            assert_registrable_scope(value)
        return values

    @field_validator("scope_ids")
    @classmethod
    def _valid_scope_ids(cls, values: list[str] | None) -> list[str] | None:
        """Reject blank ids; each entry must be a non-empty UUID4-shaped string.

        The actual existence check happens at resolution time in the
        orchestrator (any unknown id -> 404). Here we only keep the contract
        strict: no empty list, no blank entries.
        """
        if values is None:
            return None
        cleaned = [str(value).strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("scope ids must be non-blank strings")
        return cleaned or None  # scope_ids=[] normalizes to None = no scope source

    @model_validator(mode="after")
    def _exactly_one_scope_source(self) -> "ScanRequest":
        """The operator chooses manual `scope_domains`, one saved `scope_id` or
        the union `scope_ids`, never a mix.

        Rejects: any combination of two or more sources, or none at all (the
        scope is never inferred from the target, and an absent scope is never
        silently empty). ``scope_id`` is normalized into ``scope_ids`` so the
        orchestrator has a single resolution path.
        """
        sources = [
            source
            for source in (self.scope_domains, self.scope_id, self.scope_ids)
            if source
        ]
        if len(sources) > 1:
            raise ValueError("set exactly one of scope_domains, scope_id or scope_ids, not a mix")
        if not sources:
            raise ValueError("either scope_domains, scope_id or scope_ids is required")
        if self.scope_id is not None:
            self.scope_ids = [self.scope_id]
            self.scope_id = None
        return self


class ScanResult(BaseModel):
    """Terminal outcome of one scan; ``report_paths`` maps format -> file written."""

    run_id: str
    status: RunStatus
    total_assets: int
    total_findings: int
    report_paths: dict[str, Path] = Field(default_factory=dict)
    error_message: str | None = None


class ScanOrchestratorService:
    """Runs the fixed MetaTracer pipeline for one :class:`ScanRequest` at a time.

    The service never creates the database engine: ``session_factory`` and
    ``settings`` are injected, exactly like the pipelines it composes. The
    optional pipeline injections exist for tests — the same pattern as the
    pipelines' own optional guard/registry/client arguments.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        ingestion: IngestionPipeline | None = None,
        detection: DetectionPipeline | None = None,
        classification: ClassificationPipeline | None = None,
        agents: AgentPipeline | None = None,
        notifications: NotificationBus | None = None,
        webhooks: Any | None = None,
        knowledge: KnowledgeRetriever | None = None,
        delta_reporter: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._ingestion = (
            ingestion if ingestion is not None else IngestionPipeline(session_factory, settings)
        )
        self._detection = detection if detection is not None else DetectionPipeline(session_factory)
        self._classification = (
            classification
            if classification is not None
            else ClassificationPipeline(session_factory)
        )
        self._agents = (
            agents
            if agents is not None
            else AgentPipeline(session_factory, settings, knowledge=knowledge)
        )
        self._knowledge = knowledge
        # TASK-12 (v2.0): optional in-memory notification bus. Injected like
        # on_progress: the pipeline never knows it exists and a broken bus
        # never kills the scan (inviolable rule 5).
        self._notifications = notifications
        # TASK-15 (v2.2): optional outbound webhook dispatcher, injected like
        # the notification bus. ``None`` is a strict no-op — the pipeline never
        # knows it exists and a broken dispatcher never fails a scan.
        self._webhooks = webhooks
        # TASK-22 (v3.0, Eje A): optional deterministic delta reporter. When a
        # watch scan finishes, the orchestrator asks it for ``new_findings``
        # and forwards the count on the terminal webhook payload. A missing
        # reporter (all non-watch runs) never touches the pipeline.
        self._delta_reporter = delta_reporter
        self._active_run_id: str | None = None
        # TASK-22 (v3.0, Eje A): ids of the scans currently running as watch
        # iterations. Per-run (TASK-23) so concurrent runs cannot clobber each
        # other's flag; used by _notify_run_finished to attach the delta
        # counter to the terminal webhook payload.
        self._watch_run_ids: set[str] = set()
        self._background_tasks: set[asyncio.Task[None]] = set()
        # TASK-23 (Eje B): bounded concurrency. max_concurrent_runs=1 (the
        # default) degrades to the exact v1-v2.4 single-scan lock; >1 allows
        # several scans in parallel (Postgres backend recommended; with SQLite
        # the writers serialize at the database level anyway).
        limit = max(1, settings.max_concurrent_runs)
        self._run_slots = asyncio.Semaphore(limit)
        self._active_run_ids: set[str] = set()
        # Instant this process's orchestrator booted. Recovery only aborts
        # open runs started strictly earlier, so a scan this process creates
        # afterwards is not treated as an orphan (TASK-28).
        self._booted_at = datetime.now(UTC)
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._abort_messages: dict[str, str] = {}

    @property
    def active_run_id(self) -> str | None:
        """Run currently holding the single-scan lock, or None when idle."""
        return self._active_run_id

    async def scan(
        self,
        request: ScanRequest,
        *,
        formats: ExportFormat = ExportFormat.all,
        output_dir: str | Path = DEFAULT_REPORTS_DIR,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> ScanResult:
        """Execute the full pipeline to completion (the CLI path).

        See the module docstring for the failure semantics; a run slot is
        held for the whole scan and released before returning.
        """
        run = await self._begin_scan(request)
        if request.watch:
            self._watch_run_ids.add(run.id)
        try:
            return await self._execute_pipeline(
                run,
                request,
                formats=formats,
                output_dir=Path(output_dir),
                on_progress=on_progress,
            )
        finally:
            self._end_scan(run.id)

    async def start_scan(
        self,
        request: ScanRequest,
        *,
        formats: ExportFormat = ExportFormat.all,
        output_dir: str | Path = DEFAULT_REPORTS_DIR,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> str:
        """Create the Run and schedule the pipeline as a background task (the API path).

        Returns the new run_id immediately so ``POST /api/runs`` can answer
        202. :class:`ScopeNotConfirmedError` and :class:`ScanAlreadyRunningError`
        raise synchronously — before any row or task exists — which the API
        maps to 403/409. The scan's terminal state is persisted on the Run row
        and published through ``on_progress`` exactly like the CLI path.
        """
        run = await self._begin_scan(request)
        if request.watch:
            self._watch_run_ids.add(run.id)
        task = asyncio.create_task(
            self._run_background(run, request, formats, Path(output_dir), on_progress)
        )
        # Strong reference until completion: the event loop only weakly
        # references tasks. ``_run_tasks`` lets abort() cancel one run.
        self._run_tasks[run.id] = task
        self._background_tasks.add(task)

        def _discard(done: asyncio.Task[None], run_id: str = run.id) -> None:
            self._background_tasks.discard(done)
            self._run_tasks.pop(run_id, None)

        task.add_done_callback(_discard)
        return run.id

    async def shutdown(self) -> None:
        """Cancel background scans and persist them as ``aborted`` (TASK-28)."""
        for run_id in list(self._run_tasks):
            self._abort_messages.setdefault(run_id, SHUTDOWN_ABORT_MESSAGE)
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def recover_interrupted_runs(self) -> list[str]:
        """Mark other processes' open runs ``aborted`` and notify like a normal abort.

        Only rows with ``started_at`` strictly before this orchestrator booted
        are touched, and never a run this process is currently executing.

        Multi-process limitation: with PostgreSQL and
        ``METATRACER_MAX_CONCURRENT_RUNS>1``, concurrency slots are in-memory.
        A second process that boots later will abort this process's runs that
        started before the second boot. A run another process starts after
        this boot is left alone. This is not a cross-process lock.
        """
        async with self._session_factory() as session:
            runs = await RunRepository(session).list_open_started_before(self._booted_at)
        recovered: list[str] = []
        for run in runs:
            if run.id in self._active_run_ids or run.id in self._run_tasks:
                continue
            await self._settle_incomplete_assets(run.id)
            await self._finalize_run(run.id, RunStatus.aborted, INTERRUPTED_MESSAGE)
            recovered.append(run.id)
            logger.warning("recovered interrupted run %s as aborted", run.id)
        return recovered

    async def abort(self, run_id: str) -> Run:
        """Cancel one in-process scan, or persist ``aborted`` if it has no task.

        Raises :class:`RunNotFoundError` (API 404) and
        :class:`RunNotAbortableError` when the row is already terminal (API 409).
        """
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.status in _TERMINAL_STATUSES:
            raise RunNotAbortableError(run_id, run.status.value)
        self._abort_messages[run_id] = OPERATOR_ABORT_MESSAGE
        task = self._run_tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        else:
            await self._settle_incomplete_assets(run_id)
            await self._finalize_run(run_id, RunStatus.aborted, OPERATOR_ABORT_MESSAGE)
        async with self._session_factory() as session:
            fresh = await RunRepository(session).get(run_id)
        if fresh is None:  # pragma: no cover - the row existed above
            raise RunNotFoundError(run_id)
        return fresh

    async def export_report(
        self,
        run_id: str,
        *,
        formats: ExportFormat = ExportFormat.all,
        output_dir: str | Path = DEFAULT_REPORTS_DIR,
        include_false_positives: bool = False,
        redact: Redaction = Redaction.none,
    ) -> dict[str, Path]:
        """Re-export the reports of an already persisted run (CLI ``report`` / API export).

        Raises :class:`MetaTracerError` when the run does not exist (raised by
        the ReportBuilder). Read-only apart from the files written under
        ``output_dir``; works for runs in any status. Findings triaged as
        ``false_positive`` are left out unless ``include_false_positives``.
        """
        return await self._export_reports(
            run_id,
            formats,
            Path(output_dir),
            include_false_positives=include_false_positives,
            redact=redact,
        )

    async def _run_background(
        self,
        run: Run,
        request: ScanRequest,
        formats: ExportFormat,
        output_dir: Path,
        on_progress: Callable[[ProgressEvent], None] | None,
    ) -> None:
        """Task body for start_scan: run the pipeline and always release the slot."""
        try:
            await self._execute_pipeline(
                run, request, formats=formats, output_dir=output_dir, on_progress=on_progress
            )
        except Exception:
            # Defense in depth: _execute_pipeline already finalizes the run as
            # failed for every expected failure mode.
            logger.exception("background scan crashed")
        finally:
            self._end_scan(run.id)

    async def _begin_scan(self, request: ScanRequest) -> Run:
        """Scope gate + concurrency semaphore + Run creation, in that order.

        Raises before any side effect when the gate fails: no Run row, no HTTP
        (inviolable rule 1). With the default ``max_concurrent_runs=1`` the
        semaphore degenerates to the historical single-scan lock: a second
        scan raises :class:`ScanAlreadyRunningError` immediately (never
        queues). With a higher limit, up to N scans run in parallel.
        """
        if not request.scope_confirmed:
            raise ScopeNotConfirmedError(
                "scan requires scope_confirmed=True; the operator must explicitly "
                "confirm authorization before any database write or network traffic"
            )
        if self._run_slots.locked():
            # Non-blocking check: when every slot is busy, reject instead of
            # queueing (the API surfaces 409 with the active run ids).
            raise ScanAlreadyRunningError(sorted(self._active_run_ids))
        await self._run_slots.acquire()
        try:
            run = await self._create_run(request)
        except Exception:
            self._run_slots.release()
            raise
        self._active_run_ids.add(run.id)
        self._active_run_id = run.id
        set_run_context(run.id)
        return run

    def _end_scan(self, run_id: str | None = None) -> None:
        """Release one scan slot and drop the run from the active set."""
        if run_id is not None:
            self._active_run_ids.discard(run_id)
            self._watch_run_ids.discard(run_id)
        if self._active_run_id == run_id or run_id is None:
            # Keep pointing at some still-active run when N > 1; None when idle.
            remaining = sorted(self._active_run_ids)
            self._active_run_id = remaining[-1] if remaining else None
        self._run_slots.release()

    @staticmethod
    def _authorized_domains(run: Run, request: ScanRequest) -> list[str]:
        """The operator-confirmed authorized domains for this run, for messaging.

        The persisted ``Run.allowed_scope`` is the single source of truth: it
        already holds the resolved union when the scan used saved scopes
        (``request.scope_ids``), where ``request.scope_domains`` is ``None`` by
        contract. Falls back to the request for the legacy manual path and
        degrades to ``[]`` on a corrupt row (inviolable rule 5).
        """
        if request.scope_domains is not None:
            return request.scope_domains
        try:
            domains = json.loads(run.allowed_scope or "[]")
        except json.JSONDecodeError:  # pragma: no cover - corrupt allowed_scope
            return []
        return [str(domain) for domain in domains] if domains else []

    async def _execute_pipeline(
        self,
        run: Run,
        request: ScanRequest,
        *,
        formats: ExportFormat,
        output_dir: Path,
        on_progress: Callable[[ProgressEvent], None] | None,
    ) -> ScanResult:
        """The fixed stage sequence over one persisted Run (lock already held)."""
        current_step = _STEP_NUMBER[ProgressStage.scope_validation]
        try:
            self._emit(
                on_progress,
                run.id,
                ProgressStage.scope_validation,
                f"Scope confirmed by the operator: {len(request.targets)} target(s), "
                f"{len(self._authorized_domains(run, request))} authorized domain(s)",
            )
            await self._set_running(run.id)

            self._emit(
                on_progress,
                run.id,
                ProgressStage.discovery,
                "Discovering, downloading and extracting in-scope documents",
            )
            ingestion = await self._ingestion.execute(run.id)
            current_step = _STEP_NUMBER[ProgressStage.downloading]
            self._emit(
                on_progress,
                run.id,
                ProgressStage.downloading,
                f"Downloads complete: {ingestion.total_assets} asset(s) "
                f"({ingestion.assets_failed} failed, {ingestion.assets_skipped} skipped)",
            )
            current_step = _STEP_NUMBER[ProgressStage.extraction]
            self._emit(
                on_progress,
                run.id,
                ProgressStage.extraction,
                f"Metadata extraction complete: {ingestion.assets_ok} asset(s) extracted",
            )

            current_step = _STEP_NUMBER[ProgressStage.detection]
            self._emit(
                on_progress, run.id, ProgressStage.detection, "Running the metadata detectors"
            )
            detection = await self._detection.execute(run.id)
            self._emit(
                on_progress,
                run.id,
                ProgressStage.detection,
                f"Detection complete: {detection.findings_total} finding(s)",
            )

            current_step = _STEP_NUMBER[ProgressStage.ai_analysis]
            self._emit(
                on_progress,
                run.id,
                ProgressStage.ai_analysis,
                "Classifying findings and running AI analysis",
            )
            classification = await self._classification.execute(run.id)
            agents = await self._agents.execute(run.id)
            self._emit(
                on_progress,
                run.id,
                ProgressStage.ai_analysis,
                _analysis_message(classification, agents),
            )

            current_step = _STEP_NUMBER[ProgressStage.report_generation]
            self._emit(
                on_progress,
                run.id,
                ProgressStage.report_generation,
                "Writing report file(s)",
            )
            report_paths = await self._export_reports(run.id, formats, output_dir)
            self._emit(
                on_progress,
                run.id,
                ProgressStage.report_generation,
                f"Report generation complete: {len(report_paths)} file(s) written",
            )

            finished = await self._finalize_run(run.id, RunStatus.completed, None)
            self._emit(
                on_progress,
                run.id,
                ProgressStage.completed,
                f"Scan completed: {finished.total_findings} finding(s) across "
                f"{finished.total_assets} asset(s)",
                step=TOTAL_STEPS,
            )
            return ScanResult(
                run_id=run.id,
                status=RunStatus.completed,
                total_assets=finished.total_assets,
                total_findings=finished.total_findings,
                report_paths=report_paths,
            )
        except asyncio.CancelledError:
            # Ctrl+C, POST /abort and shutdown all land here. Uncancel so the
            # persist can await, then re-raise so the CLI/watch loop stops.
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            message = self._abort_messages.pop(run.id, OPERATOR_ABORT_MESSAGE)
            await self._settle_incomplete_assets(run.id)
            await self._fail(
                run.id, current_step, message, on_progress, status=RunStatus.aborted
            )
            raise
        except (ScopeNotConfirmedError, SecurityViolationError) as exc:
            # Safety aborts are expected control flow: clear message, no traceback.
            # Persisted as ``aborted``, not ``failed``, so clients can tell a
            # safety stop from an infrastructure error without parsing the text.
            message = sanitize_for_log(exc, max_length=500)
            logger.error("scan aborted by the safety layer: %s", message)
            return await self._fail(
                run.id, current_step, message, on_progress, status=RunStatus.aborted
            )
        except Exception as exc:
            # Orchestration bug or infrastructure failure: fail the run loudly
            # with a sanitized message and keep the traceback in the log.
            message = f"unexpected {type(exc).__name__}: {sanitize_for_log(exc, 400)}"
            logger.exception("scan failed")
            return await self._fail(run.id, current_step, message, on_progress)

    async def _export_reports(
        self,
        run_id: str,
        formats: ExportFormat,
        output_dir: Path,
        *,
        include_false_positives: bool = False,
        redact: Redaction = Redaction.none,
    ) -> dict[str, Path]:
        """Build the ReportData once and write the requested formats from it.

        Both exporters derive the file name from the same ``generated_at``, so
        the Markdown/JSON pair of one export shares its timestamped stem.
        """
        data = await ReportBuilder(self._session_factory).build(
            run_id, include_false_positives=include_false_positives
        )
        data = apply_redaction(data, redact)
        paths: dict[str, Path] = {}
        if formats in (ExportFormat.md, ExportFormat.all):
            paths["md"] = MarkdownReportExporter(output_dir).export(data)
        if formats in (ExportFormat.json, ExportFormat.all):
            paths["json"] = JsonReportExporter(output_dir).export(data)
        if formats in (ExportFormat.html, ExportFormat.all):
            paths["html"] = HtmlReportExporter(output_dir).export(data)
        if formats in (ExportFormat.csv, ExportFormat.all):
            paths["csv"] = CsvReportExporter(output_dir).export(data)
        if formats in (ExportFormat.bounty, ExportFormat.all):
            paths["bounty"] = BountyExporter(output_dir).export(data)
        return paths

    async def _fail(
        self,
        run_id: str,
        current_step: int,
        message: str,
        on_progress: Callable[[ProgressEvent], None] | None,
        *,
        status: RunStatus = RunStatus.failed,
    ) -> ScanResult:
        """Finalize a terminal non-success and return it as a ScanResult.

        ``status`` is ``aborted`` for a safety exception or an operator stop,
        and ``failed`` for anything else. The SSE stage matches that status
        (``aborted`` or ``failed``) so clients can tell them apart.
        """
        finished = await self._finalize_run(run_id, status, message)
        if status is RunStatus.aborted:
            stage = ProgressStage.aborted
            label = "Scan aborted"
        else:
            stage = ProgressStage.failed
            label = "Scan failed"
        self._emit(
            on_progress,
            run_id,
            stage,
            f"{label}: {message}",
            step=current_step,
        )
        return ScanResult(
            run_id=run_id,
            status=status,
            total_assets=finished.total_assets,
            total_findings=finished.total_findings,
            error_message=message,
        )

    async def _create_run(self, request: ScanRequest) -> Run:
        """Persist the Run as ``pending`` with the operator-confirmed scope.

        TASK-10 (v2.0) / TASK-21 (v2.4): when ``request.scope_ids`` is set
        (single id or a multi-engagement union), the persisted scopes' domains
        are copied onto the Run (never referenced by FK), so later
        edits/deletes of the Scope cannot alter past runs — the Run owns its
        scope snapshot. ``scope_id`` was already normalized into one-element
        ``scope_ids`` by :class:`ScanRequest`.

        Fase 2: the resolved crawl budget is snapshotted onto the Run as the
        initial ``ingestion_stats`` (counters still zero). Ingestion reads it
        back, so what the coverage view shows is exactly what the operator
        authorised — editing a later default never rewrites a past run.
        """
        scope_domains = request.scope_domains or []
        if request.scope_ids is not None:
            scope_domains = await self._resolve_scope_domains_many(request.scope_ids)
        budget = request.budget or CrawlBudget.from_settings(self._settings)
        async with self._session_factory() as session:
            return await RunRepository(session).create(
                Run(
                    target_input=json.dumps(request.targets),
                    allowed_scope=json.dumps(scope_domains),
                    scope_confirmed=True,
                    reasoning_depth=request.reasoning_depth,
                    ingestion_stats=json.dumps(
                        {"budget": budget.describe(), "limits_hit": []}, ensure_ascii=False
                    ),
                )
            )

    async def _resolve_scope_domains_many(self, scope_ids: list[str]) -> list[str]:
        """Resolve the union of several persisted scopes into one domain list.

        TASK-21 (v2.4): multi-engagement — the run is authorized against the
        union of the operator-chosen saved scopes. Each id is loaded
        individually; an unknown id raises :class:`ScopeNotFoundError` (the
        message carries the scope name when the row exists, or the token when
        it doesn't) BEFORE any Run row exists, so ``POST /api/runs`` can
        answer 404. The union keeps a stable order and drops duplicates
        (``dict.fromkeys``). Listing/resolving scopes is local only — zero
        network, zero bytes persisted extra (inviolable rule 1).
        """
        from metatracer.db.repositories import ScopeRepository  # local: avoid import cycle

        async with self._session_factory() as session:
            repo = ScopeRepository(session)
            scopes: list[str] = []
            for scope_id in scope_ids:
                scope = await repo.get(scope_id)
                if scope is None:
                    raise ScopeNotFoundError(sanitize_for_log(scope_id))
                try:
                    domains = json.loads(scope.domains)
                except json.JSONDecodeError as exc:  # pragma: no cover - corrupt row
                    raise MetaTracerError("scope database row is corrupt") from exc
                if not domains:
                    raise MetaTracerError(f"scope '{scope.name}' has no domains configured")
                scopes.extend(str(domain) for domain in domains)
        # Stable deduplicated union: preserves the first occurrence order of
        # each domain, regardless of the scope that introduced it.
        union = list(dict.fromkeys(scopes))
        if not union:  # pragma: no cover - scopes require >=1 domain at write time
            raise MetaTracerError("scope union is empty")
        return union

    async def _settle_incomplete_assets(self, run_id: str) -> None:
        """Mark assets left mid-extraction when the scan stops (TASK-28).

        Ingestion persists the row as ``failed`` with a sentinel message
        before the parser runs. Those rows stay ``failed`` (extraction did
        not finish) but the message says the scan was aborted. Assets that
        already reached ``ok`` or ``skipped`` are left alone.
        """
        async with self._session_factory() as session:
            repo = AssetRepository(session)
            assets = await repo.list_by_run(run_id)
            for asset in assets:
                if (
                    asset.extraction_status is ExtractionStatus.failed
                    and asset.error_message == _EXTRACTION_INCOMPLETE
                ):
                    asset.error_message = _ABORTED_ASSET_MESSAGE
                    await repo.update(asset)

    async def _set_running(self, run_id: str) -> None:
        """Transition pending -> running before the first pipeline stage."""
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get(run_id)
            if run is None:  # pragma: no cover - defensive; we just created it
                raise MetaTracerError("run vanished during orchestration")
            if run.status in _TERMINAL_STATUSES:
                return
            run.status = RunStatus.running
            await repo.update(run)

    async def _finalize_run(
        self, run_id: str, status: RunStatus, error_message: str | None
    ) -> Run:
        """Persist the terminal status plus completion timestamp; return the fresh row.

        ``total_assets``/``total_findings`` are maintained by the ingestion and
        detection pipelines themselves; stages that never ran leave them at 0,
        which is the honest count for a run that failed early.

        TASK-12 (v2.0): this is the single terminal exit point for both
        ``completed`` and ``failed``, so the notification is emitted here —
        inside the same session, right after the final counters are persisted.
        """
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get(run_id)
            if run is None:  # pragma: no cover - defensive; we just created it
                raise MetaTracerError("run vanished during orchestration")
            if run.status in _TERMINAL_STATUSES:
                return run
            run.status = status
            run.completed_at = datetime.now(UTC)
            run.error_message = error_message
            finished = await repo.update(run)
        await self._notify_run_finished(finished, status, error_message)
        return finished

    async def _notify_run_finished(
        self, run: Run, status: RunStatus, error_message: str | None
    ) -> None:
        """Publish one terminal-run notification; a broken bus never kills the scan.

        Only the optional in-memory bus emits here: the CLI path renders the
        outcome on screen (the run is synchronous and terminal), so it wires no
        bus and this is a no-op. ``pending``/``running`` never notify.
        """
        if self._notifications is None and self._webhooks is None:
            return
        try:
            targets = (
                [str(t).strip() for t in json.loads(run.target_input) if str(t).strip()]
                if run.target_input
                else []
            )
            target = targets[0] if targets else "unknown"
            if self._notifications is not None:
                self._notifications.publish(
                    NotificationEvent(
                        id=0,  # the bus assigns the queue index on append
                        kind=status,
                        run_id=run.id,
                        target=target,
                        total_assets=run.total_assets,
                        total_findings=run.total_findings,
                        error_message=error_message,
                        created_at=run.completed_at or datetime.now(UTC),
                    )
                )
            # TASK-15 (v2.2): enqueue outbound webhooks for the same terminal
            # event. The dispatcher's HTTP sends run as background tasks, so
            # this never blocks or fails the scan (inviolable rule 5).
            if self._webhooks is not None:
                # TASK-22 (v3.0, Eje A): for a watch iteration, compute the
                # deterministic finding delta before enqueueing, so the
                # terminal payload carries ``new_findings``. A failure here
                # degrades to 0 (nothing new to report), never fails the scan
                # (inviolable rule 5).
                new_findings = 0
                if run.id in self._watch_run_ids and self._delta_reporter is not None:
                    try:
                        delta = await self._delta_reporter.compute_delta(run.id)
                        new_findings = delta.new_findings
                    except Exception:
                        logger.warning(
                            "watch delta computation failed; webhook without "
                            "new_findings",
                            exc_info=True,
                        )
                # The dispatcher exposes the same signature as the bus; an
                # unexpected error must not kill the finalize path.
                try:
                    await self._webhooks.enqueue_terminal(
                        run.id,
                        status,
                        target=target,
                        total_assets=run.total_assets,
                        total_findings=run.total_findings,
                        new_findings=new_findings,
                        executive_summary=run.executive_summary,
                        error_message=error_message,
                    )
                except Exception:
                    logger.warning(
                        "webhook enqueue failed; continuing scan", exc_info=True
                    )
        except Exception:
            logger.warning("notification publish failed; continuing scan", exc_info=True)

    def _emit(
        self,
        callback: Callable[[ProgressEvent], None] | None,
        run_id: str,
        stage: ProgressStage,
        message: str,
        *,
        step: int | None = None,
        current_asset: str | None = None,
    ) -> None:
        """Publish one ProgressEvent; a broken consumer never kills the scan."""
        if callback is None:
            return
        event = ProgressEvent(
            run_id=run_id,
            stage=stage,
            current_step=step if step is not None else _STEP_NUMBER[stage],
            total_steps=TOTAL_STEPS,
            message=message,
            current_asset=current_asset,
        )
        try:
            callback(event)
        except Exception:
            logger.warning("progress callback failed; continuing scan", exc_info=True)


def _analysis_message(classification: ClassificationSummary, agents: AgentSummary) -> str:
    """English exit message for the ai_analysis stage, built from counters only."""
    total = classification.findings_classified + classification.findings_already_classified
    if total == 0:
        return "Analysis complete: no findings to classify"
    return (
        f"Analysis complete: {total} finding(s) classified, "
        f"{agents.findings_evaluated} AI-evaluated, "
        f"{agents.findings_fallback} heuristic fallback"
    )


async def build_orchestrator(settings: Settings) -> ScanOrchestratorService:
    """Convenience wiring: create the engine, initialize the schema, return the service.

    The engine stays alive through the returned service's session factory and
    the caller owns its lifecycle (the FastAPI lifespan will hold it; the CLI
    manages its own engine explicitly so it can dispose it per command).
    """
    engine = create_db_engine(settings.database_url)
    await init_db(engine)
    return ScanOrchestratorService(create_session_factory(engine), settings)
