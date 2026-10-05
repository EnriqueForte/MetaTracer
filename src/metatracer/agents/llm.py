"""LLM client for the agent layer (TASK-05, subtasks 5.2.2 and 5.4).

Routing: the strong model (``settings.llm_model``) produces per-finding
analysis + severity; the fast model (``settings.fast_model``) drafts titles
and the executive summary. Both are ``ChatOpenAI`` instances pointed at
``settings.llm_base_url`` (OpenAI-compatible API); the key leaves
``SecretStr`` only at client construction and is never logged or persisted.

Resilience contract:

- Transport-level failures (HTTP 429/5xx, timeouts, connection errors) are
  retried with tenacity: 3 attempts, exponential backoff with jitter.
- A schema-invalid structured output is retried ONCE (subtask 5.2.1), then
  the call fails with :class:`AgentUnavailableError`.
- Every failure mode surfaces as :class:`AgentUnavailableError`; the graph
  converts it into the heuristic fallback. A model failure never aborts a run.
- A conservative minimum interval between calls derives from
  ``settings.rate_limit_rps`` (subtask 5.4.3).

``openai`` is imported for its exception hierarchy: it is a hard dependency
of the approved ``langchain-openai`` package, not a new dependency.
"""

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from metatracer.agents.schemas import AgentFindingAnalysis, FindingTitle, ReportSummary
from metatracer.core.config import Settings
from metatracer.core.exceptions import AgentUnavailableError
from metatracer.core.logging import sanitize_for_log

logger = logging.getLogger("metatracer.agents.llm")

# HTTP statuses worth retrying (429 and 5xx plus a few transients).
_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

# function_calling is the most widely supported structured-output method on
# OpenAI-compatible endpoints (json_schema is rejected by several providers).
_STRUCTURED_METHOD = "function_calling"

