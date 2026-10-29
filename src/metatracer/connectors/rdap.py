"""RDAP context lookup. Not part of a scan and not an authorization.

The domain name is sent to ``data.iana.org`` and then to the HTTPS RDAP base
that bootstrap lists for the TLD. Registrant records are often redacted; the
summary keeps registrar, dates, status and nameservers. A disabled connector
does not call the client.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from metatracer.connectors.egress import EgressError, ProviderClient

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
IANA_HOST = "data.iana.org"
CONNECTOR_ID = "rdap"
CACHE_TTL_SECONDS = 24 * 60 * 60

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)


class ProvenanceError(Exception):
    """A provider payload cannot be returned without a source and a time."""


@dataclass(frozen=True, slots=True)
class Provenance:
    connector_id: str
    source_url: str
    retrieved_at: datetime

    def require(self) -> None:
        if self.connector_id != CONNECTOR_ID or not self.source_url or self.retrieved_at is None:
            raise ProvenanceError("rdap result missing provenance")
        if not self.source_url.lower().startswith("https://"):
            raise ProvenanceError("rdap provenance URL must be HTTPS")


@dataclass(frozen=True, slots=True)
class RdapSummary:
    domain: str
    registrar: str | None
    statuses: tuple[str, ...]
    nameservers: tuple[str, ...]
    events: tuple[tuple[str, str], ...]
    provenance: Provenance
    status: str  # available | degraded | error | disabled
    detail: str | None = None

    def require_provenance(self) -> None:
        if self.status == "available":
            self.provenance.require()


@dataclass
class _Cache:
    stored_at: float = 0.0
    body: bytes = b""
    summaries: dict[str, tuple[float, RdapSummary]] = field(default_factory=dict)


_CACHE = _Cache()


def clear_cache() -> None:
    _CACHE.stored_at = 0.0
    _CACHE.body = b""
    _CACHE.summaries.clear()


async def lookup_domain(domain: str, *, client: ProviderClient, enabled: bool) -> RdapSummary:
    """Look up one domain. ``enabled=False`` never touches ``client``."""
    name = domain.strip().lower().rstrip(".")
    if not enabled:
        return _result(
            name, "disabled", "connector is disabled", source_url=BOOTSTRAP_URL, body=None
        )
    if not _DOMAIN_RE.match(name):
        return _result(
            name, "error", "domain is not a hostname", source_url=BOOTSTRAP_URL, body=None
        )
    cached = _CACHE.summaries.get(name)
    if cached is not None and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    try:
        bootstrap = await _bootstrap(client)
    except EgressError as exc:
        return _result(name, _status_for(exc), str(exc), source_url=BOOTSTRAP_URL, body=None)
    base = _select_base(bootstrap, name)
    if base is None:
        return _result(
            name, "error", "no RDAP service for this TLD", source_url=BOOTSTRAP_URL, body=None
        )
    host = (urlsplit(base).hostname or "").lower()
    url = base.rstrip("/") + "/domain/" + name
    try:
        response = await client.get(url, allow_hosts=frozenset({host}))
    except EgressError as exc:
        return _result(name, _status_for(exc), str(exc), source_url=url, body=None)
    if response.status_code == 429:
        return _result(
            name, "degraded", "provider rate limited the lookup", source_url=url, body=None
        )
    if response.status_code != 200:
        return _result(
            name,
            "error",
            f"provider returned HTTP {response.status_code}",
            source_url=url,
            body=None,
        )
    summary = _summarize(name, response.body, source_url=url)
    summary.require_provenance()
    _CACHE.summaries[name] = (time.monotonic(), summary)
    return summary


async def _bootstrap(client: ProviderClient) -> object:
    fresh = _CACHE.body and time.monotonic() - _CACHE.stored_at < CACHE_TTL_SECONDS
    if not fresh:
        response = await client.get(BOOTSTRAP_URL, allow_hosts=frozenset({IANA_HOST}))
        if response.status_code == 429:
            raise EgressError("provider rate limited the lookup")
        if response.status_code != 200 or not response.body:
            raise EgressError(f"bootstrap returned HTTP {response.status_code}")
        _CACHE.body = response.body
        _CACHE.stored_at = time.monotonic()
    try:
        return json.loads(_CACHE.body)
    except json.JSONDecodeError as exc:
        _CACHE.body = b""
        raise EgressError("bootstrap document is not JSON") from exc


def _select_base(document: object, domain: str) -> str | None:
    if not isinstance(document, dict):
        return None
    services = document.get("services")
    if not isinstance(services, list):
        return None
    best: str | None = None
    best_len = -1
    for entry in services:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        tlds, urls = entry[0], entry[1]
        if not isinstance(tlds, list) or not isinstance(urls, list):
            continue
        https = [url for url in urls if isinstance(url, str) and url.lower().startswith("https://")]
        if not https:
            continue
        for tld in tlds:
            if not isinstance(tld, str):
                continue
            label = tld.lower().lstrip(".")
            if domain == label or domain.endswith("." + label):
                if len(label) > best_len:
                    best = https[0]
                    best_len = len(label)
    return best


def _summarize(domain: str, body: bytes, *, source_url: str) -> RdapSummary:
    try:
        document = json.loads(body)
    except json.JSONDecodeError:
        return _result(
            domain, "error", "RDAP document is not JSON", source_url=source_url, body=None
        )
    if not isinstance(document, dict):
        return _result(
            domain,
            "error",
            "RDAP document is not an object",
            source_url=source_url,
            body=None,
        )
    statuses = _strings(document.get("status"), limit=8)
    nameservers = _nameservers(document.get("nameservers"))
    events = _events(document.get("events"))
    registrar = _registrar(document.get("entities"))
    return _result(
        domain,
        "available",
        None,
        source_url=source_url,
        body=body,
        registrar=registrar,
        statuses=statuses,
        nameservers=nameservers,
        events=events,
    )


def _result(
    domain: str,
    status: str,
    detail: str | None,
    *,
    source_url: str,
    body: bytes | None,
    registrar: str | None = None,
    statuses: tuple[str, ...] = (),
    nameservers: tuple[str, ...] = (),
    events: tuple[tuple[str, str], ...] = (),
) -> RdapSummary:
    del body
    summary = RdapSummary(
        domain=domain,
        registrar=registrar,
        statuses=statuses,
        nameservers=nameservers,
        events=events,
        provenance=Provenance(
            connector_id=CONNECTOR_ID,
            source_url=source_url,
            retrieved_at=datetime.now(UTC),
        ),
        status=status,
        detail=detail,
    )
    if status == "available":
        summary.require_provenance()
    return summary


def _status_for(exc: EgressError) -> str:
    text = str(exc).lower()
    if "rate limited" in text:
        return "degraded"
    return "error"


def _strings(value: object, *, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    found = [str(item)[:80] for item in value if isinstance(item, str) and item.strip()]
    return tuple(found[:limit])


def _nameservers(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("ldhName"), str):
            names.append(item["ldhName"].lower()[:253])
        if len(names) >= 8:
            break
    return tuple(names)


def _events(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    kept: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        action = item.get("eventAction")
        when = item.get("eventDate")
        if isinstance(action, str) and isinstance(when, str):
            kept.append((action[:40], when[:40]))
        if len(kept) >= 6:
            break
    return tuple(kept)


def _registrar(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        roles = item.get("roles")
        if not isinstance(roles, list) or "registrar" not in roles:
            continue
        vcard = item.get("vcardArray")
        if isinstance(vcard, list) and len(vcard) > 1 and isinstance(vcard[1], list):
            for row in vcard[1]:
                if (
                    isinstance(row, list)
                    and len(row) >= 4
                    and row[0] == "fn"
                    and isinstance(row[3], str)
                ):
                    return row[3][:120]
    return None
