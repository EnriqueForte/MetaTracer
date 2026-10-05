"""Heuristic risk classifier tests (TASK-03).

Covers the task's minimum set (rubric mapping, determinism, no invented CVEs,
empty evidence -> info), the DoD guarantees (every classified finding gets
exactly one severity of the closed set, heuristic ceilings hold, reproduction
steps carry no exploit payloads), the anti-hallucination anchor (3.2.1) and
the persistence pipeline (only NULL-severity findings are classified;
unanchored evidence is forced to info).
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.classification import (
    HEURISTIC_CEILINGS,
    RUBRIC_PROMPT_TEXT,
    ClassificationPipeline,
    HeuristicRiskClassifier,
    apply_assessment,
    cap_severity,
    ceiling_for,
    classify_heuristically,
    evidence_is_anchored,
    unanchored_assessment,
)
from metatracer.core.exceptions import MetaTracerError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    RawMetadataItem,
    Run,
    Severity,
)
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)
from metatracer.detectors import dedup_signature

SessionFactory = async_sessionmaker[AsyncSession]


def _finding(
    finding_type: FindingType,
    snippet: str,
    field_source: str = "pdfinfo:Comments",
    confidence: Confidence = Confidence.high,
) -> Finding:
    return Finding(
        run_id="run-1",
        asset_id="asset-1",
        finding_type=finding_type,
        field_source=field_source,
        evidence_snippet=snippet,
        dedup_signature=dedup_signature("asset-1", finding_type, snippet),
        detector_method=DetectorMethod.rule,
        confidence=confidence,
    )


def _classify(finding_type: FindingType, snippet: str, **kwargs) -> Severity:
    return classify_heuristically(_finding(finding_type, snippet, **kwargs)).severity


# --- Rubric mapping: internal_path (task minimum + rubric examples) ---


def test_windows_user_path_is_high() -> None:
    snippet = "C:\\Users\\admin\\SecretProject\\"
    assert _classify(FindingType.internal_path, snippet) is Severity.high


def test_unc_path_is_high() -> None:
    assert _classify(FindingType.internal_path, r"\\CORP-DC01\share\docs") is Severity.high


def test_unix_user_paths_are_high() -> None:
    for snippet in ("/home/jdoe/.ssh/config", "/Users/jdoe/Library/x.plist", "/root/.bashrc"):
        assert _classify(FindingType.internal_path, snippet) is Severity.high, snippet


def test_var_www_without_user_is_medium() -> None:
    for snippet in ("/var/www/html/index.php", "/var/www/intranet", "/var/www"):
        assert _classify(FindingType.internal_path, snippet) is Severity.medium, snippet


def test_var_www_with_user_segment_is_high() -> None:
    assert _classify(FindingType.internal_path, "/var/www/jdoe/site/index.php") is Severity.high


def test_windows_system_path_is_medium() -> None:
    assert _classify(FindingType.internal_path, r"C:\Windows\System32\drivers") is Severity.medium


def test_unrecognized_path_shape_is_info() -> None:
    assert _classify(FindingType.internal_path, "see the docs folder") is Severity.info


# --- Rubric mapping: gps ---


def test_gps_valid_is_high_never_critical() -> None:
    severity = _classify(FindingType.gps, "Latitude: 40.416775, Longitude: -3.703790")
    assert severity is Severity.high
    assert severity is not Severity.critical


def test_gps_with_altitude_is_high() -> None:
    snippet = "Latitude: 40.412875, Longitude: -3.721944, Altitude: 15"
    assert _classify(FindingType.gps, snippet) is Severity.high


def test_gps_malformed_or_out_of_range_is_info() -> None:
    cases = (
        "see the attached map",
        "Latitude: 95.0, Longitude: -3.7",
        "Latitude: 0.0, Longitude: 0.0",
    )
    for snippet in cases:
        assert _classify(FindingType.gps, snippet) is Severity.info, snippet


# --- Rubric mapping: email ---


def test_corporate_email_is_medium() -> None:
    assert _classify(FindingType.email, "jane.doe@target.corp") is Severity.medium


def test_generic_mailbox_is_low() -> None:
    for snippet in ("info@target.corp", "contact@target.corp", "support@target.corp"):
        assert _classify(FindingType.email, snippet) is Severity.low, snippet


def test_email_shape_mismatch_is_info() -> None:
    assert _classify(FindingType.email, "contact us for details") is Severity.info


# --- Rubric mapping: debug_comment ---


def test_debug_with_api_key_is_critical() -> None:
    assert (
        _classify(FindingType.debug_comment, "TODO: rotate api_key=abc123 before release")
        is Severity.critical
    )


def test_debug_secret_markers_are_critical() -> None:
    for snippet in (
        "password= hunter2",
        "password=hunter2",
        "TODO: token=ghp_abcdefghij",
        "TODO: rotate api_key=abc123 before release",
        "AKIAIOSFODNN7EXAMPLE",
        "-----BEGIN RSA PRIVATE KEY-----",
    ):
        assert _classify(FindingType.debug_comment, snippet) is Severity.critical, snippet


def test_debug_secret_word_without_a_value_is_medium() -> None:
    for snippet in (
        "FIXME: temporary secret stored here",
        "remove staging credentials",
        "API-KEY still hardcoded",
    ):
        assert _classify(FindingType.debug_comment, snippet) is Severity.medium, snippet


def test_debug_strong_keyword_is_medium() -> None:
    for snippet in (
        "TODO: fix this before Friday",
        "blocked by JIRA-8812",
        "NOT FOR PUBLIC RELEASE",
    ):
        assert _classify(FindingType.debug_comment, snippet) is Severity.medium, snippet


def test_debug_weak_isolated_is_info() -> None:
    for snippet in ("DRAFT", "CONFIDENTIAL", "INTERNAL DRAFT"):
        assert _classify(FindingType.debug_comment, snippet) is Severity.info, snippet


def test_debug_weak_with_context_is_low() -> None:
    assert (
        _classify(FindingType.debug_comment, "DRAFT version pending legal review") is Severity.low
    )


def test_debug_without_keywords_is_info() -> None:
    assert _classify(FindingType.debug_comment, "Quarterly report 2024") is Severity.info


# --- Rubric mapping: software_version ---


def test_software_version_is_low_without_invented_cve() -> None:
    assessment = classify_heuristically(
        _finding(FindingType.software_version, "Apache FOP 2.4", field_source="pdfinfo:Producer")
    )
    assert assessment.severity is Severity.low
    prose = f"{assessment.justification} {assessment.impact_analysis}"
    assert "CVE" not in prose  # never claim a vulnerability the evidence does not show


def test_software_without_version_is_info() -> None:
    assert _classify(FindingType.software_version, "Microsoft Word") is Severity.info


# --- Empty evidence, determinism, ceilings ---


def test_empty_snippet_is_info() -> None:
    for snippet in ("", "   "):
        assessment = classify_heuristically(_finding(FindingType.debug_comment, snippet))
        assert assessment.severity is Severity.info, repr(snippet)


def test_same_input_twice_same_severity() -> None:
    finding = _finding(FindingType.internal_path, "C:\\Users\\admin\\SecretProject\\")
    first = classify_heuristically(finding)
    second = HeuristicRiskClassifier().classify(finding)
    assert first == second  # frozen dataclass equality: full assessment is deterministic


def test_cap_severity_enforces_order() -> None:
    assert cap_severity(Severity.critical, Severity.high) is Severity.high
    assert cap_severity(Severity.low, Severity.high) is Severity.low
    assert cap_severity(Severity.medium, Severity.medium) is Severity.medium


def test_heuristic_ceilings_match_the_contract() -> None:
    assert ceiling_for(FindingType.gps) is Severity.high
    assert ceiling_for(FindingType.software_version) is Severity.low
    assert ceiling_for(FindingType.email) is Severity.medium
    assert ceiling_for(FindingType.internal_path) is Severity.high
    assert ceiling_for(FindingType.debug_comment) is Severity.critical


def test_rubric_prompt_text_covers_all_five_levels() -> None:
    for level in ("critical", "high", "medium", "low", "info"):
        assert level in RUBRIC_PROMPT_TEXT
    assert HEURISTIC_CEILINGS  # non-empty mapping consumed by TASK-05


# --- DoD: every classified finding gets exactly one severity of the set ---

_CASES = [
    (FindingType.gps, "Latitude: 40.416775, Longitude: -3.703790"),
    (FindingType.gps, "not a coordinate"),
    (FindingType.email, "jane.doe@target.corp"),
    (FindingType.email, "info@target.corp"),
    (FindingType.internal_path, "C:\\Users\\admin\\SecretProject\\"),
    (FindingType.internal_path, "/var/www/html/index.php"),
    (FindingType.software_version, "Apache FOP 2.4"),
    (FindingType.software_version, "Microsoft Word"),
    (FindingType.debug_comment, "TODO: token=ghp_abcdefghij"),
    (FindingType.debug_comment, "blocked by JIRA-8812"),
    (FindingType.debug_comment, "DRAFT"),
    (FindingType.debug_comment, ""),
]


def test_every_case_yields_exactly_one_valid_severity() -> None:
    for finding_type, snippet in _CASES:
        severity = _classify(finding_type, snippet)
        assert isinstance(severity, Severity)  # exactly one value of the closed set


def test_no_case_exceeds_its_heuristic_ceiling() -> None:
    for finding_type, snippet in _CASES:
        severity = _classify(finding_type, snippet)
        assert cap_severity(severity, ceiling_for(finding_type)) is severity


# --- Templates: prose written, no exploit payloads ---


def test_apply_assessment_writes_all_fields_and_keeps_agent_model_empty() -> None:
    finding = _finding(FindingType.email, "jane.doe@target.corp")
    assessment = classify_heuristically(finding)
    apply_assessment(finding, assessment)
    assert finding.severity is Severity.medium
    assert finding.severity_justification
    assert finding.impact_analysis
    assert finding.remediation_advice
    steps = json.loads(finding.reproduction_steps)
    assert isinstance(steps, list) and steps
    assert finding.agent_model_used is None  # TASK-05 fills this, never the heuristic
    assert finding.evidence_snippet == "jane.doe@target.corp"  # evidence untouched


def test_templates_render_without_leftover_placeholders() -> None:
    for finding_type, snippet in _CASES:
        if not snippet:
            continue
        assessment = classify_heuristically(_finding(finding_type, snippet))
        prose = (
            f"{assessment.justification} {assessment.impact_analysis} "
            f"{assessment.remediation_advice}"
        )
        assert "{" not in prose and "}" not in prose


def test_reproduction_steps_are_inspection_not_exploitation() -> None:
    banned = ("msfvenom", "meterpreter", "/etc/passwd", "exploit", "payload", "shellcode")
    for finding_type, snippet in _CASES:
        if not snippet:
            continue
        assessment = classify_heuristically(_finding(finding_type, snippet))
        steps = " ".join(assessment.reproduction_steps).lower()
        assert not any(word in steps for word in banned), (finding_type, snippet)
        assert "exiftool" in steps or "pdfinfo" in steps


def test_reproduction_tool_follows_content_type() -> None:
    finding = _finding(FindingType.software_version, "Apache FOP 2.4")
    pdf_asset = Asset(
        run_id="run-1",
        source_url="http://target.com/a.pdf",
        final_url="http://target.com/a.pdf",
        content_type="application/pdf",
        file_hash_sha256="ab" * 32,
        file_size_bytes=128,
        extraction_status=ExtractionStatus.ok,
    )
    steps = " ".join(classify_heuristically(finding, pdf_asset).reproduction_steps)
    assert "pdfinfo" in steps
    assert "http://target.com/a.pdf" in steps
    image_asset = pdf_asset.model_copy(update={"content_type": "image/jpeg"})
    steps = " ".join(classify_heuristically(finding, image_asset).reproduction_steps)
    assert "exiftool" in steps
    header_finding = _finding(
        FindingType.software_version, "nginx/1.18.0", field_source="http:server"
    )
    html_asset = pdf_asset.model_copy(update={"content_type": "text/html"})
    steps = " ".join(classify_heuristically(header_finding, html_asset).reproduction_steps)
    assert "curl" in steps


# --- Anchor (subtask 3.2.1) ---


def _item(
    value: str,
    key: str = "Comments",
    namespace: str = "pdfinfo",
    asset_id: str = "asset-1",
) -> RawMetadataItem:
    return RawMetadataItem(asset_id=asset_id, namespace=namespace, key=key, value=value)


def test_anchor_email_substring() -> None:
    finding = _finding(FindingType.email, "jane.doe@target.corp")
    assert evidence_is_anchored(finding, [_item("Contact jane.doe@target.corp for details")])


def test_anchor_truncated_snippet_with_marker() -> None:
    value = "Apache FOP 2.4 " + "x" * 200
    finding = _finding(FindingType.software_version, value[:147] + "...")
    assert evidence_is_anchored(finding, [_item(value, key="Producer")])


def test_anchor_unrelated_snippet_is_rejected() -> None:
    finding = _finding(FindingType.email, "ghost@target.corp")
    assert not evidence_is_anchored(finding, [_item("jane.doe@target.corp")])


def test_anchor_empty_snippet_is_rejected() -> None:
    assert not evidence_is_anchored(_finding(FindingType.email, ""), [_item("a@b.co")])


def test_anchor_gps_uses_shape_not_substring() -> None:
    # EXIF DMS rationals never contain the decimal snippet verbatim.
    finding = _finding(FindingType.gps, "Latitude: 40.412875, Longitude: -3.721944")
    items = [_item('["40/1", "24/1", "4635/100"]', key="GPSLatitude", namespace="exif")]
    assert evidence_is_anchored(finding, items)
    bad = _finding(FindingType.gps, "Latitude: north, Longitude: west")
    assert not evidence_is_anchored(bad, items)


def test_unanchored_assessment_is_forced_info() -> None:
    finding = _finding(FindingType.internal_path, r"C:\Users\ghost\secrets")
    assessment = unanchored_assessment(finding)
    assert assessment.severity is Severity.info
    assert "anchor" in assessment.justification


# --- ClassificationPipeline (persistence) ---


@pytest.fixture()
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/classify-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session_factory(engine: AsyncEngine) -> SessionFactory:
    return create_session_factory(engine)


async def _run(factory: SessionFactory) -> str:
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input=json.dumps(["http://target.com"]),
                allowed_scope=json.dumps(["target.com"]),
                scope_confirmed=True,
            )
        )
        return run.id


async def _asset(factory: SessionFactory, run_id: str) -> str:
    async with factory() as session:
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run_id,
                source_url="http://target.com/a.pdf",
                final_url="http://target.com/a.pdf",
                content_type="application/pdf",
                file_hash_sha256="cd" * 32,
                file_size_bytes=128,
                extraction_status=ExtractionStatus.ok,
            )
        )
        return asset.id


async def test_pipeline_classifies_pending_finding(session_factory: SessionFactory) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    async with session_factory() as session:
        await RawMetadataRepository(session).create_many(
            [_item("jane.doe@target.corp", key="Author", asset_id=asset_id)]
        )
        finding = _finding(FindingType.email, "jane.doe@target.corp", "pdfinfo:Author")
        finding.run_id = run_id
        finding.asset_id = asset_id
        finding.dedup_signature = dedup_signature(
            asset_id, FindingType.email, "jane.doe@target.corp"
        )
        await FindingRepository(session).create(finding)

    summary = await ClassificationPipeline(session_factory).execute(run_id)

    assert summary.findings_classified == 1
    assert summary.findings_already_classified == 0
    assert summary.by_severity == {"medium": 1}
    async with session_factory() as session:
        stored = await FindingRepository(session).list_by_run(run_id)
        assert stored[0].severity is Severity.medium
        assert stored[0].severity_justification
        assert stored[0].agent_model_used is None
        assert json.loads(stored[0].reproduction_steps)


async def test_pipeline_forces_info_on_unanchored_evidence(
    session_factory: SessionFactory,
) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    async with session_factory() as session:
        await RawMetadataRepository(session).create_many(
            [_item("nothing relevant here", asset_id=asset_id)]
        )
        finding = _finding(FindingType.internal_path, r"C:\Users\ghost\secrets")
        finding.run_id = run_id
        finding.asset_id = asset_id
        finding.dedup_signature = dedup_signature(
            asset_id, FindingType.internal_path, r"C:\Users\ghost\secrets"
        )
        await FindingRepository(session).create(finding)

    summary = await ClassificationPipeline(session_factory).execute(run_id)

    assert summary.by_severity == {"info": 1}
    async with session_factory() as session:
        stored = await FindingRepository(session).list_by_run(run_id)
        assert stored[0].severity is Severity.info
        assert "anchor" in stored[0].severity_justification


async def test_pipeline_skips_already_classified_findings(
    session_factory: SessionFactory,
) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    async with session_factory() as session:
        await RawMetadataRepository(session).create_many(
            [_item("jane.doe@target.corp", asset_id=asset_id)]
        )
        finding = _finding(FindingType.email, "jane.doe@target.corp")
        finding.run_id = run_id
        finding.asset_id = asset_id
        finding.dedup_signature = dedup_signature(
            asset_id, FindingType.email, "jane.doe@target.corp"
        )
        finding.severity = Severity.low
        finding.severity_justification = "pre-existing classification"
        await FindingRepository(session).create(finding)

    summary = await ClassificationPipeline(session_factory).execute(run_id)

    assert summary.findings_classified == 0
    assert summary.findings_already_classified == 1
    async with session_factory() as session:
        stored = await FindingRepository(session).list_by_run(run_id)
        assert stored[0].severity is Severity.low
        assert stored[0].severity_justification == "pre-existing classification"


async def test_pipeline_is_idempotent_on_rerun(session_factory: SessionFactory) -> None:
    run_id = await _run(session_factory)
    asset_id = await _asset(session_factory, run_id)
    async with session_factory() as session:
        await RawMetadataRepository(session).create_many(
            [_item("jane.doe@target.corp", asset_id=asset_id)]
        )
        finding = _finding(FindingType.email, "jane.doe@target.corp")
        finding.run_id = run_id
        finding.asset_id = asset_id
        finding.dedup_signature = dedup_signature(
            asset_id, FindingType.email, "jane.doe@target.corp"
        )
        await FindingRepository(session).create(finding)

    first = await ClassificationPipeline(session_factory).execute(run_id)
    second = await ClassificationPipeline(session_factory).execute(run_id)

    assert first.findings_classified == 1
    assert second.findings_classified == 0
    assert second.findings_already_classified == 1


async def test_pipeline_unknown_run_raises(session_factory: SessionFactory) -> None:
    with pytest.raises(MetaTracerError):
        await ClassificationPipeline(session_factory).execute("no-such-run")
