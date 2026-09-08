"""ContextOptimizer tests (TASK-05, subtask 5.1).

The payload sent to the model is the security boundary: exactly the closed
contract keys, no bytes, no empty values, budgeted in tokens and capped per
run with type prioritization.
"""

import json
import logging

import pytest

from metatracer.agents.optimizer import (
    MAX_CALL_TOKENS,
    PAYLOAD_KEYS,
    ContextOptimizer,
    _ensure_json_safe,
    estimate_tokens,
)
from metatracer.core.exceptions import MetaTracerError
from metatracer.db.models import FindingType, Severity

from .conftest import make_asset, make_finding

RUN = "run-1"


def test_payload_contains_exactly_the_contract_keys() -> None:
    asset = make_asset(RUN)
    finding = make_finding(RUN, asset.id, severity=Severity.high)
    entry = ContextOptimizer(max_findings=10).build_entry(finding, asset, "target.com")
    assert set(entry.payload) == {
        "finding_type",
        "field_source",
        "evidence_snippet",
        "confidence",
        "heuristic_severity",
        "target_domain",
        "asset_content_type",
        "asset_url",
    }
    assert set(entry.payload) <= PAYLOAD_KEYS
    assert entry.payload["finding_type"] == "gps"
    assert entry.payload["heuristic_severity"] == "high"
    assert entry.payload["asset_url"] == "http://target.com/a.pdf"
    assert entry.finding_id == finding.id
    assert entry.had_baseline_severity is True


def test_null_and_empty_values_are_dropped() -> None:
    finding = make_finding(RUN, "asset-1", severity=None)  # no TASK-03 baseline yet
    entry = ContextOptimizer(max_findings=10).build_entry(finding, None, "target.com")
    # severity NULL and missing asset fields must not appear as null template values.
    assert "heuristic_severity" not in entry.payload
    assert "asset_content_type" not in entry.payload
    assert "asset_url" not in entry.payload
    assert entry.had_baseline_severity is False
    assert entry.payload["target_domain"] == "target.com"


def test_payload_is_json_serializable_text_only() -> None:
    asset = make_asset(RUN)
    finding = make_finding(RUN, asset.id, severity=Severity.medium)
    entry = ContextOptimizer(max_findings=10).build_entry(finding, asset, "target.com")
    text = json.dumps(entry.payload, ensure_ascii=False)
    assert text  # serializable
    assert all(isinstance(value, str) for value in entry.payload.values())


def test_bytes_values_are_rejected() -> None:
    with pytest.raises(MetaTracerError, match="never sees bytes"):
        _ensure_json_safe({"evidence_snippet": b"\xff\xd8binary"})  # type: ignore[dict-item]


def test_cost_cap_prioritizes_by_type(caplog: pytest.LogCaptureFixture) -> None:
    asset = make_asset(RUN)
    rows = [
        (make_finding(RUN, asset.id, finding_type=FindingType.email,
                      field_source="XMP:Creator", evidence_snippet="jane.doe@target.com"), asset),
        (make_finding(RUN, asset.id, finding_type=FindingType.software_version,
                      field_source="PDF:Producer", evidence_snippet="Apache FOP 2.4"), asset),
        (make_finding(RUN, asset.id, finding_type=FindingType.gps), asset),
        (make_finding(RUN, asset.id, finding_type=FindingType.internal_path,
                      field_source="XMP:CreatorTool",
                      evidence_snippet="C:\\Users\\admin\\Projects\\Internal\\doc.pdf"), asset),
        (make_finding(RUN, asset.id, finding_type=FindingType.email,
                      field_source="XMP:MetadataDate",
                      evidence_snippet="john.smith@target.com"), asset),
    ]
    with caplog.at_level(logging.WARNING, logger="metatracer.agents.optimizer"):
        entries = ContextOptimizer(max_findings=3).optimize(rows, "target.com")
    kept_types = [entry.payload["finding_type"] for entry in entries]
    # Selection follows gps -> internal_path -> debug_comment -> email ->
    # software_version; the kept findings preserve their original scan order.
    assert kept_types == ["email", "gps", "internal_path"]
    assert entries[0].payload["evidence_snippet"] == "jane.doe@target.com"
    assert "context budget cut" in caplog.text
    assert "dropping 2" in caplog.text


def test_cut_is_stable_within_a_type() -> None:
    asset = make_asset(RUN)
    rows = [
        (make_finding(RUN, asset.id, finding_type=FindingType.email,
                      field_source="XMP:A", evidence_snippet="first.person@target.com"), asset),
        (make_finding(RUN, asset.id, finding_type=FindingType.email,
                      field_source="XMP:B", evidence_snippet="second.person@target.com"), asset),
        (make_finding(RUN, asset.id, finding_type=FindingType.email,
                      field_source="XMP:C", evidence_snippet="third.person@target.com"), asset),
    ]
    entries = ContextOptimizer(max_findings=2).optimize(rows, "target.com")
    kept = [entry.payload["evidence_snippet"] for entry in entries]
    assert kept == ["first.person@target.com", "second.person@target.com"]


def test_no_cut_when_under_the_cap(caplog: pytest.LogCaptureFixture) -> None:
    asset = make_asset(RUN)
    rows = [(make_finding(RUN, asset.id), asset)]
    with caplog.at_level(logging.WARNING, logger="metatracer.agents.optimizer"):
        entries = ContextOptimizer(max_findings=50).optimize(rows, "target.com")
    assert len(entries) == 1
    assert "context budget cut" not in caplog.text


def test_oversized_snippet_is_truncated_to_the_token_budget(
    caplog: pytest.LogCaptureFixture,
) -> None:
    asset = make_asset(RUN)
    huge = "A" * 10_000
    finding = make_finding(
        RUN,
        asset.id,
        finding_type=FindingType.debug_comment,
        field_source="XMP:Description",
        evidence_snippet="TODO: " + huge,
    )
    with caplog.at_level(logging.WARNING, logger="metatracer.agents.optimizer"):
        entry = ContextOptimizer(max_findings=10).build_entry(finding, asset, "target.com")
    text = json.dumps(entry.payload, ensure_ascii=False)
    assert estimate_tokens(text) <= MAX_CALL_TOKENS
    assert entry.payload["evidence_snippet"].endswith("...")
    assert len(entry.payload["evidence_snippet"]) < len(huge)
    assert "truncated" in caplog.text


def test_estimate_tokens_is_len_over_four() -> None:
    assert estimate_tokens("abcd" * 100) == 100
    assert estimate_tokens("") == 1
