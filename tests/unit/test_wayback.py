"""Wayback CDX lists captures and never downloads the archived page."""

import json

import httpx
import pytest

from metatracer.connectors.egress import ProviderClient
from metatracer.connectors.wayback import ProvenanceError, search_domain
from metatracer.core.safety.guard import NetworkSafetyGuard

CDX = [
    ["timestamp", "original", "statuscode", "mimetype"],
    ["20200101120000", "http://example.com/a", "200", "text/html"],
    ["not-a-date", "http://example.com/skip", "200", "text/html"],
    ["20210615030000", "http://example.com/b?x=1", "301", "text/html"],
]


def _client(handler) -> ProviderClient:
    return ProviderClient(
        NetworkSafetyGuard(allow_loopback=False),
        transport=httpx.MockTransport(handler),
    )


async def test_disabled_wayback_does_not_touch_the_network(fake_public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"disabled connector requested {request.url}")

    summary = await search_domain("example.com", client=_client(handler), enabled=False)
    assert summary.status == "disabled"
    assert summary.replay_fetched is False


async def test_cdx_keeps_dated_captures_and_does_not_fetch_replay(fake_public_dns) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert "/web/" not in str(request.url)
        assert request.url.params["gzip"] == "false"
        assert request.url.params["collapse"] == "urlkey"
        return httpx.Response(200, content=json.dumps(CDX).encode())

    summary = await search_domain("example.com", client=_client(handler), enabled=True, limit=500)
    assert summary.status == "available"
    assert summary.replay_fetched is False
    assert [item.capture_date for item in summary.captures] == [
        "20200101120000",
        "20210615030000",
    ]
    assert "limit=20" in seen[0]
    summary.require_provenance()


async def test_rate_limit_is_degraded(fake_public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    summary = await search_domain("example.com", client=_client(handler), enabled=True)
    assert summary.status == "degraded"
    assert summary.captures == ()


def test_a_capture_without_a_date_cannot_pass_as_available() -> None:
    from datetime import UTC, datetime

    from metatracer.connectors.wayback import Capture, Provenance, WaybackSummary

    summary = WaybackSummary(
        domain="example.com",
        status="available",
        detail=None,
        captures=(Capture("yesterday", "http://example.com/", "200", "text/html"),),
        replay_fetched=False,
        provenance=Provenance(
            connector_id="wayback",
            source_url="https://web.archive.org/cdx/search/cdx?url=example.com",
            retrieved_at=datetime.now(UTC),
        ),
    )
    with pytest.raises(ProvenanceError):
        summary.require_provenance()
