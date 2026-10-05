"""BountyExporter: plain-text write-up ready to paste into a bounty program (TASK-18, v2.2).

HackerOne, Bugcrowd and Intigriti all accept free-text report bodies that do
not render Markdown (``#``, backticks and ``---`` come through literally).
The bounty export therefore renders *one plain-text write-up per finding*
with exactly the fields of the TASK-04 card, so an operator can copy the
block into the program's "New report" form without rewriting anything.

The content mirrors the Markdown exporter (subtask 4.2) field for field, in
plain text:

- Title, Severity (Title Case — presentation layer), Finding type (human
  label), Affected asset, Metadata field, Evidence (byte-for-byte snippet),
  Impact, Explanation, Reproduction (non-exploitative, numbered) and
  Remediation. Empty prose renders as the heuristic-baseline placeholder.
- A run with no findings produces a valid file with the summary and a
  ``No findings.`` line — never an empty/corrupt artifact.

No network, no LLM, no reads of original asset files: the data is
:class:`ReportData` only. This is a *local file artifact*; nothing is ever
sent to any platform (auto-submission is out of scope, feature 04).

Formula neutralization (TASK-27) is applied by the CSV exporter, not here.
Each line of this write-up starts with a field label (``Evidence: ...``),
so the file is a prose card for a bounty form, not a cell-oriented sheet.
"""

from pathlib import Path

from metatracer.reports.builder import (
    DEFAULT_REPORTS_DIR,
    REPORT_TITLE,
    ReportData,
    ReportFindingData,
    iso_z,
    report_filename_stem,
)


class BountyExporter:
    """Writes the report as a plain-text ``.txt`` file (subtask 18.3)."""

    def __init__(self, output_dir: str | Path = DEFAULT_REPORTS_DIR) -> None:
        self._output_dir = Path(output_dir)

    def export(self, data: ReportData) -> Path:
        """Render and write the ``.txt`` file; returns the path written."""
        path = self._output_dir / f"{report_filename_stem(data)}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_bounty(data), encoding="utf-8")
        return path


def render_bounty(data: ReportData) -> str:
    """Plain-text bounty write-up: header, summary, one block per finding."""
    parts = [_render_header(data), _render_summary(data), _render_compliance(data)]
    if data.findings:
        blocks = [
            f"=== Finding {index + 1}/{len(data.findings)} ===\n" + _render_finding_text(finding)
            for index, finding in enumerate(data.findings)
        ]
        parts.append("\n\n".join(blocks))
    else:
        parts.append("No findings.")
    return "\n\n".join(parts) + "\n"


def _render_header(data: ReportData) -> str:
    scope = ", ".join(data.scope) or "n/a"
    return "\n".join(
        [
            REPORT_TITLE,
            "",
            f"Target: {data.target}",
            f"Confirmed scope: {scope}",
            f"Run ID: {data.run_id}",
            f"Generated at (UTC): {iso_z(data.generated_at)}",
            f"Reasoning depth: {data.reasoning_depth.value}",
            f"MetaTracer version: {data.metatracer_version}",
        ]
    )


def _render_summary(data: ReportData) -> str:
    return "\n".join(
        [
            "Executive Summary",
            "",
            data.executive_summary_line,
            "",
            _no_fake_finding_header(data.hygiene_note),
        ]
    )


def _render_compliance(data: ReportData) -> str:
    return "\n".join(
        [
            "Scope & Compliance Notice",
            "",
            "This report summarizes a passive metadata audit of publicly available "
            "documents inside the confirmed scope listed above; it is not an "
            "exploitation test.",
            "",
            data.compliance_notice,
        ]
    )


def _render_finding_text(finding: ReportFindingData) -> str:
    """One finding card in plain text, fields in the TASK-04 4.2 order."""
    severity_label = (
        finding.severity.value.capitalize() if finding.severity is not None else "Unclassified"
    )
    reproduction = "\n".join(
        f"{index}. {step}" for index, step in enumerate(finding.reproduction_steps, start=1)
    )
    return "\n".join(
        [
            f"Title: {_single_line(finding.title)}",
            f"Severity: {severity_label}",
            *([f"Triage: {finding.triage_label}"] if finding.triage_status.value != "open" else []),
            f"Finding type: {finding.type_label}",
            f"Affected asset: {finding.asset_final_url} "
            f"(source: {finding.asset_source_url}, "
            f"content-type: {finding.asset_content_type})",
            f"Metadata field: {finding.field_source}",
            f"Evidence: {finding.evidence}",
            f"Impact: {_single_line(finding.impact)}",
            f"Explanation: {_single_line(finding.explanation)}",
            "Reproduction (non-exploitative):",
            _indent(_no_fake_finding_header(reproduction)),
            "Remediation:",
            _indent(_no_fake_finding_header(finding.remediation)),
        ]
    )


def _no_fake_finding_header(text: str) -> str:
    """A prose line must not look like the ``=== Finding N/N ===`` separator."""
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("==="):
            line = "Note: " + line.strip()
        lines.append(line)
    return "\n".join(lines)


def _single_line(text: str) -> str:
    """Collapse internal whitespace so prose fits a single plain-text line."""
    import re

    return re.sub(r"\s+", " ", text).strip()


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())