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
- A second concurrent scan raises :class:`ScanAlreadyRunningError`
  (``asyncio.Lock`` with non-blocking acquisition; SQLite has a single writer,
  tasks README known trap 6). The API maps it to HTTP 409.
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
    ScanAlreadyRunningError,
    ScopeNotConfirmedError,
    ScopeNotFoundError,
    SecurityViolationError,
)
from metatracer.core.logging import sanitize_for_log, set_run_context
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import ReasoningDepth, Run, RunStatus
from metatracer.db.repositories import RunRepository
from metatracer.detectors.pipeline import DetectionPipeline
from metatracer.extractors.ingest import IngestionPipeline
from metatracer.reports.bounty import BountyExporter
from metatracer.reports.builder import DEFAULT_REPORTS_DIR, ReportBuilder
from metatracer.reports.csv_exporter import CsvReportExporter
from metatracer.reports.html import HtmlReportExporter
from metatracer.reports.json_exporter import JsonReportExporter
from metatracer.reports.markdown import MarkdownReportExporter
from metatracer.services.notifications import NotificationBus, NotificationEvent

logger = logging.getLogger("metatracer.services.orchestrator")


class ProgressStage(StrEnum):
    """Ordered stages of one scan; ``completed``/``failed`` are terminal events.

    StrEnum per the repo convention (ruff UP042); values are the lowercase
    strings of the task contract.
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
    (v1.x) or a saved `scope_id` (TASK-10, v2.0); never both. Export options
    are NOT part of this contract: they are parameters of
    :meth:`ScanOrchestratorService.scan`, so the API request body stays
    exactly this model.
    """

    targets: list[str] = Field(min_length=1)
    # Optional now: when scope_id is set, scope_domains must be absent, and
    # the resolver supplies the domains. A request with neither is invalid.
    scope_domains: list[str] | None = None
    scope_confirmed: bool
    reasoning_depth: ReasoningDepth = ReasoningDepth.standard
    # TASK-10 (v2.0): optional reference to a persisted named scope. When set,
    # the orchestrator resolves it to its domains and ignores scope_domains;
    # exactly one of {scope_domains, scope_id} is allowed per request.
    scope_id: str | None = None

    @field_validator("targets", "scope_domains")
    @classmethod
    def _non_blank_entries(cls, values: list[str] | None) -> list[str] | None:
        """Strip entries and reject blank ones (whitespace is not a target).

        ``None`` passes through unchanged: a request that uses ``scope_id``
        legitimately ships ``scope_domains=None``.
        """
        if values is None:
            return None
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("entries must be non-blank strings")
        return cleaned

    @model_validator(mode="after")
    def _exactly_one_scope_source(self) -> "ScanRequest":
        """The operator chooses the manual `scope_domains` OR a saved `scope_id`, never both.

        Rejects: both set, or neither set (the scope is never inferred from
        the target, and an absent scope is never silently empty).
        """
        if self.scope_domains is not None and self.scope_id is not None:
            raise ValueError("set either scope_domains or scope_id, not both")
        if (self.scope_domains is None or not self.scope_domains) and self.scope_id is None:
            raise ValueError("either scope_domains or scope_id is required")
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
        self._lock = asyncio.Lock()
        self._active_run_id: str | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()

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

        See the module docstring for the failure semantics; the single-scan
        lock is held for the whole run and released before returning.
        """
        run = await self._begin_scan(request)
        try:
            return await self._execute_pipeline(
                run,
                request,
                formats=formats,
                output_dir=Path(output_dir),
                on_progress=on_progress,
            )
        finally:
            self._end_scan()

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
        task = asyncio.create_task(
            self._run_background(run, request, formats, Path(output_dir), on_progress)
        )
        # Strong reference until completion: the event loop only weakly
        # references tasks, and the set doubles as introspection for shutdown.
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return run.id

    async def shutdown(self) -> None:
        """Cancel background scans (API server shutdown).

        A cancelled scan keeps its last persisted status (``running``):
        recovery of interrupted runs is out of MVP scope (v1.1).
        """
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def export_report(
        self,
        run_id: str,
        *,
        formats: ExportFormat = ExportFormat.all,
        output_dir: str | Path = DEFAULT_REPORTS_DIR,
    ) -> dict[str, Path]:
        """Re-export the reports of an already persisted run (CLI ``report`` / API export).

        Raises :class:`MetaTracerError` when the run does not exist (raised by
        the ReportBuilder). Read-only apart from the files written under
        ``output_dir``; works for runs in any status.
        """
        return await self._export_reports(run_id, formats, Path(output_dir))

    async def _run_background(
        self,
        run: Run,
        request: ScanRequest,
        formats: ExportFormat,
        output_dir: Path,
        on_progress: Callable[[ProgressEvent], None] | None,
    ) -> None:
        """Task body for start_scan: run the pipeline and always release the lock."""
        try:
            await self._execute_pipeline(
                run, request, formats=formats, output_dir=output_dir, on_progress=on_progress
            )
        except Exception:
            # Defense in depth: _execute_pipeline already finalizes the run as
            # failed for every expected failure mode.
            logger.exception("background scan crashed")
        finally:
            self._end_scan()

    async def _begin_scan(self, request: ScanRequest) -> Run:
        """Scope gate + single-scan lock + Run creation, in that order.

        Raises before any side effect when the gate fails: no Run row, no HTTP
        (inviolable rule 1). The lock check-then-acquire is atomic in practice:
        acquiring a free ``asyncio.Lock`` completes without suspending, so no
        other coroutine can interleave between the check and the acquisition.
        """
        if not request.scope_confirmed:
            raise ScopeNotConfirmedError(
                "scan requires scope_confirmed=True; the operator must explicitly "
                "confirm authorization before any database write or network traffic"
            )
        if self._lock.locked():
            # Non-blocking acquisition: one active scan per process, never a queue.
            raise ScanAlreadyRunningError(self._active_run_id)
        await self._lock.acquire()
        try:
            run = await self._create_run(request)
        except Exception:
            self._lock.release()
            raise
        self._active_run_id = run.id
        set_run_context(run.id)
        return run

    def _end_scan(self) -> None:
        """Release the single-scan lock and clear the active-run marker."""
        self._active_run_id = None
        self._lock.release()

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
                f"{len(request.scope_domains)} authorized domain(s)",
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
        except (ScopeNotConfirmedError, SecurityViolationError) as exc:
            # Safety aborts are expected control flow: clear message, no traceback.
            message = sanitize_for_log(exc, max_length=500)
            logger.error("scan aborted by the safety layer: %s", message)
            return await self._fail(run.id, current_step, message, on_progress)
        except Exception as exc:
            # Orchestration bug or infrastructure failure: fail the run loudly
            # with a sanitized message and keep the traceback in the log.
            message = f"unexpected {type(exc).__name__}: {sanitize_for_log(exc, 400)}"
            logger.exception("scan failed")
            return await self._fail(run.id, current_step, message, on_progress)

    async def _export_reports(
        self, run_id: str, formats: ExportFormat, output_dir: Path
    ) -> dict[str, Path]:
        """Build the ReportData once and write the requested formats from it.

        Both exporters derive the file name from the same ``generated_at``, so
        the Markdown/JSON pair of one export shares its timestamped stem.
        """
        data = await ReportBuilder(self._session_factory).build(run_id)
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
    ) -> ScanResult:
        """Finalize the run as failed and return the failure as a ScanResult."""
        finished = await self._finalize_run(run_id, RunStatus.failed, message)
        self._emit(
            on_progress,
            run_id,
            ProgressStage.failed,
            f"Scan failed: {message}",
            step=current_step,
        )
        return ScanResult(
            run_id=run_id,
            status=RunStatus.failed,
            total_assets=finished.total_assets,
            total_findings=finished.total_findings,
            error_message=message,
        )

    async def _create_run(self, request: ScanRequest) -> Run:
        """Persist the Run as ``pending`` with the operator-confirmed scope.

        TASK-10: when ``request.scope_id`` is set, the persisted scope's
        domains are copied onto the Run (never referenced by FK), so later
        edits/deletes of the Scope cannot alter past runs — the Run owns its
        scope snapshot.
        """
        scope_domains = request.scope_domains or []
        if request.scope_id is not None:
            scope_domains = await self._resolve_scope_domains(request.scope_id)
        async with self._session_factory() as session:
            return await RunRepository(session).create(
                Run(
                    target_input=json.dumps(request.targets),
                    allowed_scope=json.dumps(scope_domains),
                    scope_confirmed=True,
                    reasoning_depth=request.reasoning_depth,
                )
            )

    async def _resolve_scope_domains(self, scope_id: str) -> list[str]:
        """Load a persisted scope's domains; unknown scope_id aborts the run.

        Raises :class:`MetaTracerError` before any Run row exists, so
        ``POST /api/runs`` with a bad scope_id answers 500 today — the API
        layer maps it to an explicit 404 (TASK-10, subtask 10.4 handles the
        request with a dedicated exception).
        """
        from metatracer.db.repositories import ScopeRepository  # local: avoid import cycle

        async with self._session_factory() as session:
            scope = await ScopeRepository(session).get(scope_id)
        if scope is None:
            raise ScopeNotFoundError(sanitize_for_log(scope_id))
        try:
            domains = json.loads(scope.domains)
        except json.JSONDecodeError as exc:  # pragma: no cover - corrupt row
            raise MetaTracerError("scope database row is corrupt") from exc
        if not domains:
            raise MetaTracerError("scope has no domains configured")
        return [str(domain) for domain in domains]

    async def _set_running(self, run_id: str) -> None:
        """Transition pending -> running before the first pipeline stage."""
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get(run_id)
            if run is None:  # pragma: no cover - defensive; we just created it
                raise MetaTracerError("run vanished during orchestration")
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
                # The dispatcher exposes the same signature as the bus; an
                # unexpected error must not kill the finalize path.
                try:
                    await self._webhooks.enqueue_terminal(
                        run.id,
                        status,
                        target=target,
                        total_assets=run.total_assets,
                        total_findings=run.total_findings,
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
