"""API-edge rate limiter and body-size guard (v2.3 performance slice).

Two controls that protect the HTTP API itself (as opposed to the outbound
ingestion pipeline, which has its own ``DomainRateLimiter`` in
``metatracer.core.safety.http``):

1. :class:`ApiRateLimiter` — fixed-window per-client-IP limiting
   (sliding-window is unnecessary for a localhost-first tool; a fixed minute
   window is simple and predictable). The limiter is **pure stdlib**: no new
   dependency enters the closed supply chain, and the algorithm is
   deliberately small enough to audit in one sitting (threat 15).

2. :func:`enforce_body_limit` — cheap exact check that a request body fits
   the configured cap before anything reads it. It never buffers the body
   itself; callers that use ``await request.body()`` afterwards are still
   bounded by this pre-check (the middleware runs first).

Design notes:

- ``Retry-After`` on the 429 is in whole seconds, always >= 1, so a compliant
  client can pace itself without clock math.
- A malformed X-Forwarded-For (e.g. a proxy spoofing client IPs) can only make
  the limiter **more** conservative per distinct value; it can never widen an
  attacker's budget, because the key includes the raw peer address.
- The limiter is per-process and in-memory by design: the API is single-node
  (SQLite single writer), so a shared counter adds nothing but complexity.
- ``last_seen`` on each window is refreshed on every request so idle windows
  are evicted and memory stays bounded by active clients.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import Request
from starlette.exceptions import HTTPException

WINDOW_SECONDS = 60.0
# Sweep cadence for idle-window eviction (bounded memory under sustained load).
_SWEEP_EVERY_SECONDS = 60.0

# Client identity: X-Forwarded-For leftmost value + peer address. The value is
# used only as a map key and is never logged or rendered.
def client_key(request: Request) -> str:
    """Best-effort caller identity, defensive against absent/malformed headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        leftmost = forwarded.split(",", 1)[0].strip()
        if leftmost:
            return f"{request.client.host}|{leftmost}" if request.client else leftmost
    peer = request.client.host if request.client else "unknown"
    return str(peer)


@dataclass(slots=True)
class _WindowState:
    """One client's current fixed window: arrival wall-clock timestamps."""

    starts: deque[float] = field(default_factory=deque)
    last_seen: float = field(default_factory=time.monotonic)


class ApiRateLimiter:
    """Fixed-window per-client rate limiter with idle-window eviction.

    ``limit_per_minute > 0`` requests per minute per :func:`client_key`.
    ``limit_per_minute == 0`` disables limiting entirely (a no-op), which is
    the escape hatch for reverse-proxy deployments that already limit.
    """

    def __init__(self, limit_per_minute: int) -> None:
        if limit_per_minute < 0:
            raise ValueError("api_rate_limit_per_minute must be >= 0")
        self._limit = limit_per_minute
        self._states: dict[str, _WindowState] = {}
        self._lock = asyncio.Lock()
        self._last_sweep = time.monotonic()

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    async def check(self, request: Request) -> None:
        """Raise a 429 :class:`HTTPException` when the client is over limit.

        Side-effect free when disabled. The idle-window sweep runs at most
        once per ``_SWEEP_EVERY_SECONDS`` to keep memory bounded.
        """
        if not self.enabled:
            return
        key = client_key(request)
        now = time.monotonic()
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                state = self._states[key] = _WindowState()
            # Drop arrivals older than the window and refresh liveness.
            cutoff = now - WINDOW_SECONDS
            while state.starts and state.starts[0] <= cutoff:
                state.starts.popleft()
            state.last_seen = now
            if len(state.starts) >= self._limit:
                # The requester is already at the cap: answer 429. The sleep
                # yields to other coroutines (e.g. a scan's SSE or polling)
                # before the error is sent — never a busy-wait.
                await asyncio.sleep(0)
                retry = self._retry_seconds_for(state)
                raise HTTPException(
                    status_code=429,
                    detail="rate limit exceeded: too many requests from this client",
                    headers={"Retry-After": str(max(1, retry))},
                )
            state.starts.append(now)
            if now - self._last_sweep >= _SWEEP_EVERY_SECONDS:
                self._last_sweep = now
                idle_cutoff = now - WINDOW_SECONDS
                for stale in [k for k, s in self._states.items() if s.last_seen < idle_cutoff]:
                    del self._states[stale]

    def _retry_seconds_for(self, state: _WindowState) -> int:
        """Whole seconds until the *this client's* window rolls over.

        ``ceil`` of the remaining time: a request that expires in 59.2 s
        reports 60 s (never 59), and the absolute floor is 1 s.
        """
        if not state.starts:
            return 1
        oldest = state.starts[0]
        remaining = WINDOW_SECONDS - (time.monotonic() - oldest)
        return max(1, int(-(-remaining // 1)))  # ceil


def enforce_body_limit(length: int | None, max_bytes: int) -> None:
    """Raise a 413 when a declared Content-Length exceeds ``max_bytes``.

    ``length is None`` (chunked transfer) cannot be pre-empted; the caller is
    responsible for bounding the chunked path (the DB-backed endpoints
    already stream to temp files).
    """
    if max_bytes <= 0:
        return
    if length is not None and length > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"request body too large: {length} bytes exceeds the "
            f"{max_bytes} byte limit",
        )