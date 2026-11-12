"""internal_endpoint and cloud_storage stay inside the evidence that triggered them."""

from metatracer.classification.classifier import classify_heuristically
from metatracer.classification.rubric import ceiling_for
from metatracer.classification.templates import template_for
from metatracer.db.models import (
    Confidence,
    DetectorMethod,
    Finding,
    FindingType,
    RawMetadataItem,
    Severity,
)
from metatracer.detectors.network import CloudStorageDetector, InternalEndpointDetector
from metatracer.detectors.registry import DetectorRegistry


def _item(value: str, key: str = "Comments") -> RawMetadataItem:
    return RawMetadataItem(asset_id="asset-1", namespace="pdfinfo", key=key, value=value)


def _snippets(detector: object, value: str) -> list[str]:
    return [draft.evidence_snippet for draft in detector.detect([_item(value)])]  # type: ignore[attr-defined]


def test_rfc1918_and_internal_hosts_are_endpoints() -> None:
    detector = InternalEndpointDetector()
    assert _snippets(detector, "see 10.1.2.3 and 192.168.0.9") == ["10.1.2.3", "192.168.0.9"]
    assert _snippets(detector, "jump 172.16.0.4 then 172.31.255.1") == [
        "172.16.0.4",
        "172.31.255.1",
    ]
    assert _snippets(detector, "db.corp and api.svc.cluster.local") == [
        "api.svc.cluster.local",
        "db.corp",
    ]
    assert set(_snippets(detector, "vpn.internal files.lan printer.local")) == {
        "vpn.internal",
        "files.lan",
        "printer.local",
    }
    assert _snippets(detector, "8.8.8.8 172.15.0.1 172.32.0.1 127.0.0.1 localhost") == []
    assert _snippets(detector, "Apache 2.4.52") == []
    # An email is the email detector's job; @host.corp is not an endpoint.
    assert _snippets(detector, "jane.doe@target.corp") == []
    assert _snippets(detector, "security.lead@acme-corp.internal") == []


def test_cloud_urls_are_recorded_without_the_query_string() -> None:
    detector = CloudStorageDetector()
    snippets = _snippets(
        detector,
        "backup at https://logs.s3.amazonaws.com/2024/a?X-Amz-Signature=secret",
    )
    assert snippets == ["https://logs.s3.amazonaws.com/2024/a"]
    assert "secret" not in snippets[0]
    assert _snippets(detector, "https://files.blob.core.windows.net/docs") == [
        "https://files.blob.core.windows.net/docs"
    ]
    assert _snippets(detector, "https://storage.googleapis.com/acme-logs/2024") == [
        "https://storage.googleapis.com/acme-logs/2024"
    ]
    assert _snippets(detector, "nots3.amazonaws.com and https://example.com/file") == []
    assert _snippets(detector, "s3://acme-logs/2024/a.bin") == ["s3://acme-logs/2024/a.bin"]
    assert _snippets(detector, "gs://acme-logs/2024/a.bin") == ["gs://acme-logs/2024/a.bin"]
    assert _snippets(
        detector, "https://acme.nyc3.digitaloceanspaces.com/bucket/a?sig=secret"
    ) == ["https://acme.nyc3.digitaloceanspaces.com/bucket/a"]
    assert _snippets(detector, "https://acme.s3.wasabisys.com/docs/a") == [
        "https://acme.s3.wasabisys.com/docs/a"
    ]


def test_ceilings_hold_and_the_storage_url_is_not_described_as_fetched() -> None:
    assert ceiling_for(FindingType.internal_endpoint) is Severity.medium
    assert ceiling_for(FindingType.cloud_storage) is Severity.high
    endpoint = Finding(
        run_id="r",
        asset_id="a",
        finding_type=FindingType.internal_endpoint,
        field_source="pdfinfo:Comments",
        evidence_snippet="10.1.2.3",
        dedup_signature="x",
        detector_method=DetectorMethod.rule,
        confidence=Confidence.high,
    )
    storage = Finding(
        run_id="r",
        asset_id="a",
        finding_type=FindingType.cloud_storage,
        field_source="pdfinfo:Comments",
        evidence_snippet="https://logs.s3.amazonaws.com/2024/a",
        dedup_signature="y",
        detector_method=DetectorMethod.rule,
        confidence=Confidence.medium,
    )
    assert classify_heuristically(endpoint).severity is Severity.medium
    assessment = classify_heuristically(storage)
    assert assessment.severity is Severity.high
    prose = template_for(FindingType.cloud_storage, Severity.high)
    assert "did not request" in prose.justification


def test_registry_includes_both_detectors() -> None:
    types = {
        draft.finding_type
        for draft in DetectorRegistry().detect_all(
            [_item("gateway 10.8.0.4; mirror https://cdn.r2.cloudflarestorage.com/pub")]
        )
    }
    assert FindingType.internal_endpoint in types
    assert FindingType.cloud_storage in types
