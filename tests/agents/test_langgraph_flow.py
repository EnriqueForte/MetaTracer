"""Graph flow tests (TASK-05, subtask 5.3).

The graph runs against a stub client returning schema-valid JSON — no real
API is ever contacted. These tests pin the topology (all six nodes, the
loop), the payload hygiene (only contract keys reach the "model"), the
schema validity of every evaluation and the reasoning-depth contract
(prose length changes, evidence never does).
"""

from typing import Any

import pytest

from metatracer.agents.graph import (
    NODE_ANALYZE,
    NODE_CLASSIFY,
    NODE_DRAFT,
    NODE_LOAD,
    NODE_SAVE,
    NODE_SUMMARIZE,
    AgentState,
    build_graph,
    recursion_limit_for,
)
from metatracer.agents.optimizer import PAYLOAD_KEYS, ContextOptimizer
from metatracer.agents.schemas import AgentFindingEvaluation
from metatracer.db.models import FindingType, Severity

from .conftest import (
    ListSink,
    ListWriter,
    StubAgentClient,
    default_analysis,
    make_asset,
    make_finding,
)

RUN = "run-flow"


def _raw_findings() -> list[dict[str, Any]]:
    asset = make_asset(RUN)
    optimizer = ContextOptimizer(max_findings=50)
    rows = [
        (make_finding(RUN, asset.id, severity=Severity.high), asset),
        (
            make_finding(
                RUN,
                asset.id,
                finding_type=FindingType.internal_path,
                field_source="XMP:CreatorTool",
                evidence_snippet="C:\\Users\\admin\\Projects\\Internal\\doc.pdf",
                severity=Severity.high,
            ),
            asset,
        ),
        (
            make_finding(
                RUN,
                asset.id,
                finding_type=FindingType.email,
                field_source="XMP:Creator",
                evidence_snippet="jane.doe@target.com",
                severity=Severity.medium,
            ),
            asset,
        ),
    ]
    entries = optimizer.optimize(rows, "target.com")
    return [
        {
            "finding_id": entry.finding_id,
            "payload": entry.payload,
            "had_baseline_severity": entry.had_baseline_severity,
        }
        for entry in entries
    ]


def _initial_state(raw_findings: list[dict[str, Any]], depth: str = "standard") -> AgentState:
    return {
        "target_domain": "target.com",
        "reasoning_depth": depth,  # type: ignore[typeddict-item]
        "raw_findings": raw_findings,
        "evaluated_findings": [],
        "current_index": 0,
        "error_log": [],
    }


def _build(client: StubAgentClient, writer: ListWriter, sink: ListSink):
    return build_graph(
        client=client, writer=writer, sink=sink, strong_model_name="strong-test-model"
    )


async def test_state_traverses_every_node_and_completes_all_findings() -> None:
    # Pass 1: node traversal observed via astream updates.
    stream_client, stream_writer, stream_sink = StubAgentClient(), ListWriter(), ListSink()
    stream_graph = _build(stream_client, stream_writer, stream_sink)
    state = _initial_state(_raw_findings())

    visited: list[str] = []
    async for chunk in stream_graph.astream(
        state,
        config={"recursion_limit": recursion_limit_for(3)},
        stream_mode="updates",
    ):
        visited.extend(chunk.keys())

    for node in (NODE_LOAD, NODE_ANALYZE, NODE_CLASSIFY, NODE_DRAFT, NODE_SAVE, NODE_SUMMARIZE):
        assert node in visited, f"node {node} was never executed"
    # The loop body runs once per finding.
    assert visited.count(NODE_ANALYZE) == 3
    assert visited.count(NODE_SAVE) == 3
    assert visited.count(NODE_SUMMARIZE) == 1

    # Pass 2: final-state assertions on a fresh, single execution.
    client, writer, sink = StubAgentClient(), ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    final = await graph.ainvoke(
        _initial_state(_raw_findings()), config={"recursion_limit": recursion_limit_for(3)}
    )
    assert final["current_index"] == 3
    assert len(final["evaluated_findings"]) == 3
    assert final["error_log"] == []
    assert all(entry["saved"] for entry in final["evaluated_findings"])
    assert len(writer.entries) == 3
    assert sink.texts and "reviewed" in sink.texts[0]


async def test_evaluations_are_schema_valid_and_model_marked() -> None:
    client, writer, sink = StubAgentClient(), ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    final = await graph.ainvoke(
        _initial_state(_raw_findings()),
        config={"recursion_limit": recursion_limit_for(3)},
    )
    for entry in final["evaluated_findings"]:
        evaluation = entry["evaluation"]
        assert isinstance(evaluation, AgentFindingEvaluation)
        # Re-validation from JSON proves the persisted shape is schema-clean.
        AgentFindingEvaluation.model_validate_json(evaluation.model_dump_json())
        assert entry["agent_model_used"] == "strong-test-model"
        assert entry["fallback"] is False


