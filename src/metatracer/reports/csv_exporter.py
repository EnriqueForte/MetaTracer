"""CsvReportExporter: tabular view of a run for triage and tooling (TASK-18, v2.2).

One row per finding with the *same* columns as the JSON report (TASK-04,
subtask 4.3.2), so an operator can open a run in a spreadsheet, correlate it
with the history or feed external triage tooling without re-parsing Markdown.

Contract notes:

- ``severity`` is the lowercase enum value, or an empty string for
  unclassified findings (NULL). The Markdown report spells "Unclassified"
  for presentation; a CSV must stay parseable, so the empty string is the
  explicit "not yet classified" sentinel.
- ``finding_type`` / ``confidence`` are lowercase enum values (data layer).
- ``evidence`` is the persisted snippet byte-for-byte (whitespace-trimmed),
  exactly like the JSON exporter.
- Empty prose renders as ``Not generated (heuristic baseline)`` (same
  placeholder as the Markdown/JSON exporters) — the export never crashes on
  fields TASK-05 has not filled.

The writer is the stdlib ``csv`` module (RFC 4180, ``QUOTE_MINIMAL``), the
file is UTF-8 **with BOM** so spreadsheet apps treat it as UTF-8 instead of
latin-1. Cells whose text starts with ``=``, ``+``, ``-``, ``@``, tab or CR
are prefixed with ``'`` so a spreadsheet does not evaluate them as formulas
(TASK-27). No network, no LLM, no reads of the original asset files: the data
comes from :class:`ReportData` only.
"""

import csv
from pathlib import Path

from metatracer.reports.builder import (
    DEFAULT_REPORTS_DIR,
    PROSE_PLACEHOLDER,
    ReportData,
    report_filename_stem,
)

# Same columns as the JSON report, one per finding, in this order.
CSV_COLUMNS = [
    "run_id",
    "target",
    "severity",
    "finding_type",
    "confidence",
    "asset_url",
    "field",
    "evidence",
    "impact",
    "explanation",
    "remediation",
    "triage_status",  # TASK-35, lowercase enum value
]


class CsvReportExporter:
    """Writes the report as a RFC 4180 CSV file (subtask 18.2)."""

    def __init__(self, output_dir: str | Path = DEFAULT_REPORTS_DIR) -> None:
        self._output_dir = Path(output_dir)

    def export(self, data: ReportData) -> Path:
        """Write the ``.csv`` file with header + one row per finding."""
        path = self._output_dir / f"{report_filename_stem(data)}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig writes a BOM so spreadsheet apps detect UTF-8 correctly.
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            for finding in data.findings:
                writer.writerow(_row(data, finding))
        return path


# Spreadsheet formula triggers (OWASP CSV injection). Prefix, do not strip:
# the evidence text stays recoverable and a sheet treats the cell as text.
_FORMULA_TRIGGERS = frozenset("=+-@\t\r")


def neutralize_spreadsheet_formula(value: str) -> str:
    """Prefix formula-like text so a spreadsheet will not evaluate the cell."""
    if value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _row(data: ReportData, finding) -> dict[str, str]:
    """Map one report finding onto the CSV columns (lowercase enums)."""
    raw = {
        "run_id": data.run_id,
        "target": data.target,
        "severity": finding.severity.value if finding.severity is not None else "",
        "finding_type": finding.finding_type.value,
        "confidence": finding.confidence.value,
        "asset_url": finding.asset_final_url,
        "field": finding.field_source,
        "evidence": finding.evidence if finding.evidence else PROSE_PLACEHOLDER,
        "impact": finding.impact,
        "explanation": finding.explanation,
        "remediation": finding.remediation,
        "triage_status": finding.triage_status.value,
    }
    return {key: neutralize_spreadsheet_formula(value) for key, value in raw.items()}