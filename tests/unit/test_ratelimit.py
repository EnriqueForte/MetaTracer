"""Unit tests for the API-edge rate limiter and body guard (v2.3).

Covers the branches the integration tests do not reach: the disabled limiter,
the invalid-config rejection, and the body-guard edge cases (None length,
zero cap). The 429/413 happy paths live in tests/integration/test_api_performance.py.
"""

from types import SimpleNamespace

import pytest
from starlette.exceptions import HTTPException

from metatracer.core.ratelimit import ApiRateLimiter, enforce_body_limit


def _request(host: str = "127.0.0.1", forwarded: str | None = None):
    """Minimal request double with the headers/attributes the limiter reads."""
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    request = SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers=headers,
    )
    return request


@pytest.mark.asyncio
async def test_disabled_limiter_is_noop() -> None:
    limiter = ApiRateLimiter(0)
    assert limiter.enabled is False
    # Many requests, never raises.
    for _ in range(5):
        await limiter.check(_request())


def test_invalid_limit_rejected() -> None:
    with pytest.raises(ValueError):
        ApiRateLimiter(-1)


@pytest.mark.asyncio
async def test_limits_per_forwarded_identity() -> None:
    """The key folds in the peer address, so a spoofed XFF cannot share budget."""
    limiter = ApiRateLimiter(2)
    await limiter.check(_request(host="127.0.0.1", forwarded="10.0.0.1"))
    await limiter.check(_request(host="127.0.0.1", forwarded="10.0.0.1"))
    # Same peer + different XFF is a different bucket: still allowed.
    await limiter.check(_request(host="127.0.0.1", forwarded="10.0.0.2"))
    with pytest.raises(HTTPException) as excinfo:
        await limiter.check(_request(host="127.0.0.1", forwarded="10.0.0.1"))
    assert excinfo.value.status_code == 429
    assert "Retry-After" in (excinfo.value.headers or {})


@pytest.mark.asyncio
async def test_retry_after_is_whole_seconds() -> None:
    limiter = ApiRateLimiter(1)
    await limiter.check(_request())
    with pytest.raises(HTTPException) as excinfo:
        await limiter.check(_request())
    retry = excinfo.value.headers["Retry-After"]
    assert retry.isdigit()
    assert 1 <= int(retry) <= 60


@pytest.mark.asyncio
async def test_sweep_removes_idle_windows() -> None:
    """An idle window is evicted; memory stays bounded by active clients."""
    limiter = ApiRateLimiter(2)
    await limiter.check(_request(host="10.0.0.9"))
    assert len(limiter._states) == 1
    # Force the sweep to consider the entry idle.
    for state in limiter._states.values():
        state.last_seen = 0.0  # long idle
    limiter._last_sweep = 0.0  # force the sweep branch
    # Next check touches a different key and triggers a sweep on arrival.
    await limiter.check(_request(host="10.0.0.8"))
    assert "10.0.0.9" not in limiter._states


def test_body_guard_edge_cases() -> None:
    # No declared length (chunked): no pre-emptive rejection.
    enforce_body_limit(None, 100)  # must not raise
    # Zero/negative cap: guard disabled.
    enforce_body_limit(999, 0)  # must not raise
    enforce_body_limit(999, -5)  # must not raise
    # Over the cap raises 413.
    with pytest.raises(HTTPException) as excinfo:
        enforce_body_limit(101, 100)
    assert excinfo.value.status_code == 413
    # At the cap it passes.
    enforce_body_limit(100, 100)