async def test_model_payloads_contain_only_contract_keys_and_no_bytes() -> None:
    client, writer, sink = StubAgentClient(), ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    await graph.ainvoke(
        _initial_state(_raw_findings()),
        config={"recursion_limit": recursion_limit_for(3)},
    )
    analyze_calls = client.calls_for("analyze")
    assert len(analyze_calls) == 3
    for call in analyze_calls:
        payload = call["payload"]
        assert set(payload) <= PAYLOAD_KEYS
        assert "finding_id" not in payload  # bookkeeping never reaches the model
        assert all(isinstance(value, str) for value in payload.values())
        # The TASK-03 rubric is embedded in the system prompt verbatim.
        assert "SEVERITY RUBRIC" in call["system"]
    # Title calls carry no evidence either.
    for call in client.calls_for("draft_title"):
        assert "evidence_snippet" not in call["payload"]
    assert len(client.calls_for("summarize")) == 1


async def test_reasoning_depth_changes_prose_only_not_evidence() -> None:
    two_paragraphs = default_analysis()
    two_paragraphs.justification = (
        "First paragraph explaining the exposure.\n\nSecond paragraph with more detail."
    )
    raw = _raw_findings()[:1]
    original_snippet = raw[0]["payload"]["evidence_snippet"]

    brief_client, brief_writer = StubAgentClient(analysis=two_paragraphs), ListWriter()
    brief_graph = _build(brief_client, brief_writer, ListSink())
    brief_final = await brief_graph.ainvoke(
        _initial_state(raw, depth="brief"),
        config={"recursion_limit": recursion_limit_for(1)},
    )
    brief_eval = brief_final["evaluated_findings"][0]["evaluation"]
    assert brief_eval.justification == "First paragraph explaining the exposure."

    detailed_client, detailed_writer = StubAgentClient(analysis=two_paragraphs), ListWriter()
    detailed_graph = _build(detailed_client, detailed_writer, ListSink())
    detailed_final = await detailed_graph.ainvoke(
        _initial_state(raw, depth="detailed"),
        config={"recursion_limit": recursion_limit_for(1)},
    )
    detailed_eval = detailed_final["evaluated_findings"][0]["evaluation"]
    assert "Second paragraph" in detailed_eval.justification

    # Evidence and type are identical in both depths and match the input.
    for final in (brief_final, detailed_final):
        entry = final["evaluated_findings"][0]
        assert entry["payload"]["evidence_snippet"] == original_snippet
        assert entry["payload"]["finding_type"] == "gps"
    # The depth directive is what differs in the prompt.
    brief_prompt = brief_client.calls_for("analyze")[0]["system"]
    detailed_prompt = detailed_client.calls_for("analyze")[0]["system"]
    assert "Verbosity: brief" in brief_prompt
    assert "Verbosity: detailed" in detailed_prompt


async def test_empty_run_routes_straight_to_summary() -> None:
    client, writer, sink = StubAgentClient(), ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    final = await graph.ainvoke(
        _initial_state([]), config={"recursion_limit": recursion_limit_for(0)}
    )
    assert final["evaluated_findings"] == []
    assert writer.entries == []
    assert client.calls_for("analyze") == []
    assert client.calls_for("summarize") == []  # no LLM call for an empty run
    assert sink.texts and "no findings" in sink.texts[0].lower()


async def test_title_failure_degrades_to_a_deterministic_title() -> None:
    from metatracer.core.exceptions import AgentUnavailableError

    client = StubAgentClient(title_error=AgentUnavailableError("fast model down"))
    writer, sink = ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    final = await graph.ainvoke(
        _initial_state(_raw_findings()[:1]),
        config={"recursion_limit": recursion_limit_for(1)},
    )
    entry = final["evaluated_findings"][0]
    assert entry["saved"] is True
    assert entry["fallback"] is False  # the analysis itself succeeded
    assert entry["evaluation"].title == "Embedded GPS coordinates in EXIF:GPSInfo"
    assert len(final["error_log"]) == 1
    assert "draft_title" in final["error_log"][0]


async def test_hallucinating_model_is_corrected_by_the_guard_inside_the_graph() -> None:
    bad = default_analysis(severity=Severity.critical)  # GPS critical: not allowed
    bad.cited_evidence = "Latitude: 10.0, Longitude: 20.0"  # invented
    client = StubAgentClient(analysis=bad)
    writer, sink = ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    final = await graph.ainvoke(
        _initial_state(_raw_findings()[:1]),
        config={"recursion_limit": recursion_limit_for(1)},
    )
    evaluation = final["evaluated_findings"][0]["evaluation"]
    # GPS critical is capped at the ceiling (high), and the invented citation
    # is replaced by the verbatim snippet (dropping critical -> high first).
    assert evaluation.severity is Severity.high
    assert evaluation.cited_evidence == "Latitude: 40.416775, Longitude: -3.703790"
    assert final["evaluated_findings"][0]["guard_notes"]


@pytest.mark.parametrize("depth", ["brief", "standard", "detailed"])
async def test_all_depths_run_the_full_loop(depth: str) -> None:
    client, writer, sink = StubAgentClient(), ListWriter(), ListSink()
    graph = _build(client, writer, sink)
    final = await graph.ainvoke(
        _initial_state(_raw_findings()[:2], depth=depth),
        config={"recursion_limit": recursion_limit_for(2)},
    )
    assert len(final["evaluated_findings"]) == 2
    assert final["error_log"] == []
