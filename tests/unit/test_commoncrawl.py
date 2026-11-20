"""Common Crawl index search never downloads a WARC and never runs in parallel."""

import json

import httpx
import pytest

from metatracer.connectors.commoncrawl import ProvenanceError, search_domain
from metatracer.connectors.egress import ProviderClient
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.db.models import ConnectorStatus

COLLINFO = [
    {
        "id": "CC-MAIN-2026-01",
        "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2026-01-index",
    }
]
NDJSON = "\n".join(
    [
        json.dumps(
            {
                "timestamp": "20260101120000",
                "url": "http://example.com/a",
                "status": "200",
                "mime": "text/html",
                "filename": "crawl-data/CC-MAIN-2026-01/segments/a.warc.gz",
                "offset": "10",
                "length": "20",
            }
        ),
        json.dumps({"url": "http://example.com/nodate", "status": "200"}),
    ]
)


def _client(handler) -> ProviderClient:
    return ProviderClient(
        NetworkSafetyGuard(allow_loopback=False),
        transport=httpx.MockTransport(handler),
    )


async def test_disabled_common_crawl_does_not_touch_the_network(fake_public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"disabled connector requested {request.url}")

    summary = await search_domain("example.com", client=_client(handler), enabled=False)
    assert summary.status == "disabled"
    silent = await search_domain("example.com", client=None, enabled=False)
    assert silent.status == "disabled"
    assert summary.warc_fetched is False


async def test_index_rows_keep_a_capture_date_and_skip_the_warc(fake_public_dns) -> None:
    seen: list[str] = []
    inflight = 0
    peak = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        seen.append(request.url.host + request.url.path)
        inflight -= 1
        if request.url.path == "/collinfo.json":
            return httpx.Response(200, json=COLLINFO)
        return httpx.Response(200, content=NDJSON.encode())

    summary = await search_domain(
        "example.com", client=_client(handler), enabled=True, backoff_seconds=0
    )
    assert summary.status == "available"
    assert summary.warc_fetched is False
    assert [hit.capture_date for hit in summary.hits] == ["20260101120000"]
    assert seen == [
        "index.commoncrawl.org/collinfo.json",
        "index.commoncrawl.org/CC-MAIN-2026-01-index",
    ]
    assert peak == 1
    assert all("data.commoncrawl.org" not in url and ".warc" not in url for url in seen)
    summary.require_provenance()


async def test_a_provider_timeout_is_degraded_instead_of_raising(fake_public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    summary = await search_domain(
        "example.com", client=_client(handler), enabled=True, backoff_seconds=0
    )
    assert summary.status == "degraded"
    assert summary.hits == ()
    assert summary.detail == "provider timed out"


async def test_a_repeated_503_is_degraded_after_one_retry(fake_public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    summary = await search_domain(
        "example.com", client=_client(handler), enabled=True, backoff_seconds=0
    )
    assert summary.status == "degraded"
    assert calls == 2
    assert summary.hits == ()


def test_a_hit_without_a_capture_date_cannot_pass_as_available() -> None:
    from datetime import UTC, datetime

    from metatracer.connectors.commoncrawl import CommonCrawlSummary, IndexHit, Provenance

    summary = CommonCrawlSummary(
        domain="example.com",
        status=ConnectorStatus.available,
        detail=None,
        hits=(IndexHit("yesterday", "http://example.com/", "200", "text/html"),),
        warc_fetched=False,
        provenance=Provenance(
            connector_id="commoncrawl",
            source_url="https://index.commoncrawl.org/CC-MAIN-2026-01-index?url=example.com",
            retrieved_at=datetime.now(UTC),
        ),
    )
    with pytest.raises(ProvenanceError):
        summary.require_provenance()
