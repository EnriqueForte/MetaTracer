"""AgentPipeline: run the TASK-05 agent phase for one persisted Run.

Analogous to :class:`~metatracer.classification.pipeline.ClassificationPipeline`:
loads the run's findings and assets, builds optimized payloads, executes the
LangGraph loop and returns counters. Persistence lives here (outside the
graph) so the topology stays unit-testable; the graph's
``SaveFindingEvaluationNode`` delegates to :class:`SqlEvaluationWriter`.

Persistence contract per finding (subtask 5.3.2):

- happy path: ``severity`` (guard-adjusted), ``severity_justification``,
  ``impact_analysis``, ``remediation_advice`` (the schema's ``remediation``),
  ``reproduction_steps`` (JSON array, like ``apply_assessment``) and
  ``agent_model_used`` = the strong model name;
- fallback: ``agent_model_used = "heuristic-fallback"`` — when the finding
  already had the TASK-03 baseline, its prose is left untouched; when
  ``severity`` was still NULL, the full heuristic assessment is applied
  (subtask 5.4.2). The finding is never deleted and the run never aborts.
- one ``AgentLog`` row per finding with token/latency accounting and the
  structured evaluation as ``raw_response`` — never the prompt, never the key;
- ``Finding.title`` (non-fallback evaluations only) and
  ``Run.executive_summary`` (summary node output) so the TASK-04 report can
  consume the agent prose on every export, not just in the live run.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.agents.graph import AgentState, build_graph, recursion_limit_for
from metatracer.agents.llm import AgentClient, RetryPolicy, build_default_client
from metatracer.agents.optimizer import ContextOptimizer
from metatracer.core.config import Settings
from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log, set_run_context
from metatracer.db.models import AgentLog, Finding, Run
from metatracer.db.repositories import (
    AgentLogRepository,
    AssetRepository,
    FindingRepository,
    RunRepository,
)

logger = logging.getLogger("metatracer.agents.pipeline")


@dataclass(frozen=True, slots=True)
class AgentSummary:
    """Counters of one agent phase, for the run log and the future UI."""

    run_id: str
    findings_evaluated: int
    findings_fallback: int
    findings_skipped_by_cap: int
    executive_summary: str | None
    errors: tuple[str, ...] = field(default_factory=tuple)


class ListSummarySink:
    """In-memory SummarySink: the pipeline returns the text in AgentSummary."""

    def __init__(self) -> None:
        self.text: str | None = None

    def set_summary(self, text: str) -> None:
        self.text = text


class SqlEvaluationWriter:
    """Persists one evaluated finding plus its AgentLog row (short sessions).

    The finding objects were loaded by the pipeline and are mutated here, then
    committed through the repositories — the same pattern as the
    classification pipeline (sequential sessions, single writer).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        findings_by_id: dict[str, Finding],
    ) -> None:
        self._session_factory = session_factory
        self._run_id = run_id
        self._findings = findings_by_id

    async def save_evaluation(self, entry: dict[str, Any]) -> None:
        """Persist severity + prose + model name + one AgentLog row."""
        finding = self._findings[entry["finding_id"]]
        evaluation = entry["evaluation"]
        # Fallback with an existing TASK-03 baseline: keep the baseline prose,
        # only mark where it came from (subtask 5.4.2). Everything else writes
        # the full evaluation (agent output or heuristic assessment).
        if not (entry["fallback"] and entry["had_baseline_severity"]):
            finding.severity = evaluation.severity
            finding.severity_justification = evaluation.justification
            finding.impact_analysis = evaluation.impact_analysis
            finding.remediation_advice = evaluation.remediation
            finding.reproduction_steps = json.dumps(
                evaluation.reproduction_steps, ensure_ascii=False
            )
        # The title is agent prose too: only a real (non-fallback) evaluation
        # sets it; otherwise the report keeps its per-type template title.
        if not entry["fallback"]:
            finding.title = evaluation.title.strip() or None
        finding.agent_model_used = entry["agent_model_used"]
        async with self._session_factory() as session:
            await FindingRepository(session).update(finding)

        usage = entry["usage"]
        raw_response = json.dumps(
            {
                "fallback": entry["fallback"],
                "guard_notes": entry.get("guard_notes", []),
                "evaluation": evaluation.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        log_entry = AgentLog(
            run_id=self._run_id,
            finding_id=finding.id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            model_name=entry["agent_model_used"],
            latency_ms=usage.latency_ms,
            raw_response=raw_response,
        )
        async with self._session_factory() as session:
            await AgentLogRepository(session).create(log_entry)


class AgentPipeline:
    """Runs the TASK-05 agent phase for one persisted Run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        client: AgentClient | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._client = (
            client if client is not None else build_default_client(settings, retry_policy)
        )

    async def execute(self, run_id: str) -> AgentSummary:
        """Evaluate every finding of the run (subject to the cost cap)."""
        set_run_context(run_id)
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")

        async with self._session_factory() as session:
            findings = await FindingRepository(session).list_by_run(run_id)
        async with self._session_factory() as session:
            assets = await AssetRepository(session).list_by_run(run_id)
        assets_by_id = {asset.id: asset for asset in assets}

        target_domain = _target_domain(run)
        optimizer = ContextOptimizer(self._settings.max_assets_per_run)
        optimized = optimizer.optimize(
            [(finding, assets_by_id.get(finding.asset_id)) for finding in findings],
            target_domain,
        )
        skipped = len(findings) - len(optimized)
        raw_findings = [
            {
                "finding_id": entry.finding_id,
                "payload": entry.payload,
                "had_baseline_severity": entry.had_baseline_severity,
            }
            for entry in optimized
        ]

        writer = SqlEvaluationWriter(
            self._session_factory, run_id, {finding.id: finding for finding in findings}
        )
        sink = ListSummarySink()
        graph = build_graph(
            client=self._client,
            writer=writer,
            sink=sink,
            strong_model_name=self._settings.llm_model or "heuristic-fallback",
        )
        initial_state: AgentState = {
            "target_domain": target_domain,
            # ReasoningDepth is a StrEnum; the value is one of the Literal choices.
            "reasoning_depth": run.reasoning_depth.value,  # type: ignore[typeddict-item]
            "raw_findings": raw_findings,
            "evaluated_findings": [],
            "current_index": 0,
            "error_log": [],
        }
        final_state: AgentState = await graph.ainvoke(
            initial_state, config={"recursion_limit": recursion_limit_for(len(raw_findings))}
        )

        evaluated = final_state["evaluated_findings"]
        fallback = sum(1 for entry in evaluated if entry["fallback"])
        errors = tuple(final_state["error_log"])
        # Persist the executive paragraph so re-exports (CLI `report`, API
        # export) show the agent summary instead of the heuristic note (4.1.2).
        if sink.text:
            async with self._session_factory() as session:
                repo = RunRepository(session)
                fresh = await repo.get(run_id)  # re-read: never merge a stale Run row
                if fresh is not None:
                    fresh.executive_summary = sink.text
                    await repo.update(fresh)
        summary = AgentSummary(
            run_id=run_id,
            findings_evaluated=len(evaluated) - fallback,
            findings_fallback=fallback,
            findings_skipped_by_cap=skipped,
            executive_summary=sink.text,
            errors=errors,
        )
        logger.info(
            "agent phase finished: %d evaluated, %d fallback, %d skipped by cap, %d errors",
            summary.findings_evaluated,
            summary.findings_fallback,
            summary.findings_skipped_by_cap,
            len(errors),
        )
        return summary


def _target_domain(run: Run) -> str:
    """First authorized domain (scope JSON); falls back to the raw input."""
    for raw in (run.allowed_scope, run.target_input):
        try:
            items = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(items, list) and items:
            return str(items[0])
    return "unknown"
