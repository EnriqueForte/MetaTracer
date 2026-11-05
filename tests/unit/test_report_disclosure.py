"""Fase 5: coverage is stated, and redaction stays in the exported copy."""

from datetime import UTC, datetime

from metatracer.db.models import Confidence, FindingType, ReasoningDepth, Severity
from metatracer.reports.builder import ReportCoverage, ReportData, ReportFindingData, SeverityCounts
from metatracer.reports.disclosure import (
    LIMITATIONS,
    Redaction,
    apply_redaction,
    coverage_from_stats,
)
from metatracer.reports.markdown import render_markdown
from metatracer.reports.schemas import build_report_document


def _finding(**overrides) -> ReportFindingData:
    values = {
        "id": "f1",
        "title": "Email Address Disclosure",
        "finding_type": FindingType.email,
        "type_label": "Email",
        "severity": Severity.low,
        "confidence": Confidence.high,
        "asset_source_url": "https://target.example/a.pdf",
        "asset_final_url": "https://target.example/a.pdf",
        "asset_content_type": "application/pdf",
        "field_source": "pdfinfo:Author",
        "evidence": "Author: ada@target.example",
        "impact": "Contact ada@target.example",
        "explanation": "Observed.",
        "remediation": "Remove it.",
        "reproduction_steps": ("Open the public file.",),
    }
    values.update(overrides)
    return ReportFindingData(**values)


def _report(finding: ReportFindingData, coverage: ReportCoverage | None = None) -> ReportData:
    return ReportData(
        metatracer_version="0.6.0",
        run_id="run-1",
        target="target.example",
        scope=("target.example",),
        generated_at=datetime(2026, 10, 29, tzinfo=UTC),
        reasoning_depth=ReasoningDepth.standard,
        total_assets=1,
        severity_counts=SeverityCounts(low=1),
        hygiene_note="note",
        compliance_notice="notice",
        findings=(finding,),
        coverage=coverage or ReportCoverage(),
    )


def test_limits_reached_are_named_in_the_report() -> None:
    coverage = coverage_from_stats(
        '{"budget": {"max_pages": 1}, "limits_hit": ["max_pages"], "pages_crawled": 1}'
    )
    text = render_markdown(_report(_finding(), coverage))
    assert "Limits reached: max_pages." in text
    assert "Apache Tika and MediaInfo are not used" in text
    assert "not treat an archived URL as current exposure" in text
    assert "Redaction applied to this file: none." in text


def test_missing_counters_are_not_reported_as_zero_limits() -> None:
    text = render_markdown(_report(_finding()))
    assert "Discovery counters were not recorded for this run." in text
    assert "Limits reached:" not in text


def test_contact_redaction_rewrites_the_file_and_leaves_the_source_card() -> None:
    original = _finding()
    exported = apply_redaction(_report(original), Redaction.contacts)
    assert original.evidence == "Author: ada@target.example"
    assert exported.findings[0].evidence == "Author: [redacted-email]"
    assert "ada@target.example" not in exported.findings[0].impact
    document = build_report_document(exported)
    assert document.redaction == "contacts"
    assert document.schema_version == "1.1"
    assert document.findings[0].historical is False
    assert document.findings[0].capture_date is None
    assert "current exposure" in LIMITATIONS


def test_coordinate_redaction_replaces_a_gps_snippet() -> None:
    original = _finding(
        finding_type=FindingType.gps,
        type_label="GPS / Coordinates",
        evidence="Latitude: 40.416775, Longitude: -3.703790",
        impact="The point is 40.416775, -3.703790.",
    )
    exported = apply_redaction(_report(original), "coordinates")
    assert original.evidence.startswith("Latitude:")
    assert exported.findings[0].evidence == "[redacted-coordinates]"
    assert "40.416775" not in exported.findings[0].impact


def test_none_redaction_does_not_rewrite_evidence() -> None:
    original = _finding()
    exported = apply_redaction(_report(original), Redaction.none)
    assert exported.findings[0].evidence == original.evidence
    assert exported.redaction == "none"


def test_all_redaction_covers_contacts_and_coordinates() -> None:
    original = _finding(
        finding_type=FindingType.gps,
        type_label="GPS / Coordinates",
        evidence="Latitude: 40.416775, Longitude: -3.703790",
        impact="Ask ada@target.example about 40.416775, -3.703790.",
    )
    exported = apply_redaction(_report(original), Redaction.all)
    assert original.evidence.startswith("Latitude:")
    assert original.impact.startswith("Ask ada@")
    assert exported.findings[0].evidence == "[redacted-coordinates]"
    assert "ada@" not in exported.findings[0].impact
    assert "40.416775" not in exported.findings[0].impact
    assert exported.redaction == "all"
