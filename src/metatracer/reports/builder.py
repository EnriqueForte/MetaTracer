"""ReportBuilder: consolidate a run's persisted findings into report data (TASK-04, 4.1).

Strictly read-only: the Run, its Assets and its Findings are loaded through the
repositories in one sequential session and mapped to the presentation-neutral
:class:`ReportData` consumed by the Markdown and JSON exporters. No network, no
reads of the original asset files, no LLM — the report is regenerated from the
database on every export (no ``Report`` table in the MVP, subtask 4.3).

Documented decisions:

- Ordering (4.1.1): severity ``critical`` (5) -> ``info`` (1); findings whose
  ``severity`` is still NULL sort *last* as unclassified (never treated as
  info). Ties break on confidence ``high`` -> ``low``, then on
  ``Asset.discovered_at`` ascending, then on the finding id so the output is
  fully deterministic (the contract leaves the last tie open).
- ``target`` is the run's primary target: the first entry of the JSON list in
  ``Run.target_input``, kept verbatim. The file-name slug derives the host.
- ``total_assets`` counts the Asset rows actually loaded, so the report is
  self-consistent even if the run's denormalized counter lags behind.
- NULL prose fields render as ``Not generated (heuristic baseline)``: an export
  never crashes on fields TASK-05 has not filled (DoD).
- Agent prose wins when present: ``Run.executive_summary`` replaces the
  heuristic hygiene paragraph (except for the fixed empty-run sentence) and
  ``Finding.title`` replaces the per-type template title.
- ``generated_at`` is captured once per ``build()`` so a Markdown/JSON pair
  exported from the same ReportData shares the file-name timestamp; a fresh
  build yields a fresh timestamped file instead of overwriting (4.3).
- Triage (TASK-35): findings an operator marked ``false_positive`` are left
  out by default and counted in ``excluded_false_positives``; severity counts
  cover only the findings in the report. ``include_false_positives=True``
  keeps them, each with its ``triage_status``.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer import __version__
from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import (
    Asset,
    Confidence,
    Finding,
    FindingType,
    ReasoningDepth,
    Severity,
    TriageStatus,
)
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository

TRIAGE_LABELS: dict[TriageStatus, str] = {
    TriageStatus.open: "Open",
    TriageStatus.confirmed: "Confirmed",
    TriageStatus.false_positive: "False positive",
    TriageStatus.fixed: "Fixed",
}

REPORT_TITLE = "MetaTracer Security Report"

PROSE_PLACEHOLDER = "Not generated (heuristic baseline)"

COMPLIANCE_NOTICE = (
    "This scan was limited to the confirmed in-scope public documents. "
    "Reproduction is inspection-only."
)

DEFAULT_REPORTS_DIR = Path("reports")

# Severity ranks per the task contract (4.1.1): critical 5 -> info 1; NULL
# sorts below info (rank 0) so unclassified findings always come last.
_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.critical: 5,
    Severity.high: 4,
    Severity.medium: 3,
    Severity.low: 2,
    Severity.info: 1,
}
_CONFIDENCE_ORDER: dict[Confidence, int] = {
    Confidence.high: 3,
    Confidence.medium: 2,
    Confidence.low: 1,
}

# Human labels for the finding types (4.2, item 4).
_TYPE_LABELS: dict[FindingType, str] = {
    FindingType.gps: "GPS / Coordinates",
    FindingType.email: "Email",
    FindingType.internal_path: "Internal Path",
    FindingType.software_version: "Software Version",
    FindingType.debug_comment: "Debug Comment",
}

# One-line card titles (4.2, item 1), suffixed with the asset context.
_TYPE_TITLES: dict[FindingType, str] = {
    FindingType.gps: "GPS Coordinate Disclosure",
    FindingType.email: "Email Address Disclosure",
    FindingType.internal_path: "Internal Path Disclosure",
    FindingType.software_version: "Software Version Disclosure",
    FindingType.debug_comment: "Debug Comment Disclosure",
}

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9.-]+")
_BACKTICK_RUN_RE = re.compile(r"`+")


@dataclass(frozen=True, slots=True)
class SeverityCounts:
    """Severity tallies of one report; unclassified = findings with NULL severity."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    unclassified: int = 0


@dataclass(frozen=True, slots=True)
class ReportFindingData:
    """One report card: persisted evidence plus resolved prose and asset context."""

    id: str
    title: str
    finding_type: FindingType
    type_label: str
    severity: Severity | None  # None = unclassified
    confidence: Confidence
    asset_source_url: str
    asset_final_url: str
    asset_content_type: str
    field_source: str
    evidence: str  # byte-for-byte the persisted snippet, whitespace-trimmed
    impact: str
    explanation: str
    remediation: str
    reproduction_steps: tuple[str, ...]
    triage_status: TriageStatus = TriageStatus.open
    triage_note: str = ""
    triaged_by: str = ""
    triaged_at: datetime | None = None

    @property
    def triage_label(self) -> str:
        return TRIAGE_LABELS[self.triage_status]


