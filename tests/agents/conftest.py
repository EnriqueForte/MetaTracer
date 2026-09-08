"""Shared plumbing for TASK-05 agent tests.

No test ever calls a real LLM API: the graph consumes a ``StubAgentClient``
implementing the ``AgentClient`` protocol, and the client-level retry tests
use a ``ScriptedChatModel`` stub that mimics ``with_structured_output``.
The database fixtures use a real (temporary-file) SQLite engine — only the
model is faked.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.agents.llm import LLMResult, LLMUsage
from metatracer.agents.schemas import AgentFindingAnalysis, FindingTitle, ReportSummary
from metatracer.core.config import Settings
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


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/metatracer-agents-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture()
def settings() -> Settings:
    """Configured-but-unreachable settings; tests never perform real calls."""
    return Settings(
        llm_api_key=SecretStr("sk-test-not-a-real-key"),
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="strong-test-model",
        fast_model="fast-test-model",
        max_assets_per_run=50,
        rate_limit_rps=0.0,  # no pacing sleep in tests
    )


def make_run(**kwargs: Any) -> Run:
    defaults: dict[str, Any] = {
        "target_input": '["http://target.com"]',
        "allowed_scope": '["target.com"]',
        "scope_confirmed": True,
    }
    defaults.update(kwargs)
    return Run(**defaults)


def make_asset(run_id: str, file_hash: str = "cd" * 32, **kwargs: Any) -> Asset:
    defaults: dict[str, Any] = {
        "run_id": run_id,
        "source_url": "http://target.com/a.pdf",
        "final_url": "http://target.com/a.pdf",
        "content_type": "application/pdf",
        "file_hash_sha256": file_hash,
        "file_size_bytes": 128,
        "extraction_status": ExtractionStatus.ok,
    }
    defaults.update(kwargs)
    return Asset(**defaults)


def make_finding(
    run_id: str,
    asset_id: str,
    *,
    finding_type: FindingType = FindingType.gps,
    field_source: str = "EXIF:GPSInfo",
    evidence_snippet: str = "Latitude: 40.416775, Longitude: -3.703790",
    dedup_signature: str | None = None,
    severity: Severity | None = None,
    confidence: Confidence = Confidence.high,
    **kwargs: Any,
) -> Finding:
    return Finding(
        run_id=run_id,
        asset_id=asset_id,
        finding_type=finding_type,
        field_source=field_source,
        evidence_snippet=evidence_snippet,
        dedup_signature=dedup_signature or f"sig-{uuid.uuid4().hex}",
        detector_method=DetectorMethod.rule,
        confidence=confidence,
        severity=severity,
        **kwargs,
    )


def default_analysis(severity: Severity = Severity.high) -> AgentFindingAnalysis:
    """Schema-valid analysis whose citation is a real snippet substring."""
    return AgentFindingAnalysis(
        severity=severity,
        justification="The snippet shows precise coordinates embedded by the device.",
        impact_analysis="Precise location exposure aids physical reconnaissance.",
        remediation="Strip location metadata before publication.",
        reproduction_steps=[
            "Fetch the public asset and save it locally.",
            "Run `exiftool` on the file and confirm the GPS fields.",
        ],
        cited_evidence="Latitude: 40.416775, Longitude: -3.703790",
    )


def _adaptive_analysis(payload: dict[str, Any]) -> AgentFindingAnalysis:
    """Guard-clean default: cite the snippet verbatim, keep the baseline level."""
    snippet = str(payload.get("evidence_snippet", ""))
    severity = Severity(str(payload.get("heuristic_severity", "low")))
    return AgentFindingAnalysis(
        severity=severity,
        justification="The evidence is present verbatim in the asset metadata.",
        impact_analysis="Exposure of this metadata aids targeted reconnaissance.",
        remediation="Scrub the metadata field before publication.",
        reproduction_steps=[
            "Fetch the public asset and save it locally.",
            "Run `exiftool` on the file and confirm the field.",
        ],
        cited_evidence=snippet,
    )


class StubAgentClient:
    """AgentClient stub: canned schema-valid responses, records every call.

    ``analyze_error`` / ``title_error`` / ``summary_error`` simulate a dead or
    unconfigured model (post-retry ``AgentUnavailableError``, exactly what the
    real client raises after tenacity gives up).
    """

    available: bool = True

    def __init__(
        self,
        *,
        analysis: AgentFindingAnalysis | None = None,
        analyze_error: Exception | None = None,
        title: str = "Embedded GPS coordinates in EXIF:GPSInfo",
        title_error: Exception | None = None,
        summary: str = "Three findings were reviewed; one needs urgent scrubbing.",
        summary_error: Exception | None = None,
    ) -> None:
        self._analysis = analysis
        self._analyze_error = analyze_error
        self._title = title
        self._title_error = title_error
        self._summary = summary
        self._summary_error = summary_error
        self.calls: list[dict[str, Any]] = []

    async def analyze(self, system_prompt: str, payload: dict[str, Any]) -> LLMResult:
        self.calls.append({"method": "analyze", "system": system_prompt, "payload": payload})
        if self._analyze_error is not None:
            raise self._analyze_error
        analysis = self._analysis or _adaptive_analysis(payload)
        return LLMResult(
            value=analysis, usage=LLMUsage(prompt_tokens=120, completion_tokens=40, latency_ms=5)
        )

    async def draft_title(self, system_prompt: str, payload: dict[str, Any]) -> LLMResult:
        self.calls.append({"method": "draft_title", "system": system_prompt, "payload": payload})
        if self._title_error is not None:
            raise self._title_error
        return LLMResult(
            value=FindingTitle(title=self._title),
            usage=LLMUsage(prompt_tokens=30, completion_tokens=8, latency_ms=2),
        )

    async def summarize(self, system_prompt: str, payload: dict[str, Any]) -> LLMResult:
        self.calls.append({"method": "summarize", "system": system_prompt, "payload": payload})
        if self._summary_error is not None:
            raise self._summary_error
        return LLMResult(
            value=ReportSummary(executive_summary=self._summary),
            usage=LLMUsage(prompt_tokens=60, completion_tokens=25, latency_ms=3),
        )

    def calls_for(self, method: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["method"] == method]


class ListWriter:
    """In-memory EvaluationWriter: records the exact entries the graph saves."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def save_evaluation(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)


class ListSink:
    """In-memory SummarySink."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def set_summary(self, text: str) -> None:
        self.texts.append(text)


class ScriptedChatModel:
    """Chat-model stub exposing ``with_structured_output`` (langchain-core 1.x
    fake models do not implement it, so the client is exercised against this
    scriptable stand-in).

    ``outcomes`` is a queue: each ``ainvoke`` pops the next outcome, which is
    either an exception to raise (e.g. an openai 500) or a dict with ``parsed``
    (a validated schema instance or None) and optional ``parsing_error``.
    """

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.invocations: int = 0

    def with_structured_output(self, schema: Any, **kwargs: Any) -> "ScriptedRunnable":
        return ScriptedRunnable(self, schema)


class ScriptedRunnable:
    def __init__(self, model: ScriptedChatModel, schema: Any) -> None:
        self._model = model
        self._schema = schema

    async def ainvoke(self, messages: list[Any]) -> dict[str, Any]:
        self._model.invocations += 1
        if not self._model.outcomes:
            raise AssertionError("ScriptedChatModel ran out of outcomes")
        outcome = self._model.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        parsed = outcome.get("parsed")
        return {
            "raw": None,
            "parsed": parsed,
            "parsing_error": outcome.get("parsing_error"),
        }
