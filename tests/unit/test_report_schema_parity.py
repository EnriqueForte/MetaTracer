"""CSV <-> JSON schema parity guard (T4, audit finding ARC-06).

The JSON report and the CSV report describe the same findings through two
independently maintained field lists:

- ``ReportFinding`` (``reports/schemas.py``) — the machine-readable card;
- ``CSV_COLUMNS`` (``reports/csv_exporter.py``) — the flat tabular row.

Nothing in the code forces them to agree, so a new finding field could ship in
one exporter and silently miss the other. This module pins the mapping and
fails when either side changes without an explicit decision.

The two intentional asymmetries are declared below, not inferred:

- ``id`` is absent from the CSV: the CSV row already carries ``run_id`` and
  ``target`` context, and the id is not needed to triage in a spreadsheet.
- ``reproduction_steps`` is absent from the CSV: it is a multi-line list that
  would break a spreadsheet cell (the Markdown/Bounty exports keep it, the
  JSON keeps it as a list).

Everything else must map 1:1 (``type`` -> ``finding_type`` is the only rename).
"""

from metatracer.reports.csv_exporter import CSV_COLUMNS
from metatracer.reports.schemas import ReportFinding

# JSON field -> CSV column. Only ``type`` is renamed; the rest keep their name.
_FIELD_TO_COLUMN: dict[str, str] = {
    "type": "finding_type",
    "severity": "severity",
    "confidence": "confidence",
    "asset_url": "asset_url",
    "field": "field",
    "evidence": "evidence",
    "impact": "impact",
    "explanation": "explanation",
    "remediation": "remediation",
    "triage_status": "triage_status",
}

# Deliberate exclusions, each with its reason (see the module docstring).
_JSON_ONLY: frozenset[str] = frozenset({"id", "reproduction_steps"})

# CSV columns that are row context, not a projection of one JSON finding field.
_CSV_ONLY: frozenset[str] = frozenset({"run_id", "target"})


def test_every_json_finding_field_is_mapped_or_explicitly_excluded() -> None:
    """A new ReportFinding field must be mapped to a CSV column or excluded."""
    json_fields = set(ReportFinding.model_fields)
    mapped = set(_FIELD_TO_COLUMN) | _JSON_ONLY
    unmapped = json_fields - mapped
    assert not unmapped, (
        "ReportFinding gained field(s) with no CSV mapping decision: "
        f"{sorted(unmapped)}. Add them to _FIELD_TO_COLUMN (and CSV_COLUMNS) "
        "or to _JSON_ONLY with a documented reason."
    )


def test_every_mapped_json_field_still_exists() -> None:
    """A renamed/deleted JSON field must not leave a stale mapping behind."""
    json_fields = set(ReportFinding.model_fields)
    stale = set(_FIELD_TO_COLUMN) - json_fields
    assert not stale, f"mapping references field(s) no longer on ReportFinding: {sorted(stale)}"


def test_every_csv_column_is_mapped_or_row_context() -> None:
    """A new CSV column must come from a JSON field or be declared row context."""
    expected = set(_FIELD_TO_COLUMN.values()) | _CSV_ONLY
    actual = set(CSV_COLUMNS)
    assert actual == expected, (
        "CSV_COLUMNS and the JSON mapping diverged. "
        f"Missing from CSV: {sorted(expected - actual)}; "
        f"unmapped CSV columns: {sorted(actual - expected)}."
    )


def test_no_csv_column_is_declared_twice() -> None:
    """The rename ``type -> finding_type`` must not collide with another column."""
    columns = list(_FIELD_TO_COLUMN.values())
    assert len(columns) == len(set(columns)), "duplicate CSV column in the mapping"


def test_header_order_is_stable() -> None:
    """CSV_COLUMNS order is a contract (TASK-18); changing it is a decision.

    This pins the current order so a reordering shows up as a failing test
    instead of a surprise for spreadsheet-driven consumers.
    """
    assert CSV_COLUMNS == [
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
        "triage_status",
    ]