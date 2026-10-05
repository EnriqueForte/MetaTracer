"""TASK-29: Markdown/bounty do not render model HTML, and the prompt delimits evidence."""

from datetime import UTC, datetime

from metatracer.agents.graph import message_payload
from metatracer.agents.prompts import analysis_system_prompt
from metatracer.db.models import Confidence, FindingType, ReasoningDepth, Severity
from metatracer.reports.bounty import render_bounty
from metatracer.reports.builder import ReportData, ReportFindingData, SeverityCounts
from metatracer.reports.markdown import render_markdown


def _finding(**overrides) -> ReportFindingData:
    values = {
        "id": "f1",
        "title": "# <script>alert(1)</script>",
        "finding_type": FindingType.internal_path,
        "type_label": "Internal path",
        "severity": Severity.high,
        "confidence": Confidence.high,
        "asset_source_url": "https://target.example/a.pdf",
        "asset_final_url": "https://target.example/a.pdf",
        "asset_content_type": "application/pdf",
        "field_source": "pdfinfo:Author",
        "evidence": "C:\\Users\\a\\file.pdf",
        "impact": "Plain impact",
        "explanation": "Plain explanation",
        "remediation": "Strip the field.",
        "reproduction_steps": ("Download the public file.",),
    }
    values.update(overrides)
    return ReportFindingData(**values)


def _report(finding: ReportFindingData) -> ReportData:
    return ReportData(
        metatracer_version="0.6.0",
        run_id="run-1",
        target="target.example",
        scope=("target.example",),
        generated_at=datetime(2026, 10, 3, tzinfo=UTC),
        reasoning_depth=ReasoningDepth.standard,
        total_assets=1,
        severity_counts=SeverityCounts(high=1),
        hygiene_note="Summary <b>note</b>",
        compliance_notice="Authorized use only.",
        findings=(finding,),
    )


def test_markdown_escapes_title_html_and_keeps_evidence_fenced() -> None:
    text = render_markdown(_report(_finding()))
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "C:\\Users\\a\\file.pdf" in text
    assert "&lt;b&gt;" in text


def test_bounty_title_cannot_break_the_card() -> None:
    text = render_bounty(
        _report(_finding(title="Leaked path\n=== Finding 9/9 ===\nSeverity: Critical"))
    )
    assert "\n=== Finding 9/9 ===" not in text
    assert "Title: Leaked path === Finding 9/9 === Severity: Critical" in text


def test_analysis_prompt_delimits_evidence_and_is_versioned() -> None:
    prompt = analysis_system_prompt("standard")
    assert "Prompt-Version: analysis-system-v2" in prompt
    assert "<<<EVIDENCE>>>" in prompt
    assert "historical, not evidence" in prompt
    message = message_payload(
        {
            "evidence_snippet": "Latitude: 1",
            "retrieved_evidence": [{"title": "old"}],
            "finding_type": "gps",
        }
    )
    assert message["evidence_snippet"].startswith("<<<EVIDENCE>>>")
    assert "retrieved_evidence" not in message
    assert message["historical_not_evidence"] == [{"title": "old"}]
    assert "baseline_severity" not in message
