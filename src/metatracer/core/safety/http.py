"""The single HTTP gateway of MetaTracer.

Every network request in the project — crawler, downloaders, anything — goes
through :func:`safe_httpx_request`, which enforces, in order:

1. ``scope_confirmed`` must be True (ScopeNotConfirmedError otherwise);
2. the URL host must be inside the confirmed scope (OutOfScopeError), checked
   before any socket is opened;
3. the anti-SSRF guard runs immediately before every connection;
4. redirects are followed manually (httpx follow_redirects=False), at most 5
   hops, re-validating scope and guard on every hop — an out-of-scope hop
   raises RedirectOutOfScopeError before the body is read;
5. GET downloads stream the body and abort as soon as max_file_bytes is
   exceeded (``too_large=True``, no partial bytes kept);
6. the client is created with ``trust_env=False`` so ``HTTP_PROXY`` /
   ``HTTPS_PROXY`` / ``ALL_PROXY`` cannot move the socket to an address the
   guard never checks (TASK-27).

GET requests are preceded by a HEAD probe for Content-Length/Content-Type.
HEAD follows redirects (each hop validated). The GET then starts at that
already-validated final URL, so the chain is not walked a second time.
When HEAD is not allowed (405/501) or fails at transport level, the wrapper
falls back to a streaming GET from the original URL. Residual cost: one HEAD
per redirect hop plus one GET of the final resource (TASK-32, R3/R8).

Timeouts: connect 10 s, read 20 s, pool 10 s (TASK-00); the write timeout is
unspecified there and is set equal to the connect timeout.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

from metatracer.core.exceptions import (
    MetaTracerError,
    OutOfScopeError,
    RedirectOutOfScopeError,
    ScopeNotConfirmedError,
    SecurityViolationError,
)
from metatracer.core.logging import sanitize_for_log
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.scope import ScopeValidator

logger = logging.getLogger("metatracer.safety.http")

USER_AGENT = "MetaTracer/1.0 (authorized security audit; +https://github.com/your-org/metatracer)"
MAX_REDIRECT_HOPS = 5
# Transport-level failure raised by the gateway (timeouts, connection errors,
# protocol errors). Re-exported so callers can catch it WITHOUT importing httpx:
# this module is the only place in the project that touches the HTTP library.
HttpTransportError = httpx.HTTPError
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MiB, mirrors Settings.max_file_bytes
DEFAULT_RATE_LIMIT_RPS = 2.0
MAX_CONCURRENT_DOWNLOADS = 3
_CHUNK_SIZE = 64 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_HEAD_NOT_ALLOWED = frozenset({405, 501})


@dataclass(frozen=True, slots=True)
class SafeHttpResponse:
    """Result of a request through the safety gateway.

    ``content`` holds the body in memory only (this layer never persists it);
    it is empty for HEAD responses, redirects and downloads aborted by size.
    """

    url: str  # final URL after any in-scope redirects
    status_code: int
    headers: dict[str, str]  # lower-cased header names
    content: bytes
    too_large: bool
    redirect_chain: tuple[str, ...]

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")


@dataclass(slots=True)
class _DomainState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_slot: float = 0.0


class DomainRateLimiter:
    """Per-domain rate limiter: at most ``requests_per_second`` to the same domain.

    Share a single instance across all requests of a run — per-call instances
    cannot enforce anything across calls.
    """

    def __init__(self, requests_per_second: float = DEFAULT_RATE_LIMIT_RPS) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._interval = 1.0 / requests_per_second
        self._states: dict[str, _DomainState] = {}
        self._states_lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        """Wait until the domain's next request slot, then reserve it."""
        async with self._states_lock:
            state = self._states.setdefault(domain, _DomainState())
        async with state.lock:
            now = time.monotonic()
            wait = state.next_slot - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            state.next_slot = now + self._interval


async def safe_httpx_request(
    url: str,
    *,
    scope: ScopeValidator,
    guard: NetworkSafetyGuard,
    scope_confirmed: bool,
    rate_limiter: DomainRateLimiter,
    method: Literal["GET", "HEAD"] = "GET",
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    download_semaphore: asyncio.Semaphore | None = None,
) -> SafeHttpResponse:
    """Perform an HTTP request through every safety control.

    ``scope``, ``guard``, ``scope_confirmed`` and ``rate_limiter`` are mandatory
    keyword arguments so a caller cannot forget them: a request never leaves
    this gateway unthrottled. Share a single ``DomainRateLimiter`` across all
    requests of a run. Pass a shared ``download_semaphore`` (e.g.
    ``asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)``) to bound concurrent
    downloads run-wide; without one, only this call's own requests are bounded.

    httpx transport errors (timeouts, connect errors) propagate to the caller,
    which must handle them per asset so a single failure never aborts the run.
    """
    if not scope_confirmed:
        raise ScopeNotConfirmedError(
            "network requests require an explicitly confirmed scope (scope_confirmed=True)"
        )
    semaphore = (
        download_semaphore
        if download_semaphore is not None
        else asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    )
    if method == "HEAD":
        return await _request_with_redirects(
            "HEAD",
            url,
            scope=scope,
            guard=guard,
            max_file_bytes=max_file_bytes,
            rate_limiter=rate_limiter,
            semaphore=semaphore,
        )
    probe = await _head_probe(
        url,
        scope=scope,
        guard=guard,
        max_file_bytes=max_file_bytes,
        rate_limiter=rate_limiter,
        semaphore=semaphore,
    )
    if probe is not None:
        declared = _declared_length(probe)
        if declared is not None and declared > max_file_bytes:
            return SafeHttpResponse(
                url=probe.url,
                status_code=probe.status_code,
                headers=probe.headers,
                content=b"",
                too_large=True,
                redirect_chain=probe.redirect_chain,
            )
        # GET the URL the HEAD already validated. A further redirect on the
        # GET is still checked; the HEAD chain is not requested again.
        fetched = await _request_with_redirects(
            "GET",
            probe.url,
            scope=scope,
            guard=guard,
            max_file_bytes=max_file_bytes,
            rate_limiter=rate_limiter,
            semaphore=semaphore,
        )
        return SafeHttpResponse(
            url=fetched.url,
            status_code=fetched.status_code,
            headers=fetched.headers,
            content=fetched.content,
            too_large=fetched.too_large,
            redirect_chain=probe.redirect_chain + fetched.redirect_chain,
        )
    return await _request_with_redirects(
        "GET",
        url,
        scope=scope,
        guard=guard,
        max_file_bytes=max_file_bytes,
        rate_limiter=rate_limiter,
        semaphore=semaphore,
    )


