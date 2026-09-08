"""Redirect scope enforcement (TASK-01 subtask 1.2.1, tasks README trap #1/#4).

An out-of-scope redirect hop raises RedirectOutOfScopeError before the body is
read; an in-scope hop that resolves to a private address is blocked by the
guard; redirect loops die at the 5-hop limit. DNS and transport are faked;
ScopeValidator and NetworkSafetyGuard are the real ones.
"""

import socket

import httpx
import pytest

from metatracer.core.exceptions import (
    MetaTracerError,
    RedirectOutOfScopeError,
    SecurityViolationError,
)
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import DomainRateLimiter, safe_httpx_request
from metatracer.core.safety.scope import ScopeValidator
from tests.conftest import PUBLIC_ADDRINFO


def _gateway(url: str):
    return safe_httpx_request(
        url,
        scope=ScopeValidator(["target.com"]),
        guard=NetworkSafetyGuard(allow_loopback=False),
        rate_limiter=DomainRateLimiter(1000.0),
        scope_confirmed=True,
    )


async def test_redirect_off_scope_never_touches_the_host(
    fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "evil.com":
            raise AssertionError("the off-scope host was requested")
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://evil.com/loot.pdf"})
        return httpx.Response(200, content=b"%PDF-1.7")

    install_transport(handler)
    with pytest.raises(RedirectOutOfScopeError):
        await _gateway("http://target.com/start")
    # Neither the HEAD probe nor the GET ever reached the off-scope host, and
    # the redirecting body was never read.
    assert requested
    assert all("evil.com" not in url for url in requested)


async def test_redirect_to_private_address_blocked_by_guard(
    monkeypatch: pytest.MonkeyPatch, install_transport
) -> None:
    """In-scope host that resolves to RFC1918: blocked before the socket."""

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "internal.target.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 443))]
        return PUBLIC_ADDRINFO

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "internal.target.com":
            raise AssertionError("a private address was contacted")
        return httpx.Response(302, headers={"location": "http://internal.target.com/x.pdf"})

    install_transport(handler)
    with pytest.raises(SecurityViolationError):
        await _gateway("http://target.com/start")


async def test_redirect_loop_dies_at_the_hop_limit(fake_public_dns, install_transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    install_transport(handler)
    with pytest.raises(MetaTracerError, match="redirect limit"):
        await _gateway("http://target.com/loop")
