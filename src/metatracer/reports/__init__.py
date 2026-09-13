"""Report generation and exporters (TASK-04).

Pipeline: :class:`ReportBuilder` (read-only DB -> :class:`ReportData`) feeds
the Markdown, JSON and HTML exporters. The module does no network I/O, never
opens the original asset files and never calls the LLM; it only reads the
database and writes report files.
"""

from metatracer.reports.bounty import BountyExporter, render_bounty
from metatracer.reports.builder import (
    COMPLIANCE_NOTICE,
    DEFAULT_REPORTS_DIR,
    PROSE_PLACEHOLDER,
    REPORT_TITLE,
    ReportBuilder,
    ReportData,
    ReportFindingData,
    SeverityCounts,
    iso_z,
    report_filename_stem,
    run_id_short,
    slugify_target,
)
from metatracer.reports.csv_exporter import CSV_COLUMNS, CsvReportExporter
from metatracer.reports.filters import filter_findings
from metatracer.reports.html import HtmlReportExporter, render_html
from metatracer.reports.json_exporter import JsonReportExporter
from metatracer.reports.markdown import MarkdownReportExporter, render_markdown
from metatracer.reports.schemas import (
    ReportDocument,
    ReportFinding,
    ReportSeverityCounts,
    ReportSummary,
    build_report_document,
)

__all__ = [
    "BountyExporter",
    "CSV_COLUMNS",
    "COMPLIANCE_NOTICE",
    "CsvReportExporter",
    "DEFAULT_REPORTS_DIR",
    "PROSE_PLACEHOLDER",
    "REPORT_TITLE",
    "HtmlReportExporter",
    "JsonReportExporter",
    "MarkdownReportExporter",
    "filter_findings",
    "render_bounty",
    "render_html",
    "ReportBuilder",
    "ReportData",
    "ReportDocument",
    "ReportFinding",
    "ReportFindingData",
    "ReportSeverityCounts",
    "ReportSummary",
    "SeverityCounts",
    "build_report_document",
    "iso_z",
    "render_markdown",
    "report_filename_stem",
    "run_id_short",
    "slugify_target",
]
