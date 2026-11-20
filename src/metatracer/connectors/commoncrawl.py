"""Common Crawl index rows. The WARC files are never downloaded.

One request at a time: the collection list, then a single index query.
A 503 or 429 is retried once after a short pause and then reported as
degraded. Rows without a 14-digit capture timestamp are dropped.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode, urlsplit

from metatracer.connectors.egress import EgressError, ProviderClient, ProviderResponse
from metatracer.db.models import ConnectorStatus

CONNECTOR_ID = "commoncrawl"
INDEX_HOST = "index.commoncrawl.org"
COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
_BACKOFF_SECONDS = 1.0
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
_TIMESTAMP_RE = re.compile(r"^\d{14}$")
_RETRYABLE = frozenset({429, 503})


class ProvenanceError(Exception):
    """An index result cannot be returned without a source and a capture date."""


@dataclass(frozen=True, slots=True)
class Provenance:
    connector_id: str
    source_url: str
    retrieved_at: datetime

    def require(self) -> None:
        if self.connector_id != CONNECTOR_ID or not self.source_url.startswith("https://"):
            raise ProvenanceError("common crawl result missing provenance")
        host = (urlsplit(self.source_url).hostname or "").lower()
        if host != INDEX_HOST:
            raise ProvenanceError("common crawl provenance must be the index host")
        if ".warc" in self.source_url or "data.commoncrawl.org" in self.source_url:
            raise ProvenanceError("common crawl provenance must not name a WARC")


@dataclass(frozen=True, slots=True)
class IndexHit:
    capture_date: str
    original_url: str
    status_code: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class CommonCrawlSummary:
    domain: str
    status: ConnectorStatus
    detail: str | None
    hits: tuple[IndexHit, ...]
    warc_fetched: bool
    provenance: Provenance

    def require_provenance(self) -> None:
        if self.status is not ConnectorStatus.available:
            return
        self.provenance.require()
        for hit in self.hits:
            if not _TIMESTAMP_RE.match(hit.capture_date):
                raise ProvenanceError("index row is missing a capture date")


async def search_domain(
    domain: str,
    *,
    client: ProviderClient | None,
    enabled: bool,
    limit: int = DEFAULT_LIMIT,
    backoff_seconds: float = _BACKOFF_SECONDS,
) -> CommonCrawlSummary:
    """Query the latest collection index. ``enabled=False`` never calls ``client``."""
    name = domain.strip().lower().rstrip(".")
    bounded = min(max(limit, 1), MAX_LIMIT)
    placeholder = _index_query("https://index.commoncrawl.org/latest-index", name, bounded)
    if not enabled:
        return _summary(name, ConnectorStatus.disabled, "connector is disabled", (), placeholder)
    if client is None:
        return _summary(name, ConnectorStatus.error, "connector client is missing", (), placeholder)
    if not _DOMAIN_RE.match(name):
        return _summary(name, ConnectorStatus.error, "domain is not a hostname", (), placeholder)
    try:
        listing = await _get(client, COLLINFO_URL, backoff_seconds)
    except EgressError as exc:
        return _summary(name, _status_for(exc), str(exc), (), COLLINFO_URL)
    if listing.status_code in _RETRYABLE or listing.status_code == 504:
        return _summary(
            name,
            ConnectorStatus.degraded,
            f"provider returned HTTP {listing.status_code}",
            (),
            COLLINFO_URL,
        )
    if listing.status_code != 200:
        return _summary(
            name,
            ConnectorStatus.error,
            f"provider returned HTTP {listing.status_code}",
            (),
            COLLINFO_URL,
        )
    index = _latest_index(listing.body)
    if index is None:
        return _summary(
            name,
            ConnectorStatus.error,
            "collection list has no index on the allowlisted host",
            (),
            COLLINFO_URL,
        )
    query = _index_query(index, name, bounded)
    try:
        page = await _get(client, query, backoff_seconds)
    except EgressError as exc:
        return _summary(name, _status_for(exc), str(exc), (), query)
    if page.status_code in _RETRYABLE or page.status_code == 504:
        return _summary(
            name, ConnectorStatus.degraded, f"provider returned HTTP {page.status_code}", (), query
        )
    if page.status_code != 200:
        return _summary(
            name, ConnectorStatus.error, f"provider returned HTTP {page.status_code}", (), query
        )
    summary = _summary(name, ConnectorStatus.available, None, _hits(page.body), query)
    summary.require_provenance()
    return summary


async def _get(client: ProviderClient, url: str, backoff_seconds: float) -> ProviderResponse:
    """One request, then a single sequential retry on 429 or 503."""
    response = await client.get(url, allow_hosts=frozenset({INDEX_HOST}))
    if response.status_code not in _RETRYABLE:
        return response
    await asyncio.sleep(backoff_seconds)
    return await client.get(url, allow_hosts=frozenset({INDEX_HOST}))


def _latest_index(body: bytes) -> str | None:
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    raw = rows[0].get("cdx-api")
    if not isinstance(raw, str):
        return None
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or host != INDEX_HOST:
        return None
    if ".warc" in raw or "data.commoncrawl.org" in raw:
        return None
    return raw.split("?", 1)[0]


def _index_query(index: str, domain: str, limit: int) -> str:
    query = urlencode({"url": f"{domain}/*", "output": "json", "limit": str(limit)})
    return f"{index}?{query}"


def _hits(body: bytes) -> tuple[IndexHit, ...]:
    found: list[IndexHit] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        timestamp = row.get("timestamp")
        url = row.get("url")
        if not isinstance(timestamp, str) or not _TIMESTAMP_RE.match(timestamp):
            continue
        if not isinstance(url, str) or not url:
            continue
        status = row.get("status")
        mime = row.get("mime")
        found.append(
            IndexHit(
                capture_date=timestamp,
                original_url=url[:500],
                status_code=status[:8] if isinstance(status, str) else "",
                mime_type=mime[:80] if isinstance(mime, str) else "",
            )
        )
        if len(found) >= MAX_LIMIT:
            break
    return tuple(found)


def _summary(
    domain: str,
    status: ConnectorStatus,
    detail: str | None,
    hits: tuple[IndexHit, ...],
    source_url: str,
) -> CommonCrawlSummary:
    summary = CommonCrawlSummary(
        domain=domain,
        status=status,
        detail=detail,
        hits=hits,
        warc_fetched=False,
        provenance=Provenance(
            connector_id=CONNECTOR_ID,
            source_url=source_url,
            retrieved_at=datetime.now(UTC),
        ),
    )
    if status is ConnectorStatus.available:
        summary.require_provenance()
    return summary


def _status_for(exc: EgressError) -> ConnectorStatus:
    text = str(exc).lower()
    if "rate limited" in text or "503" in text or "504" in text or "timed out" in text:
        return ConnectorStatus.degraded
    return ConnectorStatus.error
