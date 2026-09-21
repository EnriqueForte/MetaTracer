"""MetaTracer CLI (TASK-06, subtask 6.2): ``scan``, ``report`` and ``list-runs``.

Thin Typer/Rich shell over :class:`ScanOrchestratorService`: commands parse
arguments, enforce the scope-confirmation gate, render progress and map the
outcome to an exit code. No business logic lives here — the service owns the
pipeline, so the CLI and the Web UI can never diverge (CLI/UI parity).

Exit codes: ``0`` when the run terminates on its own (completed — even with
zero findings); ``1`` for fatal safety/configuration/orchestration errors
(scope not confirmed, another scan already running, unknown run, failed run).

Settings are constructed fresh per invocation instead of the cached
``get_settings()``: a CLI process is one-shot, and in-process test runners
(CliRunner) monkeypatch ``METATRACER_*`` env vars between commands. Each
command owns exactly one ``asyncio.run`` boundary and disposes its engine.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape

from metatracer.cli import formatters
from metatracer.core.config import Settings
from metatracer.core.exceptions import (
    MetaTracerError,
    ScanAlreadyRunningError,
    ScopeNotConfirmedError,
)
from metatracer.core.logging import configure_logging
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Confidence, FindingType, ReasoningDepth, Run, RunStatus, Severity
from metatracer.db.repositories import RunRepository
from metatracer.knowledge.portable import export_kb, import_kb
from metatracer.reports.builder import DEFAULT_REPORTS_DIR, ReportBuilder, ReportData
from metatracer.reports.filters import filter_findings
from metatracer.scopes.portable import ScopeImportResult, export_scopes, import_scopes
from metatracer.services.orchestrator import (
    ExportFormat,
    ProgressEvent,
    ScanOrchestratorService,
    ScanRequest,
    ScanResult,
)

logger = logging.getLogger("metatracer.cli.main")

app = typer.Typer(
    name="metatracer",
    help="MetaTracer — AI-powered sensitive metadata discovery (authorized use only).",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def scan(
    targets: Annotated[
        list[str],
        typer.Argument(help="In-scope targets (domains or URLs of public documents)."),
    ],
    scope_domains: Annotated[
        list[str] | None,
        typer.Option(
            "--scope-domain",
            "-s",
            help="Authorized in-scope domain (repeatable). Required; never inferred "
            "from the target.",
        ),
    ] = None,
    confirm_scope: Annotated[
        bool,
        typer.Option(
            "--confirm-scope",
            "-y",
            help="Confirm explicit authorization non-interactively (CI/scripts).",
        ),
    ] = False,
    depth: Annotated[
        ReasoningDepth,
        typer.Option("--depth", "-d", help="Agent reasoning depth."),
    ] = ReasoningDepth.standard,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for exported reports."),
    ] = DEFAULT_REPORTS_DIR,
    export_format: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Report format to export (md, json, html, csv, bounty, all).",
        ),
    ] = ExportFormat.all,
) -> None:
    """Scan in-scope targets for sensitive metadata (authorized use only)."""
    formatters.print_banner(console)
    cleaned_targets = [target.strip() for target in targets if target.strip()]
    domains = [domain.strip() for domain in (scope_domains or []) if domain.strip()]
    if not cleaned_targets:
        err_console.print("[red]Error:[/red] at least one non-empty target is required.")
        raise typer.Exit(1)
    if not domains:
        # The scope is never inferred from the target (inviolable rule 1).
        err_console.print(
            "[red]Error:[/red] at least one --scope-domain is required; "
            "the scope is never inferred from the target."
        )
        raise typer.Exit(1)
    if not confirm_scope:
        console.print(f"Targets: {escape(', '.join(cleaned_targets))}")
        console.print(f"Authorized scope: {escape(', '.join(domains))}")
        confirmed = typer.confirm(
            "Do you confirm explicit authorization to audit this target?", default=False
        )
        if not confirmed:
            # Default is N: declining (or a non-TTY abort) stops before any
            # database write or network traffic.
            err_console.print("Scope not confirmed — aborted before any network activity.")
            raise typer.Exit(1)
    try:
        request = ScanRequest(
            targets=cleaned_targets,
            scope_domains=domains,
            scope_confirmed=True,
            reasoning_depth=depth,
        )
    except ValidationError as exc:
        err_console.print(f"[red]Invalid scan request:[/red] {exc}")
        raise typer.Exit(1) from exc
    try:
        with formatters.StageProgressRenderer(console) as renderer:
            result, report_data = asyncio.run(
                _execute_scan(request, export_format, output_dir, renderer.handle_event)
            )
    except ScopeNotConfirmedError as exc:
        err_console.print(f"[red]Scope gate:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    except ScanAlreadyRunningError as exc:
        err_console.print(f"[red]Busy:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _render_scan_outcome(result, report_data)
    if result.status is not RunStatus.completed:
        raise typer.Exit(1)


@app.command()
def report(
    run_id: Annotated[
        str, typer.Argument(help="Run UUID or the 8-character prefix from list-runs.")
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for exported reports."),
    ] = DEFAULT_REPORTS_DIR,
    export_format: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Report format to export (md, json, html, csv, bounty, all).",
        ),
    ] = ExportFormat.all,
) -> None:
    """Re-export the Markdown/JSON/HTML/CSV/bounty reports of a persisted run."""
    try:
        paths = asyncio.run(_execute_report(run_id, export_format, output_dir))
    except MetaTracerError as exc:
        err_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    for fmt, path in paths.items():
        console.print(f"Report ({fmt}): {path}")


@app.command()
def show(
    run_id: Annotated[
        str, typer.Argument(help="Run UUID or the 8-character prefix from list-runs.")
    ],
    severity: Annotated[
        Severity | None,
        typer.Option("--severity", help="Filter by severity."),
    ] = None,
    finding_type: Annotated[
        FindingType | None,
        typer.Option("--type", help="Filter by finding type."),
    ] = None,
    confidence: Annotated[
        Confidence | None,
        typer.Option("--confidence", help="Filter by confidence."),
    ] = None,
    query: Annotated[
        str | None,
        typer.Option("--q", help="Case-insensitive search in evidence, title, field or URL."),
    ] = None,
) -> None:
    """Show the findings table of a persisted run without re-scanning."""
    try:
        report_data = asyncio.run(_execute_show(run_id))
    except MetaTracerError as exc:
        err_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    filtered = filter_findings(
        report_data.findings,
        severity=severity,
        finding_type=finding_type,
        confidence=confidence,
        q=query,
    )
    view = report_data
    if filtered != list(report_data.findings):
        view = replace(report_data, findings=tuple(filtered))
    console.print(
        f"Run {report_data.run_id} — {len(filtered)} finding(s) "
        f"(of {len(report_data.findings)}) across {report_data.total_assets} asset(s)."
    )
    if filtered:
        console.print(formatters.findings_table(view))
        console.print(report_data.executive_summary_line)
    else:
        console.print("No findings match the current filters.")


@app.command(name="list-runs")
def list_runs(
    status: Annotated[
        RunStatus | None,
        typer.Option("--status", help="Filter by run status."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Newest N runs."),
    ] = None,
    cursor: Annotated[
        str | None,
        typer.Option(
            "--cursor",
            help="Keyset anchor from a previous page's next_cursor (v2.4 pagination).",
        ),
    ] = None,
) -> None:
    """List persisted runs (local history).

    TASK-21 (v2.4): pass ``--cursor`` (from the last page's ``next_cursor``)
    to page through more than the default window; keyset stays stable under
    new runs.
    """
    runs = asyncio.run(_fetch_runs(status=status, limit=limit, cursor=cursor))
    if not runs:
        console.print("No runs recorded yet.")
        return
    console.print(formatters.runs_table(runs))


@app.command()
def watch(
    scope_id: Annotated[
        str,
        typer.Argument(help="The saved scope id to re-scan (the single scope source)."),
    ],
    interval: Annotated[
        float,
        typer.Option(
            "--interval",
            help="Seconds between scans (default 6h = 21600s).",
        ),
    ] = 21600.0,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Run a single iteration and exit (CI / smoke tests).",
        ),
    ] = False,
    webhook_id: Annotated[
        str | None,
        typer.Option(
            "--webhook",
            help="Webhook id to notify with deltas (reuses TASK-15 deliveries).",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for exported reports."),
    ] = DEFAULT_REPORTS_DIR,
) -> None:
    """Re-scan a saved scope on a cadence, reporting only new findings.

    Platform v3.0, Eje A (TASK-22): headless continuous recon. The scope is
    never inferred — ``scope_id`` is the single source of authorization, and
    every iteration goes through the exact same ``ScanOrchestratorService``
    gate. ``--once`` runs a single iteration and exits; without it, the
    command loops forever with ``asyncio.sleep`` (a real ``--cron`` requires
    supply-chain approval and is out of scope).

    Deltas: each iteration compares the run's ``dedup_signature`` set against
    the historical same-scope baseline (deterministic, no LLM). ``--webhook``
    forwards the run's terminal event plus ``new_findings`` to the configured
    endpoint via the TASK-15 relay buffer.
    """
    formatters.print_banner(console)
    try:
        results = asyncio.run(
            _execute_watch(
                scope_id=scope_id,
                # ``--once``: a single iteration, signalled to the loop as a
                # zero interval (exit after the first scan). The user-supplied
                # ``--interval`` is only meaningful when looping.
                interval=0 if once else interval,
                once=once,
                webhook_id=webhook_id,
                output_dir=output_dir,
            )
        )
    except MetaTracerError as exc:
        err_console.print(f"[red]Watch error:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if once:
        for result in results:
            _render_watch_result(result)


@app.command()
def serve(
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            help="Bind host. Defaults to METATRACER_BIND_HOST (127.0.0.1); only the "
            "Docker image should use 0.0.0.0.",
        ),
    ] = None,
    port: Annotated[int, typer.Option("--port", help="Bind port.")] = 8000,
) -> None:
    """Start the local Web UI + API server.

    Authentication is optional (TASK-24/TASK-25): when ``METATRACER_AUTH_ENABLED``
    is true the Web UI/API demand a session (first boot without users enters
    setup mode — see the console banner). With auth disabled the bind address
    remains the only protection: keep it on localhost / a trusted network.
    """
    import uvicorn  # deferred: keeps scan/report/list-runs startup light

    from metatracer.api.app import create_app

    settings = Settings()
    configure_logging(settings.log_level)
    bind_host = host or settings.bind_host
    formatters.print_banner(console)
    posture = (
        "authentication ENABLED — login required (first boot: setup mode)"
        if settings.auth_enabled
        else "authentication disabled — localhost / trusted network only"
    )
    console.print(f"Web UI + API on http://{bind_host}:{port} [dim]({posture})[/dim]")
    uvicorn.run(create_app(settings), host=bind_host, port=port)


@app.command()
def kb_export(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Destination path for the portable knowledge-base JSON file.",
        ),
    ] = Path("kb-export.json"),
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum number of newest findings to export.",
        ),
    ] = 1000,
) -> None:
    """Export the historical precedents (light-RAG corpus) to a portable JSON file.

    The file contains only the portable-KB contract fields (finding type,
    sanitized snippet, severity, title, created_at) — never run/asset ids,
    raw metadata or file bytes. To bring these precedents into another
    database on this machine, use ``metatracer kb import``.
    """
    if limit < 0:
        err_console.print("[red]Error:[/red] --limit must be >= 0.")
        raise typer.Exit(1)
    n = asyncio.run(_execute_kb_export(output, limit))
    noun = "entry" if n == 1 else "entries"
    console.print(f"[green]Exported[/green] {n} knowledge {noun} to {output}")


@app.command()
def kb_import(
    input: Annotated[
        Path,
        typer.Argument(help="Path to a portable knowledge-base JSON file."),
    ],
) -> None:
    """Import a portable knowledge-base export into the local database.

    Importing is idempotent: entries whose finding id already exists are
    skipped, and nothing is deleted. Each imported row gets a fresh shadow
    run/asset so foreign keys hold without dragging the origin run.
    """
    if not input.exists() or not input.is_file():
        err_console.print(f"[red]Error:[/red] file not found: {input}")
        raise typer.Exit(1)
    try:
        n = asyncio.run(_execute_kb_import(input))
    except ValueError as exc:
        # Invalid / unsupported / malformed portable file: report and exit 1.
        err_console.print(f"[red]Import failed:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    noun = "entry" if n == 1 else "entries"
    console.print(f"[green]Imported[/green] {n} knowledge {noun} from {input}")


scope_app = typer.Typer(help="Portable scopes: import/export named scope sets (TASK-19, v2.2).")
# Register the nested group so ``metatracer scope import|export`` resolves.
app.add_typer(scope_app, name="scope")


@scope_app.command("import")
def scope_import(
    input: Annotated[
        Path,
        typer.Argument(help="Path to a portable scopes JSON file (TASK-19, v2.2)."),
    ],
) -> None:
    """Import named scopes from a portable JSON file (idempotent).

    Scopes whose name already exists are skipped; nothing is deleted or
    overwritten. The file format is the portable-scopes contract: a JSON
    object with ``format_version`` 1 and a ``scopes`` list of ``{name,
    description?, domains: [..]}``. Domains are normalized on import.
    """
    if not input.exists() or not input.is_file():
        err_console.print(f"[red]Error:[/red] file not found: {input}")
        raise typer.Exit(1)
    try:
        result = asyncio.run(_execute_scope_import(input))
    except ValueError as exc:
        # Invalid / unsupported / malformed portable file: report and exit 1.
        err_console.print(f"[red]Import failed:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]Imported[/green] {result.imported} scope(s) "
        f"([yellow]{result.skipped} skipped[/yellow]: already exist) from {input}"
    )


@scope_app.command("export")
def scope_export(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Destination path for the portable scopes JSON file.",
        ),
    ] = Path("scopes.json"),
) -> None:
    """Export all persisted scopes to a portable JSON file.

    The complement of ``metatracer scope import``: the file contains only the
    portable-scopes contract fields (name, description, domains) — never ids
    or timestamps.
    """
    n = asyncio.run(_execute_scope_export(output))
    noun = "scope" if n == 1 else "scopes"
    console.print(f"[green]Exported[/green] {n} {noun} to {output}")


async def _execute_scope_import(source: Path) -> ScopeImportResult:
    """Single async boundary of ``scope import``: engine up, import, engine down."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        return await import_scopes(session_factory, source)
    finally:
        await engine.dispose()


async def _execute_scope_export(dest: Path) -> int:
    """Single async boundary of ``scope export``: engine up, export, engine down."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        return await export_scopes(session_factory, dest)
    finally:
        await engine.dispose()


async def _execute_kb_export(dest: Path, limit: int) -> int:
    """Single async boundary of ``kb export``: engine up, export, engine down."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        return await export_kb(session_factory, dest, limit=limit)
    finally:
        await engine.dispose()


async def _execute_kb_import(source: Path) -> int:
    """Single async boundary of ``kb import``: engine up, import, engine down."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        return await import_kb(session_factory, source)
    finally:
        await engine.dispose()


def _render_scan_outcome(result: ScanResult, report_data: ReportData | None) -> None:
    """Terminal rendering: findings table on success, explicit error on failure."""
    if result.status is RunStatus.completed:
        console.print(
            f"[green]Scan completed[/green] — run {result.run_id}: "
            f"{result.total_findings} finding(s) across {result.total_assets} asset(s)."
        )
        if report_data is not None and report_data.findings:
            console.print(formatters.findings_table(report_data))
            console.print(report_data.executive_summary_line)
        else:
            # Zero findings is a valid result and is rendered as such.
            console.print(
                "[green]No findings:[/green] no sensitive metadata was identified in the "
                f"{result.total_assets} asset(s) analyzed."
            )
        for fmt, path in result.report_paths.items():
            console.print(f"Report ({fmt}): {path}")
        return
    # Failed run: say so explicitly — never render an empty table as if the
    # target were clean (the error message is already sanitized upstream).
    err_console.print(
        f"[red]Scan failed[/red] — run {result.run_id}: "
        f"{escape(result.error_message or 'unknown error')}"
    )


async def _execute_scan(
    request: ScanRequest,
    export_format: ExportFormat,
    output_dir: Path,
    on_progress: Callable[[ProgressEvent], None],
) -> tuple[ScanResult, ReportData | None]:
    """Single async boundary of the scan command: engine up, scan, read-back, engine down."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        orchestrator = ScanOrchestratorService(session_factory, settings)
        result = await orchestrator.scan(
            request, formats=export_format, output_dir=output_dir, on_progress=on_progress
        )
        report_data = None
        if result.status is RunStatus.completed:
            # Same builder the Web UI uses: the CLI table can never diverge.
            report_data = await ReportBuilder(session_factory).build(result.run_id)
        return result, report_data
    finally:
        await engine.dispose()


async def _execute_report(
    run_id: str, export_format: ExportFormat, output_dir: Path
) -> dict[str, Path]:
    """Resolve the run token, then re-export through the orchestrator."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            run = await RunRepository(session).resolve(run_id)
        orchestrator = ScanOrchestratorService(session_factory, settings)
        return await orchestrator.export_report(
            run.id, formats=export_format, output_dir=output_dir
        )
    finally:
        await engine.dispose()


async def _execute_show(run_id: str) -> ReportData:
    """Resolve the run token and rebuild the report view (no export)."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            run = await RunRepository(session).resolve(run_id)
        return await ReportBuilder(session_factory).build(run.id)
    finally:
        await engine.dispose()


async def _fetch_runs(
    *, status: RunStatus | None = None, limit: int | None = None, cursor: str | None = None
) -> list[Run]:
    """Load persisted runs, newest first (TASK-21: optional keyset cursor)."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            return await RunRepository(session).list_recent(
                status=status, limit=limit, cursor=cursor
            )
    finally:
        await engine.dispose()


async def _execute_watch(
    *,
    scope_id: str,
    interval: float,
    once: bool,
    webhook_id: str | None,
    output_dir: Path,
) -> list[ScanResult]:
    """Single async boundary of the watch command.

    Engine up per process (one-shot for ``--once``), lock by scope, then
    iterate scans with backoff on consecutive failures. Returns the list of
    per-iteration results (one for ``--once``).
    """
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        # TASK-22: one watch per scope — a second concurrent watch must fail
        # cleanly instead of double-scanning (a real scope lock, not just the
        # in-process single-scan lock).
        from metatracer.db.repositories import ScopeRepository

        async with session_factory() as session:
            scope = await ScopeRepository(session).get(scope_id)
        if scope is None:
            raise MetaTracerError(f"scope not found: {scope_id}")

        lock = None if once else _scope_lock(scope_id)
        if not once and lock is None:
            raise MetaTracerError(
                f"another watch is already running for scope {scope_id}"
            )
        try:
            return await _watch_loop(
                session_factory,
                settings,
                scope_id,
                interval,
                webhook_id,
                output_dir,
            )
        finally:
            if lock is not None:
                _release_scope_lock(lock)
    finally:
        await engine.dispose()


async def _watch_loop(
    session_factory,
    settings: Settings,
    scope_id: str,
    interval: float,
    webhook_id: str | None,
    output_dir: Path,
) -> list[ScanResult]:
    """Run one scan, then keep running every ``interval`` seconds.

    ``--once`` is signalled by ``interval <= 0`` and runs a single iteration.
    On a failure the loop backs off (doubling, capped) instead of hammering.

    ``webhook_id`` resolves to a ``WebhookDispatcher`` wired exactly like the
    API lifespan (same anti-SSRF guard) so the watch loop can notify the
    scope's deltas outbound; the dispatcher is shut down when the loop exits.
    """
    from metatracer.services.orchestrator import ScanOrchestratorService
    from metatracer.services.watch import DeltaReporter

    delta_reporter = DeltaReporter(session_factory)
    dispatcher = None
    if webhook_id:
        from metatracer.api.webhooks import WebhookDispatcher
        from metatracer.core.safety.guard import NetworkSafetyGuard

        dispatcher = WebhookDispatcher(
            session_factory, guard=NetworkSafetyGuard(settings.allow_loopback)
        )
    orchestrator = ScanOrchestratorService(
        session_factory,
        settings,
        delta_reporter=delta_reporter,
        webhooks=dispatcher,
    )
    results: list[ScanResult] = []
    consecutive_failures = 0
    base_backoff = 5.0
    max_backoff = 300.0
    try:
        while True:
            result = await _watch_iteration(
                session_factory,
                orchestrator,
                delta_reporter,
                scope_id,
                webhook_id,
                output_dir,
            )
            results.append(result)
            if result.status is not RunStatus.completed:
                consecutive_failures += 1
            else:
                consecutive_failures = 0
            if interval <= 0:
                return results  # --once
            delay = interval
            if consecutive_failures > 1:
                delay = min(max_backoff, base_backoff * (2 ** (consecutive_failures - 1)))
            console.print(
                f"[dim]Next scan in {_format_delay(delay)}[/dim] (consecutive failures: "
                f"{consecutive_failures})"
            )
            await asyncio.sleep(delay)
    finally:
        if dispatcher is not None:
            await dispatcher.shutdown()


async def _watch_iteration(
    session_factory,
    orchestrator,
    delta_reporter,
    scope_id: str,
    webhook_id: str | None,
    output_dir: Path,
) -> ScanResult:
    """One watch iteration: scan the scope (watch flag on, delta auto-reported).

    ``delta_reporter`` is kept for the loop's own console line; the webhook
    delta travels through the orchestrator's notification path (it already
    knows the reporter).
    """
    from metatracer.db.repositories import ScopeRepository
    from metatracer.services.orchestrator import ScanRequest

    async with session_factory() as session:
        scope = await ScopeRepository(session).get(scope_id)
    if scope is None:
        return ScanResult(
            run_id="",
            status=RunStatus.failed,
            total_assets=0,
            total_findings=0,
            error_message=f"scope not found: {scope_id}",
        )
    domains = json.loads(scope.domains)
    request = ScanRequest(
        targets=[domains[0]] if domains else [],  # a watch scans the scope root
        scope_domains=domains,
        scope_confirmed=True,
        watch=True,
    )
    result = await orchestrator.scan(
        request, output_dir=output_dir, on_progress=None
    )
    if result.status is RunStatus.completed and result.run_id:
        try:
            delta = await delta_reporter.compute_delta(result.run_id)
            console.print(f"[green]Delta:[/green] {delta.new_findings} new finding(s)")
        except Exception:
            logger.warning("delta computation failed; continuing watch", exc_info=True)
    return result


def _scope_lock(scope_id: str) -> object | None:
    """Exclusive lock for one watch scope.

    POSIX uses ``fcntl.flock``; Windows falls back to ``os.open(O_CREAT|O_EXCL)``
    so the lock file itself is the marker. Returns ``None`` when another
    process holds the watch.
    """
    import os
    import tempfile

    lock_dir = Path(tempfile.gettempdir()) / "metatracer-watch"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"watch-{scope_id}.lock"
    try:
        import fcntl  # POSIX

        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {"fd": fd, "path": lock_path}
    except ImportError:
        # Windows: O_EXCL creates the file only if it does not exist.
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return {"fd": fd, "path": lock_path}
        except FileExistsError:
            return None
    except BlockingIOError:
        return None


def _release_scope_lock(lock: object) -> None:
    """Release a lock file acquired by :func:`_scope_lock`."""
    import os

    if not isinstance(lock, dict):
        return
    try:
        if "fd" in lock:
            try:
                import fcntl

                fcntl.flock(lock["fd"], fcntl.LOCK_UN)
            except ImportError:
                pass
            os.close(lock["fd"])
        Path(lock["path"]).unlink(missing_ok=True)
    except OSError:
        pass  # best-effort: a stale lock file is harmless (fcntl re-locks)


def _format_delay(seconds: float) -> str:
    """Human-readable delay, e.g. '6h 0m' or '2m 5s'."""
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _render_watch_result(result: ScanResult) -> None:
    """Render one iteration's outcome (``--once``)."""
    if result.status is RunStatus.completed:
        console.print(
            f"[green]Watch iteration completed[/green] — run {result.run_id}: "
            f"{result.total_findings} finding(s) across {result.total_assets} asset(s)."
        )
        return
    err_console.print(
        f"[red]Watch iteration failed[/red] — run {result.run_id}: "
        f"{escape(result.error_message or 'unknown error')}"
    )