async def _head_probe(
    url: str,
    *,
    scope: ScopeValidator,
    guard: NetworkSafetyGuard,
    max_file_bytes: int,
    rate_limiter: DomainRateLimiter,
    semaphore: asyncio.Semaphore,
) -> SafeHttpResponse | None:
    """Cheap HEAD probe for size/type discovery; None means 'fall back to GET'.

    Safety errors (scope, guard) are MetaTracerError subclasses and propagate;
    only transport failures and 405/501 trigger the GET fallback.
    """
    try:
        probe = await _request_with_redirects(
            "HEAD",
            url,
            scope=scope,
            guard=guard,
            max_file_bytes=max_file_bytes,
            rate_limiter=rate_limiter,
            semaphore=semaphore,
        )
    except httpx.HTTPError:
        return None
    if probe.status_code in _HEAD_NOT_ALLOWED:
        return None
    return probe


def _declared_length(response: SafeHttpResponse) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


async def _request_with_redirects(
    method: Literal["GET", "HEAD"],
    url: str,
    *,
    scope: ScopeValidator,
    guard: NetworkSafetyGuard,
    max_file_bytes: int,
    rate_limiter: DomainRateLimiter,
    semaphore: asyncio.Semaphore,
) -> SafeHttpResponse:
    scope.validate(url)  # initial URL: plain OutOfScopeError, before any socket exists
    timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)
    redirect_chain: list[str] = []
    current_url = url
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        # Default trust_env=True would honour HTTP(S)_PROXY and connect to a
        # proxy the guard never validated (TASK-27, P0-1).
        trust_env=False,
    ) as client:
        for _hop in range(MAX_REDIRECT_HOPS + 1):
            # current_url is always in scope here: the initial URL was validated
            # above and every redirect target is validated before becoming current.
            host, port = _host_and_port(current_url)
            await rate_limiter.acquire(host)
            async with semaphore:
                await guard.check(host, port)  # immediately before the socket
                raw = await _single_request(client, method, current_url, max_file_bytes)
            if raw.status_code not in _REDIRECT_STATUSES:
                return SafeHttpResponse(
                    url=current_url,
                    status_code=raw.status_code,
                    headers=raw.headers,
                    content=raw.content,
                    too_large=raw.too_large,
                    redirect_chain=tuple(redirect_chain),
                )
            location = raw.headers.get("location")
            if not location:  # redirect status without Location: treat as final
                return SafeHttpResponse(
                    url=current_url,
                    status_code=raw.status_code,
                    headers=raw.headers,
                    content=raw.content,
                    too_large=raw.too_large,
                    redirect_chain=tuple(redirect_chain),
                )
            next_url = urljoin(current_url, location)
            try:
                scope.validate(next_url)
            except OutOfScopeError as exc:
                raise RedirectOutOfScopeError(
                    "redirect hop left the confirmed scope: "
                    f"{sanitize_for_log(current_url)} -> {sanitize_for_log(next_url)}"
                ) from exc
            logger.debug(
                "following redirect %s -> %s",
                sanitize_for_log(current_url),
                sanitize_for_log(next_url),
            )
            redirect_chain.append(current_url)
            current_url = next_url
        raise MetaTracerError(
            f"redirect limit exceeded: more than {MAX_REDIRECT_HOPS} hops "
            f"from {sanitize_for_log(url)}"
        )


@dataclass(slots=True)
class _RawResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    too_large: bool


async def _single_request(
    client: httpx.AsyncClient, method: str, url: str, max_file_bytes: int
) -> _RawResponse:
    async with client.stream(method, url) as response:
        headers = {name.lower(): value for name, value in response.headers.items()}
        if method == "HEAD" or response.status_code in _REDIRECT_STATUSES:
            # Redirect bodies are never read: the hop is validated before any read.
            return _RawResponse(response.status_code, headers, b"", False)
        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_file_bytes:
            return _RawResponse(response.status_code, headers, b"", True)
        chunks: list[bytes] = []
        received = 0
        async for chunk in response.aiter_bytes(_CHUNK_SIZE):
            received += len(chunk)
            if received > max_file_bytes:
                # Abort without keeping partial bytes; the caller marks the asset.
                return _RawResponse(response.status_code, headers, b"", True)
            chunks.append(chunk)
        return _RawResponse(response.status_code, headers, b"".join(chunks), False)


def _host_and_port(url: str) -> tuple[str, int]:
    """Extract (host, port); non-HTTP(S) schemes and broken URLs fail closed."""
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            raise SecurityViolationError(
                f"unsupported URL scheme blocked: {sanitize_for_log(parsed.scheme)}"
            )
        host = parsed.hostname
        if not host:
            raise OutOfScopeError("URL without a host cannot be checked against the scope")
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise SecurityViolationError(f"unparseable URL blocked: {sanitize_for_log(url)}") from exc
    return host.lower(), port
