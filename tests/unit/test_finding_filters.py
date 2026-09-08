"""Finding filter helper tests (TASK-08, subtask 8.2)."""

from metatracer.db.models import Confidence, FindingType, Severity
from metatracer.reports.builder import ReportFindingData
from metatracer.reports.filters import filter_findings


def _finding(
    *,
    finding_type: FindingType = FindingType.gps,
    severity: Severity | None = Severity.high,
    confidence: Confidence = Confidence.high,
    title: str = "GPS leak",
    evidence: str = "Latitude: 40.4168",
    field_source: str = "EXIF:GPSInfo",
    url: str = "https://target.com/photo.jpg",
) -> ReportFindingData:
    return ReportFindingData(
        id="f1",
        title=title,
        finding_type=finding_type,
        type_label=finding_type.value,
        severity=severity,
        confidence=confidence,
        asset_source_url=url,
        asset_final_url=url,
        asset_content_type="image/jpeg",
        field_source=field_source,
        evidence=evidence,
        impact="impact",
        explanation="explanation",
        remediation="fix it",
        reproduction_steps=("inspect",),
    )


GPS = _finding()
EMAIL = _finding(
    finding_type=FindingType.email,
    severity=Severity.medium,
    confidence=Confidence.medium,
    title="Email in Author",
    evidence="security.lead@acme-corp.test",
    field_source="pdfinfo:Author",
    url="https://target.com/report.pdf",
)


def test_no_criteria_returns_all_in_order() -> None:
    assert filter_findings([GPS, EMAIL]) == [GPS, EMAIL]


def test_severity_filter() -> None:
    assert filter_findings([GPS, EMAIL], severity=Severity.high) == [GPS]


def test_type_filter() -> None:
    assert filter_findings([GPS, EMAIL], finding_type=FindingType.email) == [EMAIL]


def test_confidence_filter() -> None:
    assert filter_findings([GPS, EMAIL], confidence=Confidence.medium) == [EMAIL]


def test_query_is_casefold_and_searches_evidence_title_field_url() -> None:
    assert filter_findings([GPS, EMAIL], q="ACME-CORP") == [EMAIL]
    assert filter_findings([GPS, EMAIL], q="gpsinfo") == [GPS]
    assert filter_findings([GPS, EMAIL], q="PHOTO.JPG") == [GPS]
    assert filter_findings([GPS, EMAIL], q="author") == [EMAIL]


def test_combined_filters_are_and() -> None:
    assert filter_findings(
        [GPS, EMAIL],
        severity=Severity.high,
        finding_type=FindingType.email,
    ) == []
    assert filter_findings(
        [GPS, EMAIL],
        finding_type=FindingType.email,
        q="acme",
    ) == [EMAIL]


def test_blank_query_is_ignored() -> None:
    assert filter_findings([GPS, EMAIL], q="   ") == [GPS, EMAIL]
