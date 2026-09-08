"""Report builder and exporter tests (TASK-04).

Covers the task's minimum set (severity ordering Critical -> Info with
unclassified last, valid exports for an empty run, JSON schema round-trip,
byte-exact evidence, placeholder prose when the agent never ran) plus the DoD
extras: tie-breaking, severity counts including unclassified, reproduction
steps materialized as a list, compliance notice in both formats and file
naming (slug, timestamp, output_dir override).

The database is a real SQLite file in tmp_path — never mocked.
"""

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer import __version__
from metatracer.core.exceptions import MetaTracerError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    Run,
    Severity,
)
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository
from metatracer.reports import (
    COMPLIANCE_NOTICE,
    PROSE_PLACEHOLDER,
    HtmlReportExporter,
    JsonReportExporter,
    MarkdownReportExporter,
    ReportBuilder,
    ReportData,
)
from metatracer.reports.schemas import ReportDocument

SessionFactory = async_sessionmaker[AsyncSession]

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_DEFAULT_SNIPPET = "C:\\Users\\mrodriguez\\Workspace\\FinancialApp\\export_v2.pdf"
_DEFAULT_STEPS = '["Fetch the public asset and save it locally.", "Run `pdfinfo` on the file."]'


@pytest.fixture()
async def session_factory(tmp_path) -> AsyncIterator[SessionFactory]:
    engine: AsyncEngine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/metatracer-test.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


def _run(**overrides) -> Run:
    values = {
        "target_input": '["http://target.com"]',
        "allowed_scope": '["target.com"]',
        "scope_confirmed": True,
    }
    return Run(**(values | overrides))


def _asset(
    run_id: str,
    url: str,
    *,
    discovered_at: datetime = _EPOCH,
    file_hash: str = "ab" * 32,
    content_type: str = "application/pdf",
) -> Asset:
    return Asset(
        run_id=run_id,
        source_url=url,
        final_url=url,
        content_type=content_type,
        file_hash_sha256=file_hash,
        file_size_bytes=128,
        extraction_status=ExtractionStatus.ok,
        discovered_at=discovered_at,
    )


def _finding(
    run_id: str,
    asset_id: str,
    signature: str,
    *,
    finding_type: FindingType = FindingType.internal_path,
    field_source: str = "XMP:CreatorTool",
    snippet: str = _DEFAULT_SNIPPET,
    severity: Severity | None = Severity.high,
    confidence: Confidence = Confidence.high,
    with_prose: bool = True,
    reproduction_steps: str | None = _DEFAULT_STEPS,
) -> Finding:
    return Finding(
        run_id=run_id,
        asset_id=asset_id,
        finding_type=finding_type,
        field_source=field_source,
        evidence_snippet=snippet,
        dedup_signature=signature,
        detector_method=DetectorMethod.rule,
        confidence=confidence,
        severity=severity,
        severity_justification="Template justification." if with_prose else None,
        impact_analysis="Template impact." if with_prose else None,
        remediation_advice="1. Strip metadata." if with_prose else None,
        reproduction_steps=reproduction_steps if with_prose else None,
    )


async def _seed(
    factory: SessionFactory,
    run: Run,
    assets: list[Asset],
    findings: list[Finding],
) -> None:
    async with factory() as session:
        await RunRepository(session).create(run)
    async with factory() as session:
        for asset in assets:
            await AssetRepository(session).create(asset)
    if findings:
        async with factory() as session:
            await FindingRepository(session).create_many(findings)


async def _build(factory: SessionFactory, run_id: str) -> ReportData:
    return await ReportBuilder(factory).build(run_id)


# --- Ordering (subtask 4.1.1) ---


