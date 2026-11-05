"""RDAP egress: disabled means no socket, 429 is degraded, redirects stop."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from metatracer.connectors.egress import EgressError, ProviderClient
from metatracer.connectors.rdap import (
    Provenance,
    ProvenanceError,
    _select_base,
    clear_cache,
    lookup_domain,
)
from metatracer.core.safety.guard import NetworkSafetyGuard

BOOTSTRAP = {
    "services": [
        [["com"], ["https://rdap.example/v1/"]],
        [["net"], ["http://insecure.example/v1/"]],
    ]
}
RDAP = {
    "ldhName": "example.com",
    "status": ["active"],
    "nameservers": [{"ldhName": "ns1.example.com"}],
    "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"}],
    "entities": [
        {
            "roles": ["registrar"],
            "vcardArray": ["vcard", [["fn", {}, "text", "Example Registrar"]]],
        }
    ],
}


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_cache()


def _client(handler, guard: NetworkSafetyGuard | None = None) -> ProviderClient:
    return ProviderClient(
        guard or NetworkSafetyGuard(allow_loopback=False),
        transport=httpx.MockTransport(handler),
    )


async def test_disabled_connector_does_not_touch_the_network(fake_public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"disabled connector requested {request.url}")

    summary = await lookup_domain("example.com", client=_client(handler), enabled=False)
    assert summary.status == "disabled"
    silent = await lookup_domain("example.com", client=None, enabled=False)
    assert silent.status == "disabled"


async def test_lookup_reads_bootstrap_then_the_tld_server(fake_public_dns) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "data.iana.org":
            return httpx.Response(200, json=BOOTSTRAP)
        if request.url.host == "rdap.example":
            return httpx.Response(200, json=RDAP)
        raise AssertionError(f"unexpected host {request.url.host}")

    summary = await lookup_domain("example.com", client=_client(handler), enabled=True)
    assert summary.status == "available"
    assert summary.registrar == "Example Registrar"
    assert summary.nameservers == ("ns1.example.com",)
    assert summary.events[0][0] == "registration"
    summary.require_provenance()
    assert seen[0].startswith("https://data.iana.org/rdap/dns.json")
    assert seen[1] == "https://rdap.example/v1/domain/example.com"
    assert "http://" not in "".join(seen)


async def test_rate_limit_is_degraded_and_a_redirect_is_not_followed(fake_public_dns) -> None:
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    summary = await lookup_domain("example.com", client=_client(limited), enabled=True)
    assert summary.status == "degraded"

    clear_cache()
    seen: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    summary = await lookup_domain("example.com", client=_client(redirect), enabled=True)
    assert summary.status == "error"
    assert seen == ["https://data.iana.org/rdap/dns.json"]


async def test_http_and_unlisted_hosts_are_refused_before_connect(fake_public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("refused URL was requested")

    client = _client(handler)
    with pytest.raises(EgressError, match="HTTPS"):
        await client.get(
            "http://data.iana.org/rdap/dns.json",
            allow_hosts=frozenset({"data.iana.org"}),
        )
    with pytest.raises(EgressError, match="allowlist"):
        await client.get("https://evil.example/rdap", allow_hosts=frozenset({"data.iana.org"}))


def test_a_result_without_provenance_is_rejected() -> None:
    provenance = Provenance(
        connector_id="rdap",
        source_url="",
        retrieved_at=datetime.now(UTC),
    )
    with pytest.raises(ProvenanceError):
        provenance.require()


def test_insecure_bootstrap_base_is_not_selected() -> None:
    assert _select_base(BOOTSTRAP, "example.net") is None
    assert _select_base(json.loads(json.dumps(BOOTSTRAP)), "example.com") == "https://rdap.example/v1/"
