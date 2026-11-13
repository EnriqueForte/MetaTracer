"""finding_type=secret stays on the closed allowlist and extracted metadata."""

from metatracer.classification.classifier import classify_heuristically
from metatracer.classification.rubric import HEURISTIC_CEILINGS, ceiling_for
from metatracer.classification.templates import template_for
from metatracer.db.models import (
    Confidence,
    DetectorMethod,
    Finding,
    FindingType,
    RawMetadataItem,
    Severity,
)
from metatracer.detectors.debug import DebugCommentDetector
from metatracer.detectors.registry import DetectorRegistry
from metatracer.detectors.secrets import SecretDetector

_AWS_EXAMPLE = "AKIAIOSFODNN7EXAMPLE"
_GITHUB_PAT = "ghp_" + ("A" * 36)
_PEM = "-----BEGIN RSA PRIVATE KEY-----"
_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)


def _item(value: str, key: str = "Author") -> RawMetadataItem:
    return RawMetadataItem(asset_id="asset-1", namespace="pdfinfo", key=key, value=value)


def _snippets(value: str, key: str = "Author") -> list[str]:
    return [draft.evidence_snippet for draft in SecretDetector().detect([_item(value, key)])]


def test_closed_allowlist_matches_and_open_password_does_not() -> None:
    assert _snippets(_AWS_EXAMPLE) == [_AWS_EXAMPLE]
    assert _snippets(_GITHUB_PAT) == [_GITHUB_PAT]
    assert _snippets(_PEM) == [_PEM]
    assert _snippets(f"token {_JWT} leftover") == [_JWT]
    assert _snippets("password=hunter2") == []
    assert _snippets("ghp_short") == []
    assert _snippets("AKIA123") == []
    assert _snippets("-----BEGIN CERTIFICATE-----") == []
    assert _snippets("eyJhbGciOiJub25lIn0.e30") == []


def test_clean_secret_is_not_debug_comment() -> None:
    items = [_item(_AWS_EXAMPLE, key="Comments")]
    assert DebugCommentDetector().detect(items) == []
    secrets = SecretDetector().detect(items)
    assert len(secrets) == 1
    assert secrets[0].finding_type is FindingType.secret
    assert "severity" not in secrets[0].__dataclass_fields__


def test_todo_plus_secret_keeps_both_types() -> None:
    items = [_item(f"TODO: rotate {_AWS_EXAMPLE}", key="Comments")]
    types = {draft.finding_type for draft in DetectorRegistry().detect_all(items)}
    assert FindingType.secret in types
    assert FindingType.debug_comment in types


def test_detector_never_assigns_severity_and_snippet_is_the_match() -> None:
    draft = SecretDetector().detect([_item(f"see {_AWS_EXAMPLE} please")])[0]
    assert draft.finding_type is FindingType.secret
    assert draft.evidence_snippet == _AWS_EXAMPLE
    assert draft.confidence is Confidence.medium
    assert draft.detector_method is DetectorMethod.rule
    assert "severity" not in draft.__dataclass_fields__


def test_ceiling_and_classifier_require_the_pattern() -> None:
    assert set(HEURISTIC_CEILINGS) == set(FindingType)
    assert ceiling_for(FindingType.secret) is Severity.critical
    hit = Finding(
        run_id="r",
        asset_id="a",
        finding_type=FindingType.secret,
        field_source="pdfinfo:Author",
        evidence_snippet=_AWS_EXAMPLE,
        dedup_signature="x",
        detector_method=DetectorMethod.rule,
        confidence=Confidence.high,
    )
    miss = Finding(
        run_id="r",
        asset_id="a",
        finding_type=FindingType.secret,
        field_source="pdfinfo:Author",
        evidence_snippet="password=hunter2",
        dedup_signature="y",
        detector_method=DetectorMethod.rule,
        confidence=Confidence.medium,
    )
    assert classify_heuristically(hit).severity is Severity.critical
    assert classify_heuristically(miss).severity is Severity.info
    prose = template_for(FindingType.secret, Severity.critical)
    assert "closed" in prose.justification
    assert "exploit" not in prose.impact.lower()
