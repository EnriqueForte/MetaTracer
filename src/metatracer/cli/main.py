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
from metatracer.services.orchestrator import (
    ExportFormat,
    ProgressEvent,
    ScanOrchestratorService,
    ScanRequest,
    ScanResult,
)

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
        typer.Option("--format", "-f", help="Report format to export."),
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
        typer.Option("--format", "-f", help="Report format to export (md, json, html, all)."),
    ] = ExportFormat.all,
) -> None:
    """Re-export the Markdown/JSON/HTML reports of a persisted run."""
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
) -> None:
    """List persisted runs (local history)."""
    runs = asyncio.run(_fetch_runs(status=status, limit=limit))
    if not runs:
        console.print("No runs recorded yet.")
        return
    console.print(formatters.runs_table(runs))


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

    No authentication in v1.0: the bind address is the only protection, so the
    default is localhost / trusted networks only.
    """
    import uvicorn  # deferred: keeps scan/report/list-runs startup light

    from metatracer.api.app import create_app

    settings = Settings()
    configure_logging(settings.log_level)
    bind_host = host or settings.bind_host
    formatters.print_banner(console)
    console.print(
        f"Web UI + API on http://{bind_host}:{port} "
        "[dim](no authentication in v1.0 — localhost / trusted network only)[/dim]"
    )
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
    *, status: RunStatus | None = None, limit: int | None = None
) -> list[Run]:
    """Load persisted runs, newest first."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    try:
        await init_db(engine)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            return await RunRepository(session).list_recent(status=status, limit=limit)
    finally:
        await engine.dispose()
