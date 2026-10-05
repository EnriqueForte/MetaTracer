"""TASK-34: agent budget is independent of the asset cap, plus response cache."""

import asyncio

import pytest
from pydantic import SecretStr

from metatracer.agents.llm import LangChainAgentClient, RetryPolicy
from metatracer.agents.optimizer import ContextOptimizer
from metatracer.agents.pipeline import AgentPipeline
from metatracer.core.config import Settings
from metatracer.db.models import Severity
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository

from .conftest import (
    ScriptedChatModel,
    ScriptedRunnable,
    StubAgentClient,
    make_asset,
    make_finding,
    make_run,
)


def test_optimizer_keeps_100_of_120_findings() -> None:
    rows = [
        (
            make_finding(
                "run",
                "asset",
                evidence_snippet=f"Latitude: 40.{index:06d}, Longitude: -3.700000",
                severity=Severity.high,
            ),
            None,
        )
        for index in range(120)
    ]
    entries = ContextOptimizer(max_findings=100).optimize(rows, "target.com")
    assert len(entries) == 100


async def test_pipeline_agentizes_the_agent_budget_not_the_asset_cap(session_factory) -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key=SecretStr("sk-test"),
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="strong-test-model",
        max_assets_per_run=5,
        max_agent_findings=100,
        rate_limit_rps=0.0,
    )
    run = make_run()
    asset = make_asset(run.id)
    findings = [
        make_finding(
            run.id,
            asset.id,
            evidence_snippet=f"Latitude: 41.{index:06d}, Longitude: -3.700000",
            severity=Severity.high,
        )
        for index in range(120)
    ]
    async with session_factory() as session:
        await RunRepository(session).create(run)
    async with session_factory() as session:
        await AssetRepository(session).create(asset)
    async with session_factory() as session:
        await FindingRepository(session).create_many(findings)

    client = StubAgentClient()
    summary = await AgentPipeline(session_factory, settings, client=client).execute(run.id)
    assert summary.findings_evaluated == 100
    assert summary.findings_skipped_by_cap == 20
    assert len(client.calls_for("analyze")) == 100


async def test_identical_findings_on_two_assets_call_the_model_once(session_factory) -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key=SecretStr("sk-test"),
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="strong-test-model",
        max_agent_findings=50,
        rate_limit_rps=0.0,
    )
    run = make_run()
    first = make_asset(
        run.id,
        file_hash="ab" * 32,
        source_url="http://target.com/a.jpg",
        final_url="http://target.com/a.jpg",
    )
    second = make_asset(
        run.id,
        file_hash="cd" * 32,
        source_url="http://target.com/b.jpg",
        final_url="http://target.com/b.jpg",
    )
    snippet = "Latitude: 40.416775, Longitude: -3.703790"
    findings = [
        make_finding(run.id, first.id, evidence_snippet=snippet, severity=Severity.high),
        make_finding(run.id, second.id, evidence_snippet=snippet, severity=Severity.high),
    ]
    async with session_factory() as session:
        await RunRepository(session).create(run)
    async with session_factory() as session:
        await AssetRepository(session).create(first)
        await AssetRepository(session).create(second)
    async with session_factory() as session:
        await FindingRepository(session).create_many(findings)

    client = StubAgentClient()
    summary = await AgentPipeline(session_factory, settings, client=client).execute(run.id)
    assert summary.findings_evaluated == 2
    assert len(client.calls_for("analyze")) == 1


async def test_llm_concurrency_of_one_does_not_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    strong = ScriptedChatModel([{"parsed": None}, {"parsed": None}])
    client = LangChainAgentClient(
        strong,
        ScriptedChatModel([]),
        strong_model_name="strong-test-model",
        fast_model_name="fast-test-model",
        rate_limit_rps=0.0,
        llm_concurrency=1,
        retry_policy=RetryPolicy(attempts=1, wait_initial_s=0.0, wait_max_s=0.0),
    )
    current = 0
    peak = 0
    original = ScriptedRunnable.ainvoke

    async def slow(self: ScriptedRunnable, messages: list) -> dict:
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.05)
        try:
            return await original(self, messages)
        finally:
            current -= 1

    monkeypatch.setattr(ScriptedRunnable, "ainvoke", slow)
    # parsed=None raises after two schema attempts; we only care about overlap.
    await asyncio.gather(
        _ignore_unavailable(client),
        _ignore_unavailable(client),
        return_exceptions=True,
    )
    assert peak == 1


async def _ignore_unavailable(client: LangChainAgentClient) -> None:
    from metatracer.core.exceptions import AgentUnavailableError

    try:
        await client.analyze("system", {"finding_type": "gps"})
    except AgentUnavailableError:
        return
