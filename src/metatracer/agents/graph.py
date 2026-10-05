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

import hashlib
import json
import logging
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from metatracer.agents.guard import (
    EvidenceGuard,
    cap_to_baseline,
    fallback_title,
    has_hostile_wording,
    transient_finding,
)
from metatracer.agents.llm import AgentClient, LLMResult, LLMUsage
from metatracer.agents.prompts import (
    analysis_system_prompt,
    summary_system_prompt,
    title_system_prompt,
)
from metatracer.agents.schemas import AgentFindingEvaluation
from metatracer.classification.classifier import SeverityAssessment, classify_heuristically
from metatracer.core.exceptions import AgentUnavailableError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import Severity

logger = logging.getLogger("metatracer.agents.graph")

# Node names (also the astream "updates" keys used by tests and observers).
NODE_LOAD = "load_next_finding"
NODE_ANALYZE = "analyze_context"
NODE_CLASSIFY = "classify_severity"
NODE_DRAFT = "draft_explanation"
NODE_SAVE = "save_evaluation"
NODE_SUMMARIZE = "synthesize_summary"

# The guard enforces title length and hostile wording (TASK-29).


class AgentState(TypedDict):
    """Graph state (contract of subtask 5.3.1 — do not extend).

    ``raw_findings`` entries are ``{"finding_id", "payload", "had_baseline_severity"}``
    dicts; only ``payload`` (the closed contract keys) is ever sent to a model.
    ``evaluated_findings`` holds one working dict per processed finding; nodes
    refine the last entry as it flows through the loop.

    TASK-29: ``baseline_severity`` (the persisted level, including operator
    feedback) also travels outside ``payload``. The guard uses it as a ceiling.
    It is not one of ``PAYLOAD_KEYS`` and is not sent to the model.

    TASK-13 (v2.1+): each entry may additionally carry ``feedback_examples``
    (a list of operator-feedback dicts for findings of the same type). They
    travel OUTSIDE the closed ``payload`` — the ContextOptimizer contract
    stays intact — and ``AnalyzeContextNode`` merges them into the model
    message as guidance, never as evidence.
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

    TASK-13 (v2.1+): when the entry carries ``feedback_examples`` (operator
    corrections for the same finding type), they are merged into the model
    message as non-authoritative guidance — the rubric, the guard and the
    payload remain the source of truth, and the examples never replace the
    evidence snippet.

    TASK-14 (v2.1+): when the entry carries ``retrieved_evidence`` (historical
    full-text hits from previous runs), the *titles and snippets* are merged
    into the model message as **precedent context only** — never as evidence
    of the current finding. The prompt tells the model to treat it as
    background, and ``cited_evidence`` must still be a substring of the
    current ``evidence_snippet``.
    """

    def __init__(self, client: AgentClient) -> None:
        self._client = client
        # Per-run cache: identical closed payloads (same evidence on another
        # asset) reuse the strong-model answer. Failures are not cached.
        self._analysis_cache: dict[str, LLMResult[Any]] = {}

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        entry = dict(state["raw_findings"][state["current_index"]])
        error_log = list(state["error_log"])
        model_payload = dict(entry["payload"])
        feedback = entry.get("feedback_examples")
        if feedback:
            # Guidance only, outside the closed payload-contract keys.
            model_payload = {**model_payload, "feedback_examples": feedback}
        retrieved = entry.get("retrieved_evidence")
        if retrieved:
            # TASK-14: precedent context, capped and cited as background only.
            model_payload = {
                **model_payload,
                "retrieved_evidence": _retrieved_to_prompt(retrieved),
            }
        sent = message_payload(model_payload)
        cache_key = _analysis_cache_key(sent)
        cached = self._analysis_cache.get(cache_key)
        try:
            if cached is not None:
                result = LLMResult(value=cached.value, usage=LLMUsage())
            else:
                result = await self._client.analyze(
                    analysis_system_prompt(state["reasoning_depth"]),
                    sent,
                )
                self._analysis_cache[cache_key] = result
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
            if feedback:
                entry["feedback_used"] = True
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
            # heuristic provides severity and safe prose instead. The operator
            # baseline still caps that severity (TASK-29).
            assessment = classify_heuristically(transient_finding(payload))
            final_severity = _capped_baseline(assessment.severity, entry)
            notes.append("llm unavailable; deterministic heuristic fallback applied")
        else:
            analysis = entry["analysis"]
            baseline = _baseline(entry)
            outcome = self._guard.check(
                severity=analysis.severity,
                cited_evidence=analysis.cited_evidence,
                reproduction_steps=list(analysis.reproduction_steps),
                payload=payload,
                justification=analysis.justification,
                impact_analysis=analysis.impact_analysis,
                remediation=analysis.remediation,
                baseline_severity=baseline,
            )
            notes.extend(outcome.notes)
            if outcome.rejected:
                # Rubric is the source of truth: drop the incoherent proposal.
                # Do not adopt a heuristic that undoes the operator baseline.
                assessment = classify_heuristically(transient_finding(payload))
                entry["fallback"] = True
                entry["heuristic_assessment"] = assessment
                final_severity = _capped_baseline(assessment.severity, entry)
                notes.append("incoherent explanation; heuristic evaluation substituted")
            else:
                entry["analysis"] = analysis.model_copy(
                    update={
                        "severity": outcome.severity,
                        "cited_evidence": outcome.cited_evidence,
                        "reproduction_steps": outcome.reproduction_steps,
                        "justification": outcome.justification,
                        "impact_analysis": outcome.impact_analysis,
                        "remediation": outcome.remediation,
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
        if entry.get("retrieved_evidence"):
            # TASK-14: trace RAG usage without leaking the retrieved snippets
            # themselves (they are other runs' findings, see knowledge.py).
            notes.append(f"retrieved_evidence_used={len(entry['retrieved_evidence'])}")
            entry["guard_notes"] = notes
        entries[-1] = entry
        return {"evaluated_findings": entries}


class DraftExplanationNode:
    """Title (fast model) + depth shaping; assembles the final evaluation.

    A title-call failure does NOT trigger the full fallback: the analysis is
    valid, so a deterministic template title is used and the miss is logged.
    """

    def __init__(self, client: AgentClient, strong_model_name: str, guard: EvidenceGuard) -> None:
        self._client = client
        self._strong_model_name = strong_model_name
        self._guard = guard

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
        title, title_notes = self._guard.sanitize_title(result.value.title, payload)
        if title_notes:
            notes = list(entry.get("guard_notes") or [])
            notes.extend(title_notes)
            entry["guard_notes"] = notes
        entry["usage"] = entry["usage"].plus(result.usage)
        return title or fallback_title(payload)


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
        text = result.value.executive_summary.strip()
        if has_hostile_wording(text):
            logger.warning("executive summary contained disallowed wording; using the template")
            self._sink.set_summary(_deterministic_summary(state))
            return {}
        self._sink.set_summary(text)
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
    graph.add_node(NODE_DRAFT, DraftExplanationNode(client, strong_model_name, guard))
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


# TASK-14: retrieve cap for the prompt injection. The retrieved snippets are
# other findings' evidence (potentially sensitive: GPS, paths); they travel to
# the model only as short precedent context and are never logged (AgentLog
# stores the guard note counter, not the snippets).
_MAX_RETRIEVED_CHARS = 800


def _baseline(entry: dict[str, Any]) -> Severity | None:
    raw = entry.get("baseline_severity")
    if not raw:
        return None
    return Severity(raw)


def _capped_baseline(severity: Severity, entry: dict[str, Any]) -> Severity:
    return cap_to_baseline(severity, _baseline(entry))


def _analysis_cache_key(payload: dict[str, Any]) -> str:
    """Hash of the model message, ignoring the asset URL.

    The same evidence on two assets is one strong-model call (TASK-34).
    ``asset_url`` is the only field that changes between those assets.
    """
    stable = {key: value for key, value in payload.items() if key != "asset_url"}
    encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """User message: evidence is delimited; RAG is labeled as not evidence.

    The closed ``payload`` stored on the finding is unchanged. This copy is
    what the model sees (TASK-29, prompt analysis-system-v2).
    """
    message = dict(payload)
    snippet = str(message.get("evidence_snippet", ""))
    message["evidence_snippet"] = f"<<<EVIDENCE>>>\n{snippet}\n<<<END>>>"
    historical = message.pop("retrieved_evidence", None)
    if historical is not None:
        message["historical_not_evidence"] = historical
    return message


def _retrieved_to_prompt(retrieved: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Serialize retrieved hits for the prompt: capped, string-only, safe.

    Input rows come from the pipeline and already contain only the contract
    keys (finding_type, evidence_snippet, severity, title, score). We re-cap
    the total size so a pathological index cannot bloat the model call.
    """
    rendered: list[dict[str, str]] = []
    used = 0
    for hit in retrieved:
        title = (hit.get("title") or "").strip()
        snippet = (hit.get("evidence_snippet") or "").strip()
        if not snippet:
            continue
        entry = {
            "finding_type": str(hit.get("finding_type", "unknown")),
            "evidence_snippet": snippet,
            "severity": str(hit.get("severity")) if hit.get("severity") else "unknown",
            "title": title[:160],
        }
        cost = sum(len(value) for value in entry.values())
        if used + cost > _MAX_RETRIEVED_CHARS:
            break
        used += cost
        rendered.append(entry)
    return rendered


def _fallback_title(payload: dict[str, str]) -> str:
    return fallback_title(payload)


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
