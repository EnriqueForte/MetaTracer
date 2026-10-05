"""TASK-34: detector false positives, secret values, and new path roots."""

from metatracer.classification.anchor import parse_gps_line
from metatracer.classification.classifier import classify_heuristically
from metatracer.db.models import (
    Confidence,
    DetectorMethod,
    Finding,
    FindingType,
    RawMetadataItem,
    Severity,
)
from metatracer.detectors import dedup_signature
from metatracer.detectors.email import EmailDetector
from metatracer.detectors.gps import GpsDetector
from metatracer.detectors.paths import InternalPathDetector

ASSET = "asset-1"


def _item(namespace: str, key: str, value: str) -> RawMetadataItem:
    return RawMetadataItem(asset_id=ASSET, namespace=namespace, key=key, value=value)


def _emails(value: str) -> list[str]:
    drafts = EmailDetector().detect([_item("pdfinfo", "Author", value)])
    return [draft.evidence_snippet for draft in drafts]


def test_filename_and_placeholder_emails_are_not_findings() -> None:
    for value in (
        "image@2x.png",
        "logo@3x.jpg",
        "foo@example.net",
        "a@b.test",
        "user@email.com",
        "user@domain.com",
        "user@test.com",
        "a@b.invalid",
        "a@b.example",
        "a@b.localhost",
    ):
        assert _emails(value) == [], value
    assert _emails("contact john@acme.com please") == ["john@acme.com"]


def test_near_zero_gps_is_not_a_finding() -> None:
    items = [
        _item("exif", "GPSLatitude", '["0/1", "0/1", "1/1000"]'),
        _item("exif", "GPSLatitudeRef", "N"),
        _item("exif", "GPSLongitude", '["0/1", "0/1", "1/1000"]'),
        _item("exif", "GPSLongitudeRef", "E"),
    ]
    assert GpsDetector().detect(items) == []
    assert parse_gps_line("Latitude: 0.000001, Longitude: 0.000001") is None
    real = [
        _item("exif", "GPSLatitude", '["40/1", "24/1", "4635/100"]'),
        _item("exif", "GPSLatitudeRef", "N"),
        _item("exif", "GPSLongitude", '["3/1", "42/1", "7900/100"]'),
        _item("exif", "GPSLongitudeRef", "W"),
    ]
    assert len(GpsDetector().detect(real)) == 1


def test_new_internal_paths_are_medium_and_usr_stays_silent() -> None:
    cases = [
        "/private/tmp/build.o",
        "/private/var/folders/ab/x",
        r"C:\Program Files\Adobe\app.exe",
        r"C:\ProgramData\vendor\cache.db",
        r"C:\Temp\AppData\Local\secret.txt",
        "~alice/projects/notes.txt",
    ]
    for value in cases:
        drafts = InternalPathDetector().detect([_item("pdfinfo", "Comments", f"see {value}")])
        assert [draft.evidence_snippet for draft in drafts] == [value], value
        assert drafts[0].confidence is Confidence.medium, value
    assert (
        InternalPathDetector().detect([_item("pdfinfo", "Comments", "libs in /usr/lib")]) == []
    )


def test_users_appdata_stays_one_high_confidence_path() -> None:
    value = r"C:\Users\jdoe\AppData\Roaming\app.ini"
    drafts = InternalPathDetector().detect([_item("pdfinfo", "Comments", value)])
    assert [draft.evidence_snippet for draft in drafts] == [value]
    assert drafts[0].confidence is Confidence.high


def _classify(finding_type: FindingType, snippet: str) -> Severity:
    finding = Finding(
        run_id="run",
        asset_id="asset",
        finding_type=finding_type,
        field_source="html:comment",
        evidence_snippet=snippet,
        dedup_signature=dedup_signature("asset", finding_type, snippet),
        detector_method=DetectorMethod.rule,
        confidence=Confidence.high,
    )
    return classify_heuristically(finding, None).severity


def test_secret_value_is_critical_and_bare_word_is_medium() -> None:
    assert _classify(FindingType.debug_comment, "remove staging credentials") is Severity.medium
    assert _classify(FindingType.debug_comment, "password=hunter2") is Severity.critical
    assert _classify(FindingType.debug_comment, "AKIAIOSFODNN7EXAMPLE") is Severity.critical
    token = "ghp_" + ("a" * 36)
    assert _classify(FindingType.debug_comment, token) is Severity.critical