@dataclass(frozen=True, slots=True)
class ReportData:
    """Presentation-neutral report structure consumed by both exporters."""

    metatracer_version: str
    run_id: str
    target: str
    scope: tuple[str, ...]
    generated_at: datetime  # timezone-aware UTC
    reasoning_depth: ReasoningDepth
    total_assets: int
    severity_counts: SeverityCounts
    hygiene_note: str
    compliance_notice: str
    findings: tuple[ReportFindingData, ...]
    excluded_false_positives: int = 0

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def executive_summary_line(self) -> str:
        """One-line tally mandated by the header contract (4.1.2)."""
        counts = self.severity_counts
        line = (
            f"Total assets: {self.total_assets} | Critical: {counts.critical} | "
            f"High: {counts.high} | Medium: {counts.medium} | Low: {counts.low} | "
            f"Info: {counts.info} | Unclassified: {counts.unclassified}"
        )
        if self.excluded_false_positives:
            line += f" | Excluded as false positive: {self.excluded_false_positives}"
        return line


class ReportBuilder:
    """Builds :class:`ReportData` for one persisted Run; strictly read-only."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def build(self, run_id: str, *, include_false_positives: bool = False) -> ReportData:
        """Load the run, its assets and its findings and return the report data."""
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
            if run is None:
                raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")
            assets = await AssetRepository(session).list_by_run(run_id)
            findings = await FindingRepository(session).list_by_run(run_id)

        excluded = 0
        if not include_false_positives:
            kept = [f for f in findings if f.triage_status != TriageStatus.false_positive]
            excluded = len(findings) - len(kept)
            findings = kept
        assets_by_id = {asset.id: asset for asset in assets}
        # FK enforcement guarantees the asset exists; a KeyError would mean the
        # database is corrupt, which must surface rather than drop findings.
        pairs = [(finding, assets_by_id[finding.asset_id]) for finding in findings]
        pairs.sort(key=_sort_key)
        entries = tuple(_entry(finding, asset) for finding, asset in pairs)
        counts = _severity_counts(findings)
        return ReportData(
            metatracer_version=__version__,
            run_id=run.id,
            target=_primary_target(run.target_input),
            scope=_scope_list(run.allowed_scope),
            # Second precision: matches the file-name timestamp and the ISO-8601
            # Z format of the task contract's JSON example.
            generated_at=datetime.now(UTC).replace(microsecond=0),
            reasoning_depth=ReasoningDepth(run.reasoning_depth),
            total_assets=len(assets),
            severity_counts=counts,
            hygiene_note=_hygiene_note(len(assets), findings, run.executive_summary),
            compliance_notice=COMPLIANCE_NOTICE,
            findings=entries,
            excluded_false_positives=excluded,
        )


def slugify_target(target: str) -> str:
    """Domain slug for report file names (4.3): lowercase ``[a-z0-9.-]``.

    When the target is a URL the host is extracted first; every other
    disallowed character run becomes a single dash. The result is confined to
    the file-name safe set, so it can never traverse the output directory.
    """
    text = target.strip().lower()
    if "://" in text:
        try:
            text = urlsplit(text).hostname or text
        except ValueError:
            pass  # keep the raw text; the sanitizer below still confines it
    slug = _SLUG_INVALID_RE.sub("-", text).strip("-.")
    return slug or "unknown"


def run_id_short(run_id: str) -> str:
    """First segment of the UUID (8 hex chars); raw prefix as fallback."""
    return run_id.split("-", 1)[0][:8] or "unknown"


def report_filename_stem(data: ReportData) -> str:
    """``metatracer-{slug-target}-{run_id_short}-{YYYYMMDDTHHMMSSZ}`` (4.3)."""
    return (
        f"metatracer-{slugify_target(data.target)}-"
        f"{run_id_short(data.run_id)}-{filename_timestamp(data.generated_at)}"
    )


def filename_timestamp(moment: datetime) -> str:
    """UTC timestamp for file names: ``YYYYMMDDTHHMMSSZ``."""
    return _as_utc(moment).strftime("%Y%m%dT%H%M%SZ")


def iso_z(moment: datetime) -> str:
    """UTC ISO-8601 with Z suffix, as shown in the report header (4.1.2)."""
    return _as_utc(moment).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sort_key(pair: tuple[Finding, Asset]) -> tuple[int, int, datetime, str]:
    finding, asset = pair
    severity_rank = (
        _SEVERITY_ORDER[Severity(finding.severity)] if finding.severity is not None else 0
    )
    confidence_rank = _CONFIDENCE_ORDER[Confidence(finding.confidence)]
    return (-severity_rank, -confidence_rank, _as_utc(asset.discovered_at), finding.id)


def _entry(finding: Finding, asset: Asset) -> ReportFindingData:
    finding_type = FindingType(finding.finding_type)
    severity = Severity(finding.severity) if finding.severity is not None else None
    return ReportFindingData(
        id=finding.id,
        title=_title_for(finding, finding_type, asset.content_type),
        finding_type=finding_type,
        type_label=_TYPE_LABELS[finding_type],
        severity=severity,
        confidence=Confidence(finding.confidence),
        asset_source_url=asset.source_url,
        asset_final_url=asset.final_url,
        asset_content_type=asset.content_type,
        field_source=finding.field_source,
        evidence=_prose(finding.evidence_snippet),
        impact=_prose(finding.impact_analysis),
        explanation=_prose(finding.severity_justification),
        remediation=_prose(finding.remediation_advice),
        reproduction_steps=tuple(_parse_reproduction_steps(finding.reproduction_steps)),
        triage_status=TriageStatus(finding.triage_status or TriageStatus.open),
        triage_note=finding.triage_note or "",
        triaged_by=finding.triaged_by or "",
        triaged_at=finding.triaged_at,
    )


def _severity_counts(findings: list[Finding]) -> SeverityCounts:
    tallies = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "unclassified": 0}
    for finding in findings:
        key = str(finding.severity) if finding.severity is not None else "unclassified"
        tallies[key] += 1
    return SeverityCounts(**tallies)


def _hygiene_note(
    total_assets: int, findings: list[Finding], agent_summary: str | None = None
) -> str:
    """Header paragraph (4.1.2/4.1.3): the agent's executive summary when the
    TASK-05 summary node produced one, otherwise a heuristic hygiene note.

    The empty-run sentence is a fixed contract (4.1.3) and always wins.
    """
    if not findings:
        return (
            "No sensitive metadata was identified in the "
            f"{total_assets} document(s) analyzed."
        )
    if agent_summary is not None and agent_summary.strip():
        return agent_summary.strip()
    classified = [
        Severity(finding.severity) for finding in findings if finding.severity is not None
    ]
    if not classified:
        return (
            f"{len(findings)} finding(s) were identified across {total_assets} document(s); "
            "none has been classified yet, so this report lists them as unclassified."
        )
    top = max(classified, key=_SEVERITY_ORDER.__getitem__)
    return (
        f"{len(findings)} finding(s) were identified across {total_assets} document(s), "
        "consistent with residual authoring-tool or device metadata left in published "
        f"files; the highest severity observed is {top.value.capitalize()}. Stripping "
        "metadata in the publication pipeline removes this class of exposure."
    )


def _primary_target(target_input: str) -> str:
    """First usable entry of the JSON target list; raw text as fallback."""
    parsed = _try_json(target_input)
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, str) and item.strip():
                return item.strip()
    if isinstance(parsed, str) and parsed.strip():
        return parsed.strip()
    return target_input.strip() or "unknown-target"


def _scope_list(allowed_scope: str) -> tuple[str, ...]:
    """Deserialize the JSON scope list; corrupt input degrades to empty."""
    parsed = _try_json(allowed_scope)
    if isinstance(parsed, list):
        return tuple(item.strip() for item in parsed if isinstance(item, str) and item.strip())
    if isinstance(parsed, str) and parsed.strip():
        return (parsed.strip(),)
    return ()


def _parse_reproduction_steps(raw: str | None) -> list[str]:
    """Materialize persisted reproduction steps as a list of strings.

    The persisted field is a JSON array string (TASK-03) or, per the model
    contract, legacy newline-separated text. Empty, corrupt or unexpected
    content degrades to the placeholder instead of breaking the export.
    """
    if raw is None or not raw.strip():
        return [PROSE_PLACEHOLDER]
    text = raw.strip()
    parsed = _try_json(text)
    if isinstance(parsed, list):
        steps = [str(item).strip() for item in parsed if str(item).strip()]
        return steps or [PROSE_PLACEHOLDER]
    if text.startswith(("[", "{")):
        return [PROSE_PLACEHOLDER]  # looks like JSON but does not parse: corrupt
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines or [PROSE_PLACEHOLDER]


def _prose(value: str | None) -> str:
    """Trimmed prose, or the heuristic-baseline placeholder when empty (4.1)."""
    if value is None or not value.strip():
        return PROSE_PLACEHOLDER
    return value.strip()


def _title_for(finding: Finding, finding_type: FindingType, content_type: str) -> str:
    """Agent-drafted title when TASK-05 stored one; per-type template otherwise."""
    if finding.title is not None and finding.title.strip():
        return " ".join(finding.title.split())  # one line, no stray newlines in headings
    return f"{_TYPE_TITLES[finding_type]} {_asset_context(content_type)}"


def _asset_context(content_type: str) -> str:
    lowered = content_type.strip().lower()
    if lowered == "application/pdf":
        return "in Public PDF"
    if lowered.startswith("image/"):
        return "in Public Image"
    return "in Public Document"


def _try_json(text: str) -> object:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every write is UTC (see db/models.py)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def longest_backtick_run(text: str) -> int:
    """Longest backtick run in ``text``; Markdown helpers size fences with it."""
    return max((len(match.group(0)) for match in _BACKTICK_RUN_RE.finditer(text)), default=0)
