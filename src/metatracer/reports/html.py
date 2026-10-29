"""HtmlReportExporter: standalone HTML write-up (TASK-08, subtask 8.3).

Same content as the Markdown export, escaped with the stdlib so target-
controlled evidence, URLs and titles cannot inject markup. No CDN, no JS,
no asset bytes. A hunter can print-to-PDF from the browser; that is why
v1.1 does not add a PDF runtime dependency.
"""

from html import escape
from pathlib import Path

from metatracer.reports.builder import (
    DEFAULT_REPORTS_DIR,
    REPORT_TITLE,
    ReportData,
    ReportFindingData,
    iso_z,
    report_filename_stem,
)
from metatracer.reports.disclosure import disclosure_sections

_CSS = """
:root { color-scheme: dark; }
body { font-family: ui-sans-serif, system-ui, sans-serif; background: #0f172a;
       color: #e2e8f0; margin: 0; padding: 2rem; line-height: 1.5; }
main { max-width: 52rem; margin: 0 auto; }
h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid #334155;
     padding-bottom: 0.3rem; }
h3 { font-size: 1rem; margin-top: 1.5rem; }
dl { display: grid; grid-template-columns: 10rem 1fr; gap: 0.25rem 0.75rem; }
dt { color: #94a3b8; }
code, pre { font-family: ui-monospace, monospace; font-size: 0.85rem; }
pre { background: #020617; border: 1px solid #1e293b; padding: 0.75rem;
      white-space: pre-wrap; word-break: break-all; }
.card { border: 1px solid #1e293b; border-radius: 0.5rem; padding: 1rem 1.25rem;
        margin: 1rem 0; background: #0b1220; }
.notice { color: #cbd5e1; font-size: 0.9rem; }
footer { margin-top: 2rem; color: #64748b; font-size: 0.8rem; }
""".strip()


class HtmlReportExporter:
    """Writes the report as a self-contained ``.html`` file (subtask 8.3)."""

    def __init__(self, output_dir: str | Path = DEFAULT_REPORTS_DIR) -> None:
        self._output_dir = Path(output_dir)

    def export(self, data: ReportData) -> Path:
        path = self._output_dir / f"{report_filename_stem(data)}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_html(data), encoding="utf-8")
        return path


def render_html(data: ReportData) -> str:
    """Full HTML document; every target-controlled field is escaped."""
    findings = (
        "".join(_render_finding(finding) for finding in data.findings)
        if data.findings
        else "<p>No findings.</p>"
    )
    scope = ", ".join(_code(item) for item in data.scope) or "n/a"
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_t(REPORT_TITLE)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{_t(REPORT_TITLE)}</h1>"
        "<dl>"
        f"<dt>Target</dt><dd>{_code(data.target)}</dd>"
        f"<dt>Confirmed scope</dt><dd>{scope}</dd>"
        f"<dt>Run ID</dt><dd>{_code(data.run_id)}</dd>"
        f"<dt>Generated at (UTC)</dt><dd>{_t(iso_z(data.generated_at))}</dd>"
        f"<dt>Reasoning depth</dt><dd>{_t(data.reasoning_depth.value)}</dd>"
        f"<dt>MetaTracer version</dt><dd>{_t(data.metatracer_version)}</dd>"
        "</dl>"
        "<h2>Executive Summary</h2>"
        f"<p>{_t(data.executive_summary_line)}</p>"
        f"<p>{_t(data.hygiene_note)}</p>"
        "<h2>Scope &amp; Compliance Notice</h2>"
        '<p class="notice">This report summarizes a passive metadata audit of '
        "publicly available documents inside the confirmed scope listed above; "
        "it is not an exploitation test.</p>"
        f'<p class="notice">{_t(data.compliance_notice)}</p>'
        "<h2>Findings</h2>"
        f"{findings}"
        f"{_disclosure_html(data)}"
        "<footer>Authorized use only. Reproduction is inspection-only.</footer>"
        "</main></body></html>\n"
    )


def _render_finding(finding: ReportFindingData) -> str:
    severity_label = (
        finding.severity.value.capitalize() if finding.severity is not None else "Unclassified"
    )
    steps = "".join(f"<li>{_t(step)}</li>" for step in finding.reproduction_steps)
    triage = (
        f"<dt>Triage</dt><dd>{_t(finding.triage_label)}</dd>"
        if finding.triage_status.value != "open"
        else ""
    )
    return (
        f'<article class="card">'
        f"<h3>[{_t(severity_label)}] {_t(finding.title)}</h3>"
        "<dl>"
        f"<dt>Severity</dt><dd>{_t(severity_label)}</dd>"
        f"{triage}"
        f"<dt>Affected asset</dt><dd>{_code(finding.asset_final_url)} "
        f"(source: {_code(finding.asset_source_url)}, "
        f"content-type: {_code(finding.asset_content_type)})</dd>"
        f"<dt>Finding type</dt><dd>{_t(finding.type_label)}</dd>"
        f"<dt>Metadata field</dt><dd>{_code(finding.field_source)}</dd>"
        "</dl>"
        "<p><strong>Evidence</strong></p>"
        f"<pre>{_t(finding.evidence)}</pre>"
        f"<p><strong>Impact.</strong> {_t(finding.impact)}</p>"
        f"<p><strong>Explanation.</strong> {_t(finding.explanation)}</p>"
        "<p><strong>Reproduction steps</strong></p>"
        f"<ol>{steps}</ol>"
        f"<p><strong>Remediation.</strong> {_t(finding.remediation)}</p>"
        "<p><strong>Provenance.</strong> Live fetch of this asset; not an archive capture.</p>"
        "</article>"
    )


def _disclosure_html(data: ReportData) -> str:
    return "".join(
        f"<h2>{_t(title)}</h2><p>{_t(body)}</p>" for title, body in disclosure_sections(data)
    )


def _t(text: str) -> str:
    return escape(text, quote=True)


def _code(text: str) -> str:
    return f"<code>{_t(text)}</code>"
