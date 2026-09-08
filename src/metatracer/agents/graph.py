"""MetaTracerGraph: the LangGraph agent loop (TASK-05, subtask 5.3).

Topology (whiteboard version):

    START -> LoadNextFindingNode --(findings left)--> AnalyzeContextNode
                                                        |
                                              ClassifySeverityNode
                                                        |
                                              DraftExplanationNode
                                                        |
                                              SaveFindingEvaluationNode
                                                        |
                                              back to LoadNextFindingNode
                  LoadNextFindingNode --(none left)--> SynthesizeReportSummaryNode -> END

One strong-model structured call per finding (the cost cap blesses
"1 finding/call" in the MVP); the fast model drafts the title and the final
executive summary. Per-finding flow:

- ``AnalyzeContextNode`` builds the system prompt (rubric + prohibitions +
  depth directive) and calls the strong model for the full analysis. Any
  model failure flags the entry as ``fallback`` — the loop never breaks.
- ``ClassifySeverityNode`` runs the deterministic :class:`EvidenceGuard`
  (citation substring, ceilings, payload-word filter) or, on fallback, the
  TASK-03 heuristic classifier.
- ``DraftExplanationNode`` adds the fast-model title (deterministic template
  when unavailable), applies the ``reasoning_depth`` prose shaping and
  assembles the schema-valid :class:`AgentFindingEvaluation`.
- ``SaveFindingEvaluationNode`` delegates persistence to the injected
  ``EvaluationWriter`` (DB lives outside the graph, so the topology stays
  testable) and advances ``current_index``.

``reasoning_depth`` only changes prose length (subtask 5.4.4): it feeds the
prompt directive and the brief-paragraph shaping; evidence and finding type
are never touched.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from metatracer.agents.guard import EvidenceGuard, transient_finding
from metatracer.agents.llm import AgentClient, LLMUsage
from metatracer.agents.prompts import (
    analysis_system_prompt,
    summary_system_prompt,
    title_system_prompt,
)
from metatracer.agents.schemas import AgentFindingEvaluation
from metatracer.classification.classifier import SeverityAssessment, classify_heuristically
from metatracer.core.exceptions import AgentUnavailableError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import FindingType, Severity

logger = logging.getLogger("metatracer.agents.graph")

# Node names (also the astream "updates" keys used by tests and observers).
NODE_LOAD = "load_next_finding"
NODE_ANALYZE = "analyze_context"
NODE_CLASSIFY = "classify_severity"
NODE_DRAFT = "draft_explanation"
NODE_SAVE = "save_evaluation"
NODE_SUMMARIZE = "synthesize_summary"

# Cap for model-drafted titles before they reach AgentLog / the summary payload.
_MAX_TITLE_CHARS = 120
_TITLE_MARK = "..."

# Deterministic titles when the fast model is unavailable or the finding is on
# the heuristic fallback path; they name type and field, never the evidence.
_FALLBACK_TITLES: dict[FindingType, str] = {
    FindingType.gps: "Embedded GPS coordinates",
    FindingType.email: "Corporate email address",
    FindingType.internal_path: "Internal filesystem path",
    FindingType.software_version: "Software version disclosure",
    FindingType.debug_comment: "Debug or comment leftover",
}


class AgentState(TypedDict):
    """Graph state (contract of subtask 5.3.1 — do not extend).

    ``raw_findings`` entries are ``{"finding_id", "payload", "had_baseline_severity"}``
    dicts; only ``payload`` (the closed contract keys) is ever sent to a model.
    ``evaluated_findings`` holds one working dict per processed finding; nodes
    refine the last entry as it flows through the loop.
    """

    target_domain: str
    reasoning_depth: Literal["brief", "standard", "detailed"]
    raw_findings: list[dict]
    evaluated_findings: list[dict]
    current_index: int
    error_log: list[str]


class EvaluationWriter(Protocol):
    """Persistence seam for SaveFindingEvaluationNode (implemented in pipeline)."""

    async def save_evaluation(self, entry: dict[str, Any]) -> None: ...


class SummarySink(Protocol):
    """Receives the executive summary text once per run."""

    def set_summary(self, text: str) -> None: ...


@dataclass(slots=True)
class GraphNodes:
    """Bundle of the six node callables, sharing the injected dependencies."""

    client: AgentClient
    writer: EvaluationWriter
    sink: SummarySink
    strong_model_name: str
    guard: EvidenceGuard


class LoadNextFindingNode:
    """Routing node: the conditional edge decides analyze vs. summarize."""

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        total = len(state["raw_findings"])
        logger.debug(
            "agent loop: finding %d/%d", min(state["current_index"] + 1, total), total
        )
        return {}


def route_after_load(state: AgentState) -> Literal["analyze", "done"]:
    """Loop while unprocessed findings remain; then synthesize the summary."""
    return "analyze" if state["current_index"] < len(state["raw_findings"]) else "done"


class AnalyzeContextNode:
    """Bounty-triager call: one strong-model structured analysis per finding.

    The prompt forbids assuming facts beyond the payload; failure flags the
    entry for the heuristic fallback instead of breaking the loop.
    """

    def __init__(self, client: AgentClient) -> None:
        self._client = client

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        entry = dict(state["raw_findings"][state["current_index"]])
        error_log = list(state["error_log"])
        try:
            result = await self._client.analyze(
                analysis_system_prompt(state["reasoning_depth"]), entry["payload"]
            )
        except AgentUnavailableError as exc:
            logger.warning(
                "analysis unavailable for finding %s: %s",
                sanitize_for_log(entry["finding_id"]),
                sanitize_for_log(exc),
            )
            error_log.append(f"analyze_context failed for {entry['finding_id']}: {exc}")
            entry.update({"fallback": True, "analysis": None, "usage": LLMUsage()})
        else:
            entry.update({"fallback": False, "analysis": result.value, "usage": result.usage})
        return {
            "evaluated_findings": [*state["evaluated_findings"], entry],
            "error_log": error_log,
        }


class ClassifySeverityNode:
    """Applies the rubric: evidence guard on proposals, heuristic on fallback."""

    def __init__(self, guard: EvidenceGuard) -> None:
        self._guard = guard

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        entries = list(state["evaluated_findings"])
        entry = dict(entries[-1])
        payload = entry["payload"]
        notes: list[str] = []
        assessment: SeverityAssessment | None = None

        if entry["fallback"]:
            # Subtask 5.4.2: the finding is never dropped; the deterministic
            # heuristic provides severity and safe prose instead.
            assessment = classify_heuristically(transient_finding(payload))
            final_severity = assessment.severity
            notes.append("llm unavailable; deterministic heuristic fallback applied")
        else:
            analysis = entry["analysis"]
            outcome = self._guard.check(
                severity=analysis.severity,
                cited_evidence=analysis.cited_evidence,
                reproduction_steps=list(analysis.reproduction_steps),
                payload=payload,
                justification=analysis.justification,
            )
            notes.extend(outcome.notes)
            if outcome.rejected:
                # Rubric is the source of truth: drop the incoherent proposal.
                assessment = classify_heuristically(transient_finding(payload))
                entry["fallback"] = True
                entry["heuristic_assessment"] = assessment
                final_severity = assessment.severity
                notes.append("incoherent explanation; heuristic evaluation substituted")
            else:
                entry["analysis"] = analysis.model_copy(
                    update={
                        "severity": outcome.severity,
                        "cited_evidence": outcome.cited_evidence,
                        "reproduction_steps": outcome.reproduction_steps,
                    }
                )
                final_severity = outcome.severity

        entry.update(
            {
                "final_severity": final_severity,
                "heuristic_assessment": assessment,
                "guard_notes": notes,
            }
        )
        entries[-1] = entry
        return {"evaluated_findings": entries}


class DraftExplanationNode:
    """Title (fast model) + depth shaping; assembles the final evaluation.

    A title-call failure does NOT trigger the full fallback: the analysis is
    valid, so a deterministic template title is used and the miss is logged.
    """

    def __init__(self, client: AgentClient, strong_model_name: str) -> None:
        self._client = client
        self._strong_model_name = strong_model_name

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        entries = list(state["evaluated_findings"])
        entry = dict(entries[-1])
        payload = entry["payload"]
        depth = state["reasoning_depth"]
        error_log = list(state["error_log"])

        if entry["fallback"]:
            assessment = entry["heuristic_assessment"]
            evaluation = AgentFindingEvaluation(
                severity=entry["final_severity"],
                justification=assessment.justification,
                impact_analysis=assessment.impact_analysis,
                remediation=assessment.remediation_advice,
                reproduction_steps=list(assessment.reproduction_steps),
                cited_evidence=payload.get("evidence_snippet", ""),
                title=_fallback_title(payload),
            )
            entry["agent_model_used"] = "heuristic-fallback"
        else:
            analysis = entry["analysis"]
            title = await self._title_for(entry, payload, error_log)
            justification = _shape_prose(analysis.justification, depth)
            evaluation = AgentFindingEvaluation(
                severity=entry["final_severity"],
                justification=justification,
                impact_analysis=analysis.impact_analysis,
                remediation=analysis.remediation,
                reproduction_steps=list(analysis.reproduction_steps),
                cited_evidence=analysis.cited_evidence,
                title=title,
            )
            entry["agent_model_used"] = self._strong_model_name

        entry["evaluation"] = evaluation
        entries[-1] = entry
        return {"evaluated_findings": entries, "error_log": error_log}

    async def _title_for(
        self, entry: dict[str, Any], payload: dict[str, str], error_log: list[str]
    ) -> str:
        title_payload = {
            "finding_type": payload.get("finding_type", ""),
            "field_source": payload.get("field_source", ""),
            "severity": str(entry["final_severity"]),
            "asset_content_type": payload.get("asset_content_type", ""),
        }
        try:
            result = await self._client.draft_title(title_system_prompt(), title_payload)
        except AgentUnavailableError as exc:
            logger.warning(
                "title drafting failed for finding %s: %s",
                sanitize_for_log(entry["finding_id"]),
                sanitize_for_log(exc),
            )
            error_log.append(f"draft_title failed for {entry['finding_id']}: {exc}")
            return _fallback_title(payload)
        entry["usage"] = entry["usage"].plus(result.usage)
        title = result.value.title.strip()
        # The prompt asks for brevity; enforce it here too so a runaway model
        # cannot bloat AgentLog rows or the summary payload (denial of wallet).
        if len(title) > _MAX_TITLE_CHARS:
            title = title[: _MAX_TITLE_CHARS - len(_TITLE_MARK)] + _TITLE_MARK
        return title or _fallback_title(payload)


class SaveFindingEvaluationNode:
    """Persists the refined entry through the injected writer and advances."""

    def __init__(self, writer: EvaluationWriter) -> None:
        self._writer = writer

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        entries = list(state["evaluated_findings"])
        entry = dict(entries[-1])
        await self._writer.save_evaluation(entry)
        entry["saved"] = True
        entries[-1] = entry
        return {
            "evaluated_findings": entries,
            "current_index": state["current_index"] + 1,
        }


class SynthesizeReportSummaryNode:
    """Executive paragraph with the fast model; deterministic on any failure."""

    def __init__(self, client: AgentClient, sink: SummarySink) -> None:
        self._client = client
        self._sink = sink

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        error_log = list(state["error_log"])
        evaluated = state["evaluated_findings"]
        if not evaluated:
            self._sink.set_summary(
                f"Metadata exposure review of {state['target_domain']}: no findings "
                "were produced by the detection phase; nothing required agent analysis."
            )
            return {}
        if not self._client.available or all(e["fallback"] for e in evaluated):
            self._sink.set_summary(_deterministic_summary(state))
            return {}
        payload = _summary_payload(state)
        try:
            result = await self._client.summarize(summary_system_prompt(), payload)
        except AgentUnavailableError as exc:
            logger.warning("executive summary failed: %s", sanitize_for_log(exc))
            error_log.append(f"synthesize_summary failed: {exc}")
            self._sink.set_summary(_deterministic_summary(state))
            return {"error_log": error_log}
        self._sink.set_summary(result.value.executive_summary.strip())
        return {}


def build_graph(
    *,
    client: AgentClient,
    writer: EvaluationWriter,
    sink: SummarySink,
    strong_model_name: str,
    guard: EvidenceGuard | None = None,
) -> Any:
    """Compile the MetaTracer agent graph (topology of subtask 5.3.3)."""
    guard = guard or EvidenceGuard()
    graph = StateGraph(AgentState)
    graph.add_node(NODE_LOAD, LoadNextFindingNode())
    graph.add_node(NODE_ANALYZE, AnalyzeContextNode(client))
    graph.add_node(NODE_CLASSIFY, ClassifySeverityNode(guard))
    graph.add_node(NODE_DRAFT, DraftExplanationNode(client, strong_model_name))
    graph.add_node(NODE_SAVE, SaveFindingEvaluationNode(writer))
    graph.add_node(NODE_SUMMARIZE, SynthesizeReportSummaryNode(client, sink))

    graph.add_edge(START, NODE_LOAD)
    graph.add_conditional_edges(
        NODE_LOAD, route_after_load, {"analyze": NODE_ANALYZE, "done": NODE_SUMMARIZE}
    )
    graph.add_edge(NODE_ANALYZE, NODE_CLASSIFY)
    graph.add_edge(NODE_CLASSIFY, NODE_DRAFT)
    graph.add_edge(NODE_DRAFT, NODE_SAVE)
    graph.add_edge(NODE_SAVE, NODE_LOAD)
    graph.add_edge(NODE_SUMMARIZE, END)
    return graph.compile()


def recursion_limit_for(finding_count: int) -> int:
    """LangGraph super-step budget for the loop: 5 nodes per finding + slack."""
    return 6 * finding_count + 25


def _shape_prose(justification: str, depth: str) -> str:
    """Depth only shapes prose length (subtask 5.4.4); evidence is untouched."""
    if depth == "brief":
        return justification.split("\n\n", 1)[0].strip()
    return justification.strip()


def _fallback_title(payload: dict[str, str]) -> str:
    finding_type = FindingType(payload.get("finding_type", "debug_comment"))
    field_source = payload.get("field_source", "").strip()
    label = _FALLBACK_TITLES[finding_type]
    return f"{label} in {field_source}" if field_source else label


def _summary_payload(state: AgentState) -> dict[str, Any]:
    """Aggregate counts and titles for the summary call — never any evidence."""
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    top_titles: list[str] = []
    for entry in state["evaluated_findings"]:
        severity = str(entry["final_severity"])
        by_severity[severity] = by_severity.get(severity, 0) + 1
        finding_type = entry["payload"].get("finding_type", "unknown")
        by_type[finding_type] = by_type.get(finding_type, 0) + 1
        if entry["final_severity"] in (Severity.critical, Severity.high) and entry.get(
            "evaluation"
        ):
            top_titles.append(entry["evaluation"].title)
    return {
        "target_domain": state["target_domain"],
        "total_findings": len(state["evaluated_findings"]),
        "by_severity": by_severity,
        "by_type": by_type,
        "top_titles": top_titles[:5],
    }


def _deterministic_summary(state: AgentState) -> str:
    """Model-free executive paragraph for fallback runs (English, factual)."""
    counts: dict[str, int] = {}
    for entry in state["evaluated_findings"]:
        severity = str(entry["final_severity"])
        counts[severity] = counts.get(severity, 0) + 1
    distribution = ", ".join(f"{severity}: {n}" for severity, n in sorted(counts.items()))
    return (
        f"Metadata exposure review of {state['target_domain']}: "
        f"{len(state['evaluated_findings'])} finding(s) were evaluated with the "
        f"deterministic heuristic baseline because AI analysis was unavailable "
        f"(severity distribution: {distribution}). Review each finding's template "
        "justification and remediation advice."
    )
