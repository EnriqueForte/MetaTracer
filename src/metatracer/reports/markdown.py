"""MarkdownReportExporter: GFM write-up ready for a bug bounty program (4.3.1).

Severity shows in Title Case (presentation layer per the data contract) and as
a heading per finding: ``### [High] Internal Path Disclosure in Public PDF``.
Evidence is emitted in a fenced ``text`` block whose content lines are kept
byte-for-byte (only the fence lines are indented to nest under the bullet);
the fence length adapts to any backtick run in the snippet so hostile metadata
cannot break out of the block.
"""

import re
from pathlib import Path

from metatracer.reports.builder import (
    DEFAULT_REPORTS_DIR,
    REPORT_TITLE,
    ReportData,
    ReportFindingData,
    iso_z,
    longest_backtick_run,
    report_filename_stem,
)

_WHITESPACE_RUN_RE = re.compile(r"\s+")


class MarkdownReportExporter:
    """Writes the report as GitHub-flavored Markdown (subtask 4.3.1)."""

    def __init__(self, output_dir: str | Path = DEFAULT_REPORTS_DIR) -> None:
        self._output_dir = Path(output_dir)

    def export(self, data: ReportData) -> Path:
        """Render and write the ``.md`` file; returns the path written.

        The file name derives only from the sanitized slug, the run id and the
        build timestamp, so user input can never escape ``output_dir``.
        """
        path = self._output_dir / f"{report_filename_stem(data)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(data), encoding="utf-8")
        return path


def render_markdown(data: ReportData) -> str:
    """Full Markdown document for the report data (header, summary, cards)."""
    parts = [_render_header(data), _render_summary(data), _render_compliance(data)]
    if data.findings:
        parts.append(_render_findings(data))
    return "\n\n".join(parts) + "\n"


def _render_header(data: ReportData) -> str:
    scope = ", ".join(_inline_code(item) for item in data.scope) or "n/a"
    return "\n".join(
        [
            f"# {REPORT_TITLE}",
            "",
            f"- **Target:** {_inline_code(data.target)}",
            f"- **Confirmed scope:** {scope}",
            f"- **Run ID:** {_inline_code(data.run_id)}",
            f"- **Generated at (UTC):** {iso_z(data.generated_at)}",
            f"- **Reasoning depth:** {data.reasoning_depth.value}",
            f"- **MetaTracer version:** {data.metatracer_version}",
        ]
    )


def _render_summary(data: ReportData) -> str:
    return "\n".join(
        [
            "## Executive Summary",
            "",
            data.executive_summary_line,
            "",
            data.hygiene_note,
        ]
    )


def _render_compliance(data: ReportData) -> str:
    return "\n".join(
        [
            "## Scope & Compliance Notice",
            "",
            "This report summarizes a passive metadata audit of publicly available "
            "documents inside the confirmed scope listed above; it is not an "
            "exploitation test.",
            "",
            data.compliance_notice,
        ]
    )


def _render_findings(data: ReportData) -> str:
    cards = [_render_finding(finding) for finding in data.findings]
    return "\n".join(["## Findings", "", "\n\n---\n\n".join(cards)])


def _render_finding(finding: ReportFindingData) -> str:
    """One finding card, fields in the order mandated by subtask 4.2."""
    severity_label = (
        finding.severity.value.capitalize() if finding.severity is not None else "Unclassified"
    )
    reproduction = "\n".join(
        f"{index}. {step}" for index, step in enumerate(finding.reproduction_steps, start=1)
    )
    return "\n".join(
        [
            f"### [{severity_label}] {finding.title}",
            "",
            f"- **Severity:** {severity_label}",
            f"- **Affected asset:** {_inline_code(finding.asset_final_url)} "
            f"(source: {_inline_code(finding.asset_source_url)}, "
            f"content-type: {_inline_code(finding.asset_content_type)})",
            f"- **Finding type:** {finding.type_label}",
            f"- **Metadata field:** {_inline_code(finding.field_source)}",
            "- **Evidence:**",
            _fenced_evidence(finding.evidence),
            f"- **Impact:** {_single_line(finding.impact)}",
            f"- **Explanation:** {_single_line(finding.explanation)}",
            "- **Reproduction steps:**",
            _indent(reproduction),
            "- **Remediation:**",
            _indent(finding.remediation),
        ]
    )


def _fenced_evidence(evidence: str) -> str:
    """Fenced ``text`` block; the fence outlives any backtick run in the snippet.

    Only the fence lines are indented (to nest under the list item); content
    lines stay untouched so the exported file keeps the evidence byte-for-byte.
    """
    fence = "`" * max(3, longest_backtick_run(evidence) + 1)
    return f"  {fence}text\n{evidence}\n  {fence}"


def _inline_code(text: str) -> str:
    """Inline code span that survives backticks in the value itself."""
    run = longest_backtick_run(text)
    if run == 0:
        return f"`{text}`"
    fence = "`" * (run + 1)
    return f"{fence} {text} {fence}"


def _single_line(text: str) -> str:
    """Collapse internal whitespace so prose fits a single Markdown bullet."""
    return _WHITESPACE_RUN_RE.sub(" ", text).strip()


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())