async def test_findings_sorted_critical_to_info_unclassified_last(
    session_factory: SessionFactory,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    specs = [
        ("f-info", Severity.info),
        ("f-none", None),
        ("f-crit", Severity.critical),
        ("f-med", Severity.medium),
        ("f-high", Severity.high),
        ("f-low", Severity.low),
    ]
    findings = [
        _finding(run.id, asset.id, f"sig-{name}", severity=severity) for name, severity in specs
    ]
    await _seed(session_factory, run, [asset], findings)
    ids = {name: finding.id for (name, _), finding in zip(specs, findings, strict=True)}

    data = await _build(session_factory, run.id)

    assert [f.id for f in data.findings] == [
        ids["f-crit"],
        ids["f-high"],
        ids["f-med"],
        ids["f-low"],
        ids["f-info"],
        ids["f-none"],
    ]


async def test_ties_break_on_confidence_then_discovered_at(
    session_factory: SessionFactory,
) -> None:
    run = _run()
    older = _asset(run.id, "http://target.com/old.pdf", discovered_at=_EPOCH, file_hash="bb" * 32)
    newer = _asset(
        run.id,
        "http://target.com/new.pdf",
        discovered_at=_EPOCH + timedelta(hours=1),
        file_hash="cc" * 32,
    )
    f_low_conf = _finding(run.id, older.id, "sig-lc", confidence=Confidence.low)
    f_high_conf = _finding(run.id, older.id, "sig-hc", confidence=Confidence.high)
    f_older = _finding(run.id, older.id, "sig-older", confidence=Confidence.medium)
    f_newer = _finding(run.id, newer.id, "sig-newer", confidence=Confidence.medium)
    # Seeded out of order on purpose; all four share severity=high.
    await _seed(session_factory, run, [older, newer], [f_newer, f_older, f_low_conf, f_high_conf])

    data = await _build(session_factory, run.id)

    assert [f.id for f in data.findings] == [
        f_high_conf.id,
        f_older.id,
        f_newer.id,
        f_low_conf.id,
    ]


# --- Empty run (subtask 4.1.3) ---


async def test_empty_run_produces_valid_markdown_and_json(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    assets = [
        _asset(run.id, "http://target.com/a.pdf", file_hash="dd" * 32),
        _asset(run.id, "http://target.com/b.pdf", file_hash="ee" * 32),
    ]
    await _seed(session_factory, run, assets, [])

    data = await _build(session_factory, run.id)
    md_path = MarkdownReportExporter(tmp_path).export(data)
    json_path = JsonReportExporter(tmp_path).export(data)

    md_text = md_path.read_text(encoding="utf-8")
    assert md_text.strip()  # never an empty file
    assert "No sensitive metadata was identified in the 2 document(s) analyzed." in md_text
    assert (
        "Total assets: 2 | Critical: 0 | High: 0 | Medium: 0 | Low: 0 | "
        "Info: 0 | Unclassified: 0"
    ) in md_text

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    document = ReportDocument.model_validate(payload)
    assert document.summary.total_assets_scanned == 2
    assert document.summary.total_findings == 0
    assert payload["findings"] == []
    assert payload["summary"]["severity_counts"] == {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
        "unclassified": 0,
    }


# --- JSON schema and enums (subtask 4.3.2) ---


async def test_json_export_validates_and_uses_lowercase_enums(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    findings = [
        _finding(run.id, asset.id, "sig-crit", severity=Severity.critical),
        _finding(
            run.id,
            asset.id,
            "sig-none",
            severity=None,
            confidence=Confidence.low,
            with_prose=False,
        ),
    ]
    await _seed(session_factory, run, [asset], findings)

    data = await _build(session_factory, run.id)
    json_path = JsonReportExporter(tmp_path).export(data)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    # Round-trip: the written payload validates against the Pydantic schema.
    document = ReportDocument.model_validate(payload)
    assert payload["metatracer_version"] == __version__
    assert payload["run_id"] == run.id
    assert payload["target"] == "http://target.com"
    assert payload["scope"] == ["target.com"]
    assert payload["reasoning_depth"] == "standard"
    assert payload["generated_at"].endswith("Z")

    first, second = payload["findings"]
    assert first["type"] == "internal_path"
    assert first["severity"] == "critical"  # lowercase enum
    assert first["confidence"] == "high"
    assert second["severity"] is None  # unclassified -> null, never "info"
    assert document.findings[0].severity is Severity.critical
    assert document.findings[1].severity is None


async def test_severity_counts_include_unclassified(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    findings = [
        _finding(run.id, asset.id, "sig-c1", severity=Severity.critical),
        _finding(run.id, asset.id, "sig-c2", severity=Severity.critical),
        _finding(run.id, asset.id, "sig-i", severity=Severity.info),
        _finding(run.id, asset.id, "sig-n", severity=None),
    ]
    await _seed(session_factory, run, [asset], findings)

    data = await _build(session_factory, run.id)

    counts = data.severity_counts
    assert (counts.critical, counts.info, counts.unclassified) == (2, 1, 1)
    assert data.executive_summary_line == (
        "Total assets: 1 | Critical: 2 | High: 0 | Medium: 0 | Low: 0 | "
        "Info: 1 | Unclassified: 1"
    )
    payload = json.loads(JsonReportExporter(tmp_path).export(data).read_text(encoding="utf-8"))
    assert payload["summary"]["severity_counts"] == {
        "critical": 2,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 1,
        "unclassified": 1,
    }
    assert payload["summary"]["total_findings"] == 4


# --- Evidence fidelity (subtask 4.2, item 5) ---


async def test_evidence_matches_persisted_snippet_byte_for_byte(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    snippet = "  C:\\Users\\jdoe\\secret project\\v1.docx\nsecond line  "
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    finding = _finding(run.id, asset.id, "sig-ev", snippet=snippet)
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)
    trimmed = snippet.strip()  # only whitespace trim is allowed
    assert data.findings[0].evidence == trimmed

    md_text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")
    assert f"```text\n{trimmed}\n  ```" in md_text

    payload = json.loads(JsonReportExporter(tmp_path).export(data).read_text(encoding="utf-8"))
    assert payload["findings"][0]["evidence"] == trimmed


# --- Heuristic-only findings (DoD: TASK-05 not executed) ---


async def test_finding_without_agent_prose_uses_placeholder(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    finding = _finding(run.id, asset.id, "sig-bare", severity=Severity.low, with_prose=False)
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)
    entry = data.findings[0]
    assert entry.impact == PROSE_PLACEHOLDER
    assert entry.explanation == PROSE_PLACEHOLDER
    assert entry.remediation == PROSE_PLACEHOLDER
    assert entry.reproduction_steps == (PROSE_PLACEHOLDER,)

    md_text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")
    assert PROSE_PLACEHOLDER in md_text

    payload = json.loads(JsonReportExporter(tmp_path).export(data).read_text(encoding="utf-8"))
    document = ReportDocument.model_validate(payload)  # placeholders still validate
    assert document.findings[0].impact == PROSE_PLACEHOLDER
    assert document.findings[0].reproduction_steps == [PROSE_PLACEHOLDER]


async def test_legacy_newline_reproduction_steps_materialize_as_list(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    findings = [
        _finding(run.id, asset.id, "sig-json"),  # JSON array string (TASK-03)
        _finding(
            run.id,
            asset.id,
            "sig-legacy",
            reproduction_steps="Step one\nStep two",
        ),
        _finding(
            run.id,
            asset.id,
            "sig-corrupt",
            reproduction_steps='["broken"',
        ),
    ]
    await _seed(session_factory, run, [asset], findings)

    data = await _build(session_factory, run.id)
    payload = json.loads(JsonReportExporter(tmp_path).export(data).read_text(encoding="utf-8"))
    steps_by_id = {item["id"]: item["reproduction_steps"] for item in payload["findings"]}

    assert steps_by_id[findings[0].id] == [
        "Fetch the public asset and save it locally.",
        "Run `pdfinfo` on the file.",
    ]
    assert steps_by_id[findings[1].id] == ["Step one", "Step two"]
    assert steps_by_id[findings[2].id] == [PROSE_PLACEHOLDER]


# --- Markdown card (subtasks 4.2 / 4.3.1) ---


async def test_markdown_card_contains_all_ficha_fields(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    finding = _finding(run.id, asset.id, "sig-1", severity=Severity.high)
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)
    text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")

    assert "# MetaTracer Security Report" in text
    assert "### [High] Internal Path Disclosure in Public PDF" in text
    assert "- **Severity:** High" in text
    assert "- **Affected asset:** `http://target.com/a.pdf`" in text
    assert "content-type: `application/pdf`" in text
    assert "- **Finding type:** Internal Path" in text
    assert "- **Metadata field:** `XMP:CreatorTool`" in text
    assert f"```text\n{_DEFAULT_SNIPPET}\n" in text
    assert "- **Impact:** Template impact." in text
    assert "- **Explanation:** Template justification." in text
    assert "1. Fetch the public asset and save it locally." in text
    assert "1. Strip metadata." in text


async def test_unclassified_finding_renders_as_unclassified(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    finding = _finding(run.id, asset.id, "sig-u", severity=None)
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)
    text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")

    assert "### [Unclassified] Internal Path Disclosure in Public PDF" in text
    assert "- **Severity:** Unclassified" in text


async def test_title_uses_finding_type_and_asset_context(
    session_factory: SessionFactory,
) -> None:
    run = _run()
    asset = _asset(
        run.id,
        "http://target.com/photo.jpg",
        content_type="image/jpeg",
    )
    finding = _finding(
        run.id,
        asset.id,
        "sig-gps",
        finding_type=FindingType.gps,
        field_source="EXIF:GPSInfo",
        snippet="Latitude: 40.416775, Longitude: -3.703790",
    )
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)

    assert data.findings[0].title == "GPS Coordinate Disclosure in Public Image"
    assert data.findings[0].type_label == "GPS / Coordinates"


# --- Agent prose reaches the report (4.1.2 hygiene paragraph, 4.2 title) ---


async def test_agent_executive_summary_replaces_heuristic_hygiene_note(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run(executive_summary="  Agent paragraph: two paths leak a developer username.  ")
    asset = _asset(run.id, "http://target.com/a.pdf")
    finding = _finding(run.id, asset.id, "sig-agent")
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)
    md_text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")

    assert data.hygiene_note == "Agent paragraph: two paths leak a developer username."
    assert data.hygiene_note in md_text
    assert "consistent with residual authoring-tool" not in md_text  # heuristic text gone


async def test_empty_run_keeps_fixed_sentence_even_with_agent_summary(
    session_factory: SessionFactory,
) -> None:
    run = _run(executive_summary="Agent says nothing required analysis.")
    await _seed(session_factory, run, [_asset(run.id, "http://target.com/a.pdf")], [])

    data = await _build(session_factory, run.id)

    assert data.hygiene_note == (
        "No sensitive metadata was identified in the 1 document(s) analyzed."
    )


async def test_agent_title_replaces_template_title(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    titled = _finding(run.id, asset.id, "sig-titled")
    titled.title = "Developer Workstation Path in\nPublished PDF"
    blank = _finding(run.id, asset.id, "sig-blank", snippet="C:\\Users\\other\\x.pdf")
    blank.title = "   "
    await _seed(session_factory, run, [asset], [titled, blank])

    data = await _build(session_factory, run.id)
    md_text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")
    titles = {entry.id: entry.title for entry in data.findings}

    assert titles[titled.id] == "Developer Workstation Path in Published PDF"  # one line
    assert titles[blank.id] == "Internal Path Disclosure in Public PDF"  # template fallback
    assert "### [High] Developer Workstation Path in Published PDF" in md_text


# --- Compliance notice (DoD) ---


async def test_compliance_notice_present_in_both_formats(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    await _seed(session_factory, run, [], [])

    data = await _build(session_factory, run.id)
    md_text = MarkdownReportExporter(tmp_path).export(data).read_text(encoding="utf-8")
    payload = json.loads(JsonReportExporter(tmp_path).export(data).read_text(encoding="utf-8"))

    assert "## Scope & Compliance Notice" in md_text
    assert COMPLIANCE_NOTICE in md_text
    assert payload["compliance_notice"] == COMPLIANCE_NOTICE


# --- File naming (subtask 4.3) ---


async def test_filename_slug_timestamp_and_output_dir_override(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run(
        target_input='["HTTPS://Sub.Example.COM:8443/docs?x=1"]',
        allowed_scope='["sub.example.com"]',
    )
    await _seed(session_factory, run, [], [])

    data = await _build(session_factory, run.id)
    out_dir = tmp_path / "custom-reports"
    md_path = MarkdownReportExporter(out_dir).export(data)
    json_path = JsonReportExporter(out_dir).export(data)

    stem = re.escape(f"metatracer-sub.example.com-{run.id.split('-', 1)[0]}")
    assert re.fullmatch(rf"{stem}-\d{{8}}T\d{{6}}Z\.md", md_path.name)
    assert md_path.parent == out_dir
    assert json_path.parent == out_dir
    # A Markdown/JSON pair from one build shares the timestamped stem.
    assert json_path.stem == md_path.stem


async def test_default_output_dir_is_reports(
    session_factory: SessionFactory,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run = _run()
    await _seed(session_factory, run, [], [])

    data = await _build(session_factory, run.id)
    path = MarkdownReportExporter().export(data)

    assert path.parent == Path("reports")
    assert (tmp_path / "reports" / path.name).exists()


# --- Error handling ---


async def test_missing_run_raises_metatracer_error(session_factory: SessionFactory) -> None:
    with pytest.raises(MetaTracerError):
        await ReportBuilder(session_factory).build("00000000-0000-0000-0000-000000000000")


async def test_html_export_escapes_evidence_and_includes_compliance(
    session_factory: SessionFactory,
    tmp_path,
) -> None:
    run = _run()
    asset = _asset(run.id, "http://target.com/a.pdf")
    snippet = '<script>alert("xss")</script> C:\\Users\\admin\\file.pdf'
    finding = _finding(run.id, asset.id, "sig-html", snippet=snippet)
    await _seed(session_factory, run, [asset], [finding])

    data = await _build(session_factory, run.id)
    path = HtmlReportExporter(tmp_path).export(data)
    text = path.read_text(encoding="utf-8")
    assert path.suffix == ".html"
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert COMPLIANCE_NOTICE in text
    assert "MetaTracer Security Report" in text
    assert data.findings[0].evidence in snippet or "Users" in text
