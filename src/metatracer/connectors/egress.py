"""HTTPS egress for connectors. This is not the scan gateway.

Scan requests go through ``safe_httpx_request`` and must sit inside the
confirmed scope. A connector talks to a provider host declared by its own
code. The operator cannot add hosts. Redirects are not followed, proxies in
the environment are ignored, and the anti-SSRF guard still runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from metatracer.core.exceptions import SecurityViolationError
from metatracer.core.logging import sanitize_for_log
from metatracer.core.safety.guard import NetworkSafetyGuard

MAX_PROVIDER_BYTES = 256 * 1024
_REDIRECTS = frozenset({301, 302, 303, 307, 308})


class EgressError(Exception):
    """The provider was not contacted, or the response cannot be used."""


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    status_code: int
    body: bytes
    url: str


class ProviderClient:
    """One GET through the connector egress rules."""

    def __init__(
        self,
        guard: NetworkSafetyGuard,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_bytes: int = MAX_PROVIDER_BYTES,
    ) -> None:
        self._guard = guard
        self._transport = transport
        self._max_bytes = max_bytes

    async def get(self, url: str, *, allow_hosts: frozenset[str]) -> ProviderResponse:
        parts = urlsplit(url)
        if parts.scheme.lower() != "https":
            raise EgressError("provider URL must use HTTPS")
        host = (parts.hostname or "").lower()
        if not host or host not in allow_hosts:
            raise EgressError("provider host is not on this connector's allowlist")
        port = parts.port or 443
        try:
            await self._guard.check(host, port)
        except SecurityViolationError as exc:
            raise EgressError(f"provider host rejected ({sanitize_for_log(exc)})") from exc
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code in _REDIRECTS:
                        raise EgressError("provider redirect was not followed")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise EgressError("provider response exceeds the size cap")
                    return ProviderResponse(response.status_code, bytes(body), url)
        except EgressError:
            raise
        except httpx.TimeoutException as exc:
            raise EgressError("provider timed out") from exc
        except httpx.HTTPError as exc:
            raise EgressError("provider request failed") from exc