T = TypeVar("T", bound=BaseModel)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    """429/5xx/timeouts/connection errors are retryable (subtask 5.4.1)."""
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code in _RETRYABLE_STATUS


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Tenacity knobs; tests use zero waits to stay fast and deterministic."""

    attempts: int = 3
    wait_initial_s: float = 1.0
    wait_max_s: float = 8.0


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Per-call accounting persisted in AgentLog (never keys, never prompts)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    model_name: str = ""

    def plus(self, other: "LLMUsage") -> "LLMUsage":
        """Aggregate several calls of one finding into a single AgentLog row."""
        return LLMUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            latency_ms=self.latency_ms + other.latency_ms,
            model_name=self.model_name or other.model_name,
        )


@dataclass(frozen=True, slots=True)
class LLMResult(Generic[T]):
    value: T
    usage: LLMUsage


@runtime_checkable
class StructuredChatModel(Protocol):
    """The slice of BaseChatModel the client needs (duck-typed for test stubs)."""

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class AgentClient(Protocol):
    """Client contract consumed by the graph nodes."""

    available: bool

    async def analyze(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[AgentFindingAnalysis]: ...

    async def draft_title(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[FindingTitle]: ...

    async def summarize(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[ReportSummary]: ...


class LangChainAgentClient:
    """Real client: two routed chat models + structured output + retries."""

    def __init__(
        self,
        strong_llm: StructuredChatModel,
        fast_llm: StructuredChatModel,
        *,
        strong_model_name: str,
        fast_model_name: str,
        rate_limit_rps: float = 2.0,
        llm_concurrency: int = 1,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._strong = strong_llm
        self._fast = fast_llm
        self._strong_name = strong_model_name
        self._fast_name = fast_model_name
        self._retry_policy = retry_policy or RetryPolicy()
        self._min_interval_s = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0.0
        # Caps in-flight model calls. Default 1 keeps the sequential pace.
        # The per-call interval in ``_pace`` still applies inside the slot.
        slots = llm_concurrency if llm_concurrency >= 1 else 1
        self._slots = asyncio.Semaphore(slots)

    available: bool = True

    async def analyze(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[AgentFindingAnalysis]:
        return await self._structured(
            self._strong, self._strong_name, AgentFindingAnalysis, system_prompt, payload
        )

    async def draft_title(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[FindingTitle]:
        return await self._structured(
            self._fast, self._fast_name, FindingTitle, system_prompt, payload
        )

    async def summarize(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[ReportSummary]:
        return await self._structured(
            self._fast, self._fast_name, ReportSummary, system_prompt, payload
        )

    async def _structured(
        self,
        llm: StructuredChatModel,
        model_name: str,
        schema: type[T],
        system_prompt: str,
        payload: dict[str, Any],
    ) -> LLMResult[T]:
        async with self._slots:
            return await self._structured_in_slot(
                llm, model_name, schema, system_prompt, payload
            )

    async def _structured_in_slot(
        self,
        llm: StructuredChatModel,
        model_name: str,
        schema: type[T],
        system_prompt: str,
        payload: dict[str, Any],
    ) -> LLMResult[T]:
        messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        parse_error: BaseException | None = None
        try:
            # Built inside the try so a construction failure also maps to
            # AgentUnavailableError (a model failure never aborts a run).
            runnable = llm.with_structured_output(
                schema, method=_STRUCTURED_METHOD, include_raw=True
            )
            # Schema violations get exactly one retry (subtask 5.2.1).
            for parse_attempt in (1, 2):
                started = time.perf_counter()
                output = await self._invoke_retrying(runnable, messages)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if output.get("parsed") is not None:
                    usage = self._usage_from(output.get("raw"), model_name, latency_ms)
                    return LLMResult(value=output["parsed"], usage=usage)
                parse_error = output.get("parsing_error")
                logger.warning(
                    "structured output violated the schema (attempt %d/2, model=%s)",
                    parse_attempt,
                    sanitize_for_log(model_name),
                )
        except AgentUnavailableError:
            raise  # already the mapped type from _invoke_retrying
        except Exception as exc:
            raise AgentUnavailableError(
                f"structured output setup failed: {sanitize_for_log(exc)}"
            ) from exc
        finally:
            await self._pace()
        raise AgentUnavailableError(
            f"model {sanitize_for_log(model_name)} returned schema-invalid output twice"
        ) from parse_error

    async def _invoke_retrying(self, runnable: Any, messages: Sequence[BaseMessage]) -> Any:
        """One logical call with tenacity retries on transient API errors."""
        policy = self._retry_policy
        retryer = AsyncRetrying(
            stop=stop_after_attempt(policy.attempts),
            wait=wait_exponential_jitter(initial=policy.wait_initial_s, max=policy.wait_max_s),
            retry=retry_if_exception(_is_retryable_llm_error),
            reraise=True,
        )
        try:
            async for attempt in retryer:
                with attempt:
                    return await runnable.ainvoke(list(messages))
        except Exception as exc:
            # Retry-exhausted or non-retryable API failure: the caller maps it
            # to the heuristic fallback. Never log exception reprs raw — the
            # message is sanitized and the API key never appears (SecretStr
            # stays inside the client, and auth headers are not part of the
            # openai exception message).
            raise AgentUnavailableError(
                f"model call failed: {sanitize_for_log(exc)}"
            ) from exc
        raise AgentUnavailableError("model call failed without a result")  # pragma: no cover

    @staticmethod
    def _usage_from(raw: Any, model_name: str, latency_ms: int) -> LLMUsage:
        """Token accounting from the raw AIMessage; zeros when unreported."""
        prompt_tokens = completion_tokens = 0
        usage = getattr(raw, "usage_metadata", None) or {}
        prompt_tokens = int(usage.get("input_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or 0)
        if not prompt_tokens and not completion_tokens:
            legacy = getattr(raw, "response_metadata", {}).get("token_usage", {}) or {}
            prompt_tokens = int(legacy.get("prompt_tokens", 0) or 0)
            completion_tokens = int(legacy.get("completion_tokens", 0) or 0)
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            model_name=model_name,
        )

    async def _pace(self) -> None:
        """Conservative spacing between LLM calls (subtask 5.4.3)."""
        if self._min_interval_s > 0:
            await asyncio.sleep(self._min_interval_s)


class NullAgentClient:
    """Client used when the LLM is not configured: every call falls back."""

    available: bool = False

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def analyze(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[AgentFindingAnalysis]:
        raise AgentUnavailableError(self._reason)

    async def draft_title(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[FindingTitle]:
        raise AgentUnavailableError(self._reason)

    async def summarize(
        self, system_prompt: str, payload: dict[str, Any]
    ) -> LLMResult[ReportSummary]:
        raise AgentUnavailableError(self._reason)


def build_default_client(
    settings: Settings, retry_policy: RetryPolicy | None = None
) -> AgentClient:
    """Route to the real client, or to the null one when not configured.

    An empty API key, base URL or model name never raises: the whole run
    degrades to the heuristic fallback (subtask 5.4.2).
    """
    api_key = settings.llm_api_key.get_secret_value()
    if not api_key or not settings.llm_base_url or not settings.llm_model:
        logger.warning("LLM not configured (key/base_url/model missing); heuristic fallback only")
        return NullAgentClient("LLM not configured: missing API key, base URL or model name")

    from langchain_openai import ChatOpenAI  # deferred: keeps test imports light

    common: dict[str, Any] = {
        "base_url": settings.llm_base_url,
        "api_key": api_key,
        "temperature": 0.0,
        "max_retries": 0,  # tenacity owns the retry policy
        "timeout": 60.0,
        # Threat 9 (denial of wallet): the 5.1.3 budget caps the INPUT; this
        # caps the OUTPUT so a runaway endpoint cannot inflate cost or SQLite.
        "max_tokens": 2000,
    }
    strong = ChatOpenAI(model=settings.llm_model, **common)
    fast = ChatOpenAI(model=settings.fast_model or settings.llm_model, **common)
    return LangChainAgentClient(
        strong,
        fast,
        strong_model_name=settings.llm_model,
        fast_model_name=settings.fast_model or settings.llm_model,
        rate_limit_rps=settings.rate_limit_rps,
        llm_concurrency=settings.llm_concurrency,
        retry_policy=retry_policy,
    )
