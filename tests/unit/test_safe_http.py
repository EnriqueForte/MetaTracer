"""safe_httpx_request gateway: scope, confirmation, redirects and size limits.

DNS resolution (socket.getaddrinfo) and the HTTP transport (httpx.MockTransport)
are faked. ScopeValidator and NetworkSafetyGuard are never mocked — every test
exercises the real safety controls.
"""

import asyncio
import socket
from collections.abc import Callable

import httpx
import pytest

from metatracer.core.exceptions import (
    OutOfScopeError,
    RedirectOutOfScopeError,
    ScopeNotConfirmedError,
)
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import DomainRateLimiter, safe_httpx_request
from metatracer.core.safety.scope import ScopeValidator

_PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _PUBLIC_ADDRINFO)


def _install_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def _guard() -> NetworkSafetyGuard:
    return NetworkSafetyGuard(allow_loopback=False)


def _limiter() -> DomainRateLimiter:
    # High RPS keeps tests fast; throttling itself is covered by a dedicated test.
    return DomainRateLimiter(1000.0)


async def test_out_of_scope_url_raises_before_any_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    _install_transport(monkeypatch, handler)
    with pytest.raises(OutOfScopeError):
        await safe_httpx_request(
            "http://other.com/a.pdf",
            scope=ScopeValidator(["target.com"]),
            guard=_guard(),
            rate_limiter=_limiter(),
            scope_confirmed=True,
        )


async def test_unconfirmed_scope_raises_before_any_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    _install_transport(monkeypatch, handler)
    with pytest.raises(ScopeNotConfirmedError):
        await safe_httpx_request(
            "http://target.com/a.pdf",
            scope=ScopeValidator(["target.com"]),
            guard=_guard(),
            rate_limiter=_limiter(),
            scope_confirmed=False,
        )


async def test_redirect_out_of_scope_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "http://evil.com/loot.pdf"})
        return httpx.Response(200, content=b"%PDF")

    _install_transport(monkeypatch, handler)
    with pytest.raises(RedirectOutOfScopeError):
        await safe_httpx_request(
            "http://target.com/redirect",
            scope=ScopeValidator(["target.com"]),
            guard=_guard(),
            rate_limiter=_limiter(),
            scope_confirmed=True,
        )


async def test_in_scope_redirect_chain_is_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7")

    _install_transport(monkeypatch, handler)
    response = await safe_httpx_request(
        "http://target.com/start",
        scope=ScopeValidator(["target.com"]),
        guard=_guard(),
        rate_limiter=_limiter(),
        scope_confirmed=True,
    )
    assert response.status_code == 200
    assert response.url == "http://target.com/final"
    assert response.content == b"%PDF-1.7"
    assert response.redirect_chain == ("http://target.com/start",)
    assert response.too_large is False


async def test_head_probe_declared_too_large_skips_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_called
        if request.method == "GET":
            get_called = True
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf", "content-length": str(60 * 1024 * 1024)},
            content=b"x" * 10,
        )

    _install_transport(monkeypatch, handler)
    response = await safe_httpx_request(
        "http://target.com/big.pdf",
        scope=ScopeValidator(["target.com"]),
        guard=_guard(),
        rate_limiter=_limiter(),
        scope_confirmed=True,
        max_file_bytes=1024,
    )
    assert response.too_large is True
    assert response.content == b""
    assert get_called is False  # the HEAD-declared length was enough to abort


async def test_streaming_get_aborts_when_body_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 4096)  # no Content-Length declared

    _install_transport(monkeypatch, handler)
    response = await safe_httpx_request(
        "http://target.com/stream.pdf",
        scope=ScopeValidator(["target.com"]),
        guard=_guard(),
        rate_limiter=_limiter(),
        scope_confirmed=True,
        max_file_bytes=1024,
    )
    assert response.too_large is True
    assert response.content == b""


async def test_head_not_allowed_falls_back_to_get(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xff")

    _install_transport(monkeypatch, handler)
    response = await safe_httpx_request(
        "http://target.com/photo.jpg",
        scope=ScopeValidator(["target.com"]),
        guard=_guard(),
        rate_limiter=_limiter(),
        scope_confirmed=True,
    )
    assert response.status_code == 200
    assert response.content == b"\xff\xd8\xff"
    assert response.content_type == "image/jpeg"


async def test_rate_limiter_spaces_requests_to_same_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    async def fake_sleep(duration: float) -> None:
        waits.append(duration)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    limiter = DomainRateLimiter(2.0)  # one slot every 0.5 s
    await limiter.acquire("target.com")  # first slot is free
    await limiter.acquire("target.com")  # second one must wait ~0.5 s
    await limiter.acquire("other.com")  # a different domain is not throttled
    assert len(waits) == 1
    assert 0.4 < waits[0] <= 0.5
