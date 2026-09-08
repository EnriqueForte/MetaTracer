"""Shared plumbing for the whole suite: fake DNS and in-memory HTTP transport.

ScopeValidator and NetworkSafetyGuard are never mocked — every test exercises
the real safety controls. DNS resolution and the HTTP transport are faked.
"""

import socket
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

# Directory-based marks (TASK-07, subtask 7.2): tests/agents runs with a mocked
# LLM and no network, so it belongs to the fast unit tier. The e2e mark lives
# in the e2e module itself (pytestmark), on top of its integration tier.
_DIR_MARKS = {"unit": "unit", "agents": "unit", "integration": "integration"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply the tier mark from the test's directory under tests/."""
    tests_root = Path(__file__).parent.resolve()
    for item in items:
        try:
            relative = item.path.resolve().relative_to(tests_root)
        except ValueError:
            continue  # a test outside tests/ keeps its own marks only
        mark = _DIR_MARKS.get(relative.parts[0])
        if mark is not None:
            item.add_marker(getattr(pytest.mark, mark))


@pytest.fixture()
def fake_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every host resolves to a public IP; the real guard still validates it."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: PUBLIC_ADDRINFO)


@pytest.fixture()
def install_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], None]:
    """Install an httpx.MockTransport handler as the AsyncClient transport.

    Only AsyncClients created AFTER installation are affected — create any
    test-owned client (e.g. an API client) before requesting this fixture.
    """

    def _install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return _install
