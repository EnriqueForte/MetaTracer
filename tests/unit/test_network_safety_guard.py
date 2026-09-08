"""NetworkSafetyGuard tests.

DNS resolution (socket.getaddrinfo) is mocked — that is legitimate. What is
never mocked is the guard itself: every test exercises the real check logic.
"""

import socket
from collections.abc import Callable

import pytest

from metatracer.core.exceptions import SecurityViolationError
from metatracer.core.safety.guard import NetworkSafetyGuard

_PUBLIC_IP = "93.184.216.34"


def _fake_getaddrinfo(*ips: str) -> Callable:
    def fake(host, port, family=0, socktype=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    return fake


async def test_blocks_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("internal.target.com")


async def test_blocks_rfc1918(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("192.168.1.1"))
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("internal.target.com")


async def test_blocks_cloud_metadata_link_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("metadata.target.com")


async def test_blocks_cgnat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("100.64.0.1"))
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("carrier.target.com")


async def test_blocks_when_any_resolved_ip_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(_PUBLIC_IP, "10.0.0.5"))
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("roundrobin.target.com")


async def test_allows_public_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(_PUBLIC_IP))
    await NetworkSafetyGuard().check("target.com")  # must not raise


async def test_blocks_ipv6_loopback_literal() -> None:
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("::1")


async def test_blocks_ipv4_mapped_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("::ffff:127.0.0.1"))
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("sneaky.target.com")


async def test_unresolvable_host_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("nonexistent.invalid")


async def test_allow_loopback_exempts_only_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = NetworkSafetyGuard(allow_loopback=True)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    await guard.check("localhost")  # loopback exempted for the test suite

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("192.168.1.1"))
    with pytest.raises(SecurityViolationError):
        await guard.check("internal.target.com")  # RFC 1918 stays blocked
