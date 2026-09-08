"""JsonReportExporter: machine-readable export validated against the schema (4.3.2).

The payload is built through :func:`build_report_document`, serialized with
``model_dump(mode="json")`` (enums lowercase, datetimes as ISO-8601 Z) and
re-validated with ``model_validate`` before writing, per the task contract.
"""

import json
from pathlib import Path

from metatracer.reports.builder import DEFAULT_REPORTS_DIR, ReportData, report_filename_stem
from metatracer.reports.schemas import ReportDocument, build_report_document


class JsonReportExporter:
    """Writes the report as indented UTF-8 JSON (subtask 4.3.2)."""

    def __init__(self, output_dir: str | Path = DEFAULT_REPORTS_DIR) -> None:
        self._output_dir = Path(output_dir)

    def export(self, data: ReportData) -> Path:
        """Validate, serialize and write the ``.json`` file; returns its path."""
        document = build_report_document(data)
        # Explicit round-trip: validate the JSON-mode payload before writing.
        payload = ReportDocument.model_validate(document.model_dump(mode="json"))
        path = self._output_dir / f"{report_filename_stem(data)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
