"""Rich rendering helpers for the MetaTracer CLI (TASK-06, subtask 6.2).

Presentation only — the orchestrator and the ReportBuilder own every decision.
Any value originating from the target (evidence snippets, asset URLs) or from
persisted operator input (targets) is escaped with ``rich.markup.escape`` so
stored content can never inject console markup: the CLI analogue of the Web
UI's no-``|safe`` rule.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table
from rich.text import Text

from metatracer import __version__
from metatracer.db.models import Investigation, InvestigationStatus, Run, RunStatus, Severity
from metatracer.reports.builder import ReportData, run_id_short
from metatracer.services.orchestrator import ProgressEvent
from metatracer.services.search import FindingHit, MetadataHit

SEVERITY_STYLES: dict[Severity, str] = {
    Severity.critical: "bold red",
    Severity.high: "magenta",
    Severity.medium: "yellow",
    Severity.low: "cyan",
    Severity.info: "dim",
}

_STATUS_STYLES: dict[RunStatus, str] = {
    RunStatus.completed: "green",
    RunStatus.failed: "bold red",
    RunStatus.running: "yellow",
    RunStatus.pending: "dim",
    RunStatus.aborted: "dim",
}

BANNER = f"MetaTracer v{__version__} — AI-powered sensitive metadata discovery"
ETHICS_NOTICE = (
    "Authorized use only: scan exclusively targets you own or hold explicit "
    "written authorization to audit (bug bounty scope, rules of engagement)."
)

EVIDENCE_MAX_CHARS = 80
URL_MAX_CHARS = 100
TARGET_MAX_CHARS = 60


def print_banner(console: Console) -> None:
    """Product banner plus the ethical-use notice shown before every scan."""
    console.print(f"[bold]{BANNER}[/bold]")
    console.print(f"[dim]{ETHICS_NOTICE}[/dim]")


def findings_table(data: ReportData) -> Table:
    """Severity-colored findings table; same ordering as the exported reports."""
    table = Table(title=f"Findings — run {data.run_id}")
    table.add_column("Severity", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Evidence")
    table.add_column("Asset URL")
    for finding in data.findings:
        if finding.severity is None:
            severity_cell = Text("Unclassified", style="dim")
        else:
            severity_cell = Text(
                finding.severity.value.capitalize(), style=SEVERITY_STYLES[finding.severity]
            )
        table.add_row(
            severity_cell,
            escape(finding.type_label),
            escape(_truncate(finding.evidence, EVIDENCE_MAX_CHARS)),
            escape(_truncate(finding.asset_final_url, URL_MAX_CHARS)),
        )
    return table


def search_findings_table(items: tuple[FindingHit, ...] | list[FindingHit]) -> Table:
    """Global finding hits (TASK-46). Evidence is escaped, never markup."""
    table = Table(title="Finding hits")
    table.add_column("Run", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Evidence")
    table.add_column("Asset URL")
    for item in items:
        table.add_row(
            run_id_short(item.run_id),
            escape(str(item.type_label)),
            escape(_truncate(str(item.evidence_snippet), EVIDENCE_MAX_CHARS)),
            escape(_truncate(str(item.asset_url), URL_MAX_CHARS)),
        )
    return table


def search_metadata_table(items: tuple[MetadataHit, ...] | list[MetadataHit]) -> Table:
    """Global raw-metadata hits (TASK-46). Values are escaped text."""
    table = Table(title="Metadata hits")
    table.add_column("Run", no_wrap=True)
    table.add_column("Namespace", no_wrap=True)
    table.add_column("Key")
    table.add_column("Value")
    for item in items:
        table.add_row(
            run_id_short(item.run_id),
            escape(str(item.namespace)),
            escape(str(item.key)),
            escape(_truncate(str(item.value), EVIDENCE_MAX_CHARS)),
        )
    return table


def runs_table(runs: list[Run]) -> Table:
    """Minimal run history: short id, primary target, status, counters, date."""
    table = Table(title="MetaTracer runs")
    table.add_column("Run", no_wrap=True)
    table.add_column("Target")
    table.add_column("Status", no_wrap=True)
    table.add_column("Assets", justify="right")
    table.add_column("Findings", justify="right")
    table.add_column("Started (UTC)", no_wrap=True)
    for run in runs:
        status = RunStatus(run.status)
        table.add_row(
            run_id_short(run.id),
            escape(_truncate(primary_target(run), TARGET_MAX_CHARS)),
            Text(status.value, style=_STATUS_STYLES[status]),
            str(run.total_assets),
            str(run.total_findings),
            _as_utc(run.started_at).strftime("%Y-%m-%d %H:%M"),
        )
    return table


def investigations_table(
    rows: list[tuple[Investigation, int]],
) -> Table:
    """Named groups of runs. Status is grouping only, not tenancy."""
    table = Table(title="Investigations")
    table.add_column("Id", no_wrap=True)
    table.add_column("Name")
    table.add_column("Status", no_wrap=True)
    table.add_column("Runs", justify="right")
    for investigation, count in rows:
        status = InvestigationStatus(investigation.status)
        table.add_row(
            investigation.id,
            escape(_truncate(investigation.name, TARGET_MAX_CHARS)),
            status.value,
            str(count),
        )
    return table


def primary_target(run: Run) -> str:
    """First usable entry of the JSON target list; raw payload as fallback."""
    try:
        parsed = json.loads(run.target_input)
    except (json.JSONDecodeError, TypeError):
        return run.target_input
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return run.target_input


def _truncate(text: str, limit: int) -> str:
    """Single-line, length-capped rendering of a persisted value."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every write is UTC (see db/models.py)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class StageProgressRenderer:
    """Rich spinner mirroring orchestrator ProgressEvents (context manager).

    ``handle_event`` is a plain synchronous callback: the orchestrator invokes
    it from the event-loop thread while Rich refreshes the live display from
    its own thread, so the scan never waits on the terminal.
    """

    def __init__(self, console: Console) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        )
        self._task_id: TaskID | None = None

    def __enter__(self) -> StageProgressRenderer:
        self._progress.start()
        self._task_id = self._progress.add_task("Starting scan", total=None)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._progress.stop()

    def handle_event(self, event: ProgressEvent) -> None:
        """Render one ProgressEvent as the spinner's current description."""
        if self._task_id is None:
            return
        # The message is already sanitize_for_log-clean (no CRLF/C0), but Rich
        # parses "[...]" as markup: escape so a target-controlled error string
        # cannot spoof console styling (threat 13, defense in depth).
        description = f"[{event.current_step}/{event.total_steps}] {escape(event.message)}"
        self._progress.update(self._task_id, description=description)
