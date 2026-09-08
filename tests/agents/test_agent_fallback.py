"""Resilience and fallback tests (TASK-05, subtask 5.4).

Covers both layers:

- client level: tenacity retries on 429/500/timeout, one schema-retry, then
  ``AgentUnavailableError`` — no real API is ever contacted (scripted stub);
- pipeline level: a dead or unconfigured model degrades every finding to the
  TASK-03 heuristic, ``agent_model_used="heuristic-fallback"``, findings are
  never lost and the run never aborts.
"""

import json

import httpx
import pytest
from langchain_core.exceptions import OutputParserException
from openai import APITimeoutError, AuthenticationError, InternalServerError
from pydantic import SecretStr

from metatracer.agents.llm import LangChainAgentClient, NullAgentClient, RetryPolicy
from metatracer.agents.pipeline import AgentPipeline
from metatracer.agents.schemas import AgentFindingAnalysis
from metatracer.core.config import Settings
from metatracer.core.exceptions import AgentUnavailableError, MetaTracerError
from metatracer.db.models import AgentLog, Finding, Severity
from metatracer.db.repositories import (
    AgentLogRepository,
    AssetRepository,
    FindingRepository,
    RunRepository,
)

from .conftest import (
    ScriptedChatModel,
    StubAgentClient,
    default_analysis,
    make_asset,
    make_finding,
    make_run,
)

_REQUEST = httpx.Request("POST", "http://llm.test/v1/chat/completions")


def _http_error(status: int) -> InternalServerError:
    return InternalServerError(
        f"upstream {status}", response=httpx.Response(status, request=_REQUEST), body=None
    )


def _client(strong: ScriptedChatModel) -> LangChainAgentClient:
    return LangChainAgentClient(
        strong,
        ScriptedChatModel([]),
        strong_model_name="strong-test-model",
        fast_model_name="fast-test-model",
        rate_limit_rps=0.0,  # no pacing sleep in tests
        retry_policy=RetryPolicy(attempts=3, wait_initial_s=0.0, wait_max_s=0.0),
    )


# ---------------------------------------------------------------- client level


async def test_retryable_500s_are_retried_then_succeed() -> None:
    strong = ScriptedChatModel([_http_error(500), _http_error(500), {"parsed": default_analysis()}])
    result = await _client(strong).analyze("system", {"finding_type": "gps"})
    assert isinstance(result.value, AgentFindingAnalysis)
    assert strong.invocations == 3


async def test_timeouts_are_retryable() -> None:
    strong = ScriptedChatModel([APITimeoutError(request=_REQUEST), {"parsed": default_analysis()}])
    result = await _client(strong).analyze("system", {})
    assert isinstance(result.value, AgentFindingAnalysis)
    assert strong.invocations == 2


async def test_exhausted_retries_raise_agent_unavailable() -> None:
    strong = ScriptedChatModel([_http_error(500), _http_error(500), _http_error(500)])
    with pytest.raises(AgentUnavailableError):
        await _client(strong).analyze("system", {})
    assert strong.invocations == 3  # exactly the configured attempts


async def test_non_retryable_error_fails_fast_without_retries() -> None:
    auth_error = AuthenticationError(
        "bad key", response=httpx.Response(401, request=_REQUEST), body=None
    )
    strong = ScriptedChatModel([auth_error])
    with pytest.raises(AgentUnavailableError):
        await _client(strong).analyze("system", {})
    assert strong.invocations == 1


async def test_schema_violation_is_retried_exactly_once() -> None:
    strong = ScriptedChatModel(
        [
            {"parsed": None, "parsing_error": OutputParserException("not json")},
            {"parsed": default_analysis()},
        ]
    )
    result = await _client(strong).analyze("system", {})
    assert isinstance(result.value, AgentFindingAnalysis)
    assert strong.invocations == 2


async def test_persistent_schema_violation_raises_agent_unavailable() -> None:
    strong = ScriptedChatModel(
        [
            {"parsed": None, "parsing_error": OutputParserException("bad")},
            {"parsed": None, "parsing_error": OutputParserException("bad again")},
        ]
    )
    with pytest.raises(AgentUnavailableError, match="schema-invalid"):
        await _client(strong).analyze("system", {})
    assert strong.invocations == 2  # one retry, not the transport retry budget


async def test_null_client_always_raises_agent_unavailable() -> None:
    client = NullAgentClient("not configured")
    assert client.available is False
    with pytest.raises(AgentUnavailableError, match="not configured"):
        await client.analyze("system", {})


# -------------------------------------------------------------- pipeline level


async def _seed(session_factory, findings: list[Finding]) -> str:
    run = make_run()
    asset = make_asset(run.id)
    for finding in findings:
        finding.run_id = run.id
        finding.asset_id = asset.id
    async with session_factory() as session:
        await RunRepository(session).create(run)
    async with session_factory() as session:
        await AssetRepository(session).create(asset)
    async with session_factory() as session:
        await FindingRepository(session).create_many(findings)
    return run.id


async def _reload_finding(session_factory, finding_id: str) -> Finding:
    async with session_factory() as session:
        finding = await FindingRepository(session).get(finding_id)
    assert finding is not None
    return finding


async def _agent_logs(session_factory, run_id: str) -> list[AgentLog]:
    async with session_factory() as session:
        return await AgentLogRepository(session).list_by_run(run_id)


