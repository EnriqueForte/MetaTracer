"""End-to-end pipeline tests (TASK-07, subtask 7.2.3) against a REAL loopback origin.

Unlike the rest of the suite (faked DNS + in-memory HTTP transport), these
tests run the full pipeline over real TCP against :class:`tests.fixtures.mock_origin.MockOrigin`
(uvicorn on 127.0.0.1, ephemeral port) serving the synthetic fixtures.

Loopback safety contract (inviolable rule 7): the scans below construct
``Settings(allow_loopback=True)`` — the in-process equivalent of
``METATRACER_ALLOW_LOOPBACK=true`` — which exists ONLY for the test suite and
is never enabled by default, by the Docker image or by the Compose file. The
last test proves the default (flag off) still rejects this very server before
any socket is opened: the origin must record ZERO requests.

No LLM is configured, so the agent phase exercises its documented heuristic
fallback (TASK-05, subtask 5.4.2) — the run never fails for lack of a model.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from metatracer.core.config import Settings
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    ExtractionStatus,
    FindingType,
    RunStatus,
    Severity,
    SkipReason,
)
from metatracer.db.repositories import (
    AgentLogRepository,
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)
from metatracer.services.orchestrator import ScanOrchestratorService, ScanRequest, ScanResult
from tests.fixtures.generate_test_fixtures import CLEAN_FILENAMES, FIXTURE_SPECS
from tests.fixtures.mock_origin import LEAKY_PATH, REDIRECT_PATH, SECRET_PATH, MockOrigin

pytestmark = pytest.mark.e2e

# Every dirty fixture contributes exactly its own type; the clean ones, none.
EXPECTED_TYPES = {
    FindingType.gps,
    FindingType.email,
    FindingType.internal_path,
    FindingType.software_version,
    FindingType.debug_comment,
}
# Rubric-anchored severities (TASK-03) the heuristic must assign to the fixtures.
# debug_comment has TWO fixtures: the strong JIRA leftover (medium) and the
# bare "INTERNAL" weak keyword (info: isolated weak evidence per the rubric).
EXPECTED_SEVERITIES = {
    FindingType.gps: {Severity.high},  # precise coordinates; critical needs a person/home text
    FindingType.internal_path: {Severity.high},  # C:\Users\<username>\...
    FindingType.email: {Severity.medium},  # personal corporate mailbox
    FindingType.debug_comment: {Severity.medium, Severity.info},
    FindingType.software_version: {Severity.low},  # name+version ceiling
}
# fixtures + the off-scope redirect (skipped) + the crawled index HTML page (v1.2)
EXPECTED_ASSETS = len(FIXTURE_SPECS) + 2


@pytest.fixture()
async def origin() -> AsyncIterator[MockOrigin]:
    """One mock origin per test: fresh request counters and ephemeral port."""
    mock = MockOrigin()
    mock.start()
    try:
        yield mock
    finally:
        mock.stop()


def _settings(tmp_path: Path, *, allow_loopback: bool) -> Settings:
    """Hermetic settings: tmp database, no .env, no LLM (heuristic fallback)."""
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/e2e.db",
        rate_limit_rps=1000.0,
        allow_loopback=allow_loopback,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


async def _run_scan(
    settings: Settings, targets: list[str], output_dir: Path
) -> tuple[ScanResult, dict[str, object]]:
    """Run the real pipeline and read back every persisted layer of the run."""
    engine = create_db_engine(settings.database_url)
    await init_db(engine)
    try:
        session_factory = create_session_factory(engine)
        orchestrator = ScanOrchestratorService(session_factory, settings)
        result = await orchestrator.scan(
            ScanRequest(targets=targets, scope_domains=["127.0.0.1"], scope_confirmed=True),
            output_dir=output_dir,
        )
        async with session_factory() as session:
            state: dict[str, object] = {
                "run": await RunRepository(session).get(result.run_id),
                "assets": await AssetRepository(session).list_by_run(result.run_id),
                "findings": await FindingRepository(session).list_by_run(result.run_id),
                "raw_items": await RawMetadataRepository(session).list_by_run(result.run_id),
                "agent_logs": await AgentLogRepository(session).list_by_run(result.run_id),
            }
        return result, state
    finally:
        await engine.dispose()


async def test_full_pipeline_five_types_reports_and_persistence(
    origin: MockOrigin, tmp_path: Path
) -> None:
    """PRD success criteria: 5 finding types, submittable report, full persistence."""
    result, state = await _run_scan(
        _settings(tmp_path, allow_loopback=True), [origin.index_url], tmp_path / "reports"
    )

    # The run completed and every layer of the architecture was traversed.
    assert result.status is RunStatus.completed
    run = state["run"]
    assert run.status is RunStatus.completed
    assert run.completed_at is not None
    assert result.total_assets == EXPECTED_ASSETS
    assets = state["assets"]
    assert len(assets) == EXPECTED_ASSETS

    # 1) At least 4 of 5 finding types (the PRD bar); the fixtures deliver all 5.
    findings = state["findings"]
    found_types = {finding.finding_type for finding in findings}
    assert found_types == EXPECTED_TYPES
    assert len(found_types) >= 4

    # The heuristic classified everything and the agent phase fell back cleanly.
    # Several findings may share a type (two debug_comment fixtures), so the
    # maps collect a SET of severities / a LIST of snippets per type.
    severities: dict[str, set[str]] = {}
    snippets: dict[str, list[str]] = {}
    for finding in findings:
        severities.setdefault(finding.finding_type, set()).add(finding.severity)
        snippets.setdefault(finding.finding_type, []).append(finding.evidence_snippet)
    assert severities == EXPECTED_SEVERITIES
    assert all(finding.agent_model_used == "heuristic-fallback" for finding in findings)
    assert len(state["agent_logs"]) >= len(findings)
    assert state["raw_items"]  # extracted metadata rows exist

    # Evidence is the planted one (byte-for-byte snippets, never invented).
    assert snippets[FindingType.gps] == ["Latitude: 40.416800, Longitude: -3.703800"]
    assert snippets[FindingType.email] == ["security.lead@acme-corp.internal"]
    assert snippets[FindingType.internal_path] == [
        r"C:\Users\dev_admin\Projects\ConfidentialApp\build.pdf"
    ]
    assert snippets[FindingType.software_version] == ["Apache FOP Version 2.4"]
    assert any("JIRA-4412" in snippet for snippet in snippets[FindingType.debug_comment])
    # The bare weak-keyword fixture fires too (short field, length gate passes).
    assert "INTERNAL" in snippets[FindingType.debug_comment]

    # 2) Submittable reports: Markdown with evidence/impact/remediation + JSON.
    md_path = result.report_paths["md"]
    json_path = result.report_paths["json"]
    assert md_path.exists() and json_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    assert "# MetaTracer Security Report" in markdown
    for section in ("- **Evidence:**", "- **Impact:**", "- **Remediation:**"):
        assert section in markdown
    for snippet_list in snippets.values():
        for snippet in snippet_list:
            assert snippet in markdown
    # Ordered critical -> info: high cards precede medium, medium precede low.
    assert markdown.index("### [High]") < markdown.index("### [Medium]")
    assert markdown.index("### [Medium]") < markdown.index("### [Low]")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == result.run_id
    assert len(payload["findings"]) == len(findings)

    # 3) Redirect off-scope: skipped before the body, target never connected.
    redirect_asset = next(a for a in assets if a.source_url.endswith(REDIRECT_PATH))
    assert redirect_asset.extraction_status is ExtractionStatus.skipped
    assert redirect_asset.skip_reason is SkipReason.out_of_scope
    assert origin.hits(SECRET_PATH) == 0


async def test_clean_documents_yield_zero_findings(origin: MockOrigin, tmp_path: Path) -> None:
    """The sanitized fixtures scan clean: zero findings is a valid result.

    Covers the clean pair AND the long-caption regression fixture (Phase-0 NASA
    false positive: prose with a weak keyword must not fire the debug detector).
    """
    result, state = await _run_scan(
        _settings(tmp_path, allow_loopback=True), [origin.clean_url], tmp_path / "reports"
    )
    assert result.status is RunStatus.completed
    assert result.total_findings == 0
    assert result.total_assets == len(CLEAN_FILENAMES) + 1  # + crawled clean.html page
    assert all(
        asset.extraction_status is ExtractionStatus.ok for asset in state["assets"]
    )
    assert state["findings"] == []
    markdown = result.report_paths["md"].read_text(encoding="utf-8")
    assert "No sensitive metadata was identified" in markdown


async def test_loopback_origin_is_rejected_without_the_test_flag(
    origin: MockOrigin, tmp_path: Path
) -> None:
    """Flag OFF (the product default): the mock local is refused before any socket.

    Both entry points are exercised — the page crawl and a direct document
    target — and the origin must record ZERO requests: the guard raises before
    a connection is ever opened.
    """
    result, state = await _run_scan(
        _settings(tmp_path, allow_loopback=False),
        [origin.index_url, origin.file_url("gps-photo.jpg")],
        tmp_path / "reports",
    )
    assert result.status is RunStatus.completed  # a blocked target never aborts the run
    assert result.total_findings == 0
    # The page could not be crawled; the direct file became a failed asset.
    assert result.total_assets == 1
    asset = state["assets"][0]
    assert asset.extraction_status is ExtractionStatus.failed
    assert "refusing connection" in (asset.error_message or "")
    assert origin.total_hits == 0


async def test_html_headers_and_js_are_first_class_sources(
    origin: MockOrigin, tmp_path: Path
) -> None:
    """TASK-09: a leaky HTML page + JS file produce findings without PDF/EXIF."""
    result, state = await _run_scan(
        _settings(tmp_path, allow_loopback=True), [origin.leaky_url], tmp_path / "reports"
    )
    assert result.status is RunStatus.completed
    assets = state["assets"]
    urls = {asset.source_url for asset in assets}
    assert any(url.endswith(LEAKY_PATH) for url in urls)
    assert any(url.endswith("/static/app.js") for url in urls)
    assert all(asset.extraction_status is ExtractionStatus.ok for asset in assets)

    findings = state["findings"]
    found_types = {finding.finding_type for finding in findings}
    assert FindingType.software_version in found_types
    assert FindingType.email in found_types
    assert FindingType.debug_comment in found_types
    assert FindingType.internal_path in found_types

    snippets = {finding.evidence_snippet for finding in findings}
    sources = {finding.field_source for finding in findings}
    assert "PHP/8.2.0" in snippets
    assert "http:x-powered-by" in sources
    assert "WordPress 6.4.2" in snippets
    assert "recon@acme-corp.internal" in snippets
    assert any("TODO:" in snippet for snippet in snippets)
    assert any(r"C:\Users\web_admin\app.js" in snippet for snippet in snippets)
    raw_values = " ".join(item.value for item in state["raw_items"])
    assert "session=" not in raw_values