async def test_model_failure_falls_back_to_heuristic_without_losing_findings(
    session_factory, settings
) -> None:
    baseline = make_finding("run", "asset", severity=Severity.high,
                            severity_justification="BASELINE JUSTIFICATION")
    unclassified = make_finding("run", "asset", severity=None)
    run_id = await _seed(session_factory, [baseline, unclassified])

    client = StubAgentClient(analyze_error=AgentUnavailableError("HTTP 500 after 3 attempts"))
    summary = await AgentPipeline(session_factory, settings, client=client).execute(run_id)

    assert summary.findings_fallback == 2
    assert summary.findings_evaluated == 0
    assert len(summary.errors) == 2  # one logged error per failed analysis
    assert summary.executive_summary  # deterministic summary, run did not abort

    # Baseline finding: prose untouched, only the provenance mark changes.
    baseline_after = await _reload_finding(session_factory, baseline.id)
    assert baseline_after.severity is Severity.high
    assert baseline_after.severity_justification == "BASELINE JUSTIFICATION"
    assert baseline_after.agent_model_used == "heuristic-fallback"

    # NULL-severity finding: the full heuristic assessment is applied.
    unclassified_after = await _reload_finding(session_factory, unclassified.id)
    assert unclassified_after.severity is Severity.high  # valid GPS -> high
    assert unclassified_after.severity_justification
    assert json.loads(unclassified_after.reproduction_steps)
    assert unclassified_after.agent_model_used == "heuristic-fallback"

    logs = await _agent_logs(session_factory, run_id)
    assert len(logs) == 2
    assert all(log.model_name == "heuristic-fallback" for log in logs)
    assert all(log.prompt_tokens == 0 for log in logs)
    assert all(json.loads(log.raw_response)["fallback"] is True for log in logs)


async def test_empty_api_key_degrades_the_whole_run(session_factory) -> None:
    settings = Settings(llm_api_key=SecretStr(""), llm_base_url="", llm_model="")
    finding = make_finding("run", "asset", severity=None)
    run_id = await _seed(session_factory, [finding])

    # No client injected: the pipeline builds the null client by itself.
    summary = await AgentPipeline(session_factory, settings).execute(run_id)

    assert summary.findings_fallback == 1
    after = await _reload_finding(session_factory, finding.id)
    assert after.severity is Severity.high
    assert after.agent_model_used == "heuristic-fallback"


async def test_happy_path_persists_evaluation_and_agent_log(session_factory, settings) -> None:
    finding = make_finding("run", "asset", severity=Severity.high,
                           severity_justification="BASELINE JUSTIFICATION")
    run_id = await _seed(session_factory, [finding])
    client = StubAgentClient(analysis=default_analysis())

    summary = await AgentPipeline(session_factory, settings, client=client).execute(run_id)

    assert summary.findings_evaluated == 1
    assert summary.findings_fallback == 0
    assert summary.executive_summary == (
        "Three findings were reviewed; one needs urgent scrubbing."
    )

    after = await _reload_finding(session_factory, finding.id)
    analysis = default_analysis()
    assert after.severity is Severity.high
    assert after.severity_justification == analysis.justification
    assert after.impact_analysis == analysis.impact_analysis
    assert after.remediation_advice == analysis.remediation  # schema -> model field
    assert json.loads(after.reproduction_steps) == analysis.reproduction_steps
    assert after.agent_model_used == "strong-test-model"

    logs = await _agent_logs(session_factory, run_id)
    assert len(logs) == 1
    log = logs[0]
    assert log.model_name == "strong-test-model"
    assert log.prompt_tokens == 120 + 30  # strong analysis + fast title, aggregated
    assert log.completion_tokens == 40 + 8
    raw = json.loads(log.raw_response)
    assert raw["fallback"] is False
    assert raw["evaluation"]["severity"] == "high"
    # Observability without secrets: never the prompt, never the API key.
    assert "SEVERITY RUBRIC" not in log.raw_response
    assert "sk-test" not in log.raw_response


async def test_agent_prose_is_persisted_for_report_reuse(session_factory, settings) -> None:
    """Title and executive summary land in the database (TASK-04 consumes them)."""
    finding = make_finding("run", "asset", severity=Severity.high)
    run_id = await _seed(session_factory, [finding])
    client = StubAgentClient(analysis=default_analysis(), title="Precise GPS Fix in Public Photo")

    summary = await AgentPipeline(session_factory, settings, client=client).execute(run_id)

    after = await _reload_finding(session_factory, finding.id)
    assert after.title == "Precise GPS Fix in Public Photo"
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None
    assert run.executive_summary == summary.executive_summary
    assert run.status == run.status  # untouched: only the summary column was written


async def test_fallback_never_writes_an_agent_title(session_factory, settings) -> None:
    finding = make_finding("run", "asset", severity=Severity.high)
    run_id = await _seed(session_factory, [finding])
    client = StubAgentClient(analyze_error=AgentUnavailableError("down"))

    summary = await AgentPipeline(session_factory, settings, client=client).execute(run_id)

    after = await _reload_finding(session_factory, finding.id)
    assert after.title is None  # report keeps its per-type template title
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None and run.executive_summary == summary.executive_summary


async def test_unknown_run_raises(session_factory, settings) -> None:
    pipeline = AgentPipeline(session_factory, settings, client=StubAgentClient())
    with pytest.raises(MetaTracerError, match="run not found"):
        await pipeline.execute("no-such-run")
