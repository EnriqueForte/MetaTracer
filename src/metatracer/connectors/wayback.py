"""Wayback CDX index. Historical captures are listed, never downloaded.

The only host contacted is ``web.archive.org``, and only the CDX search
endpoint. A row without a 14-digit capture timestamp is dropped. Replay URLs
under ``/web/`` are not requested.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from metatracer.connectors.egress import EgressError, ProviderClient
from metatracer.db.models import ConnectorStatus

CONNECTOR_ID = "wayback"
ARCHIVE_HOST = "web.archive.org"
CDX_URL = "https://web.archive.org/cdx/search/cdx"
DEFAULT_LIMIT = 10
MAX_LIMIT = 20
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
_TIMESTAMP_RE = re.compile(r"^\d{14}$")


class ProvenanceError(Exception):
    """A capture list cannot be returned without a source and a time."""


@dataclass(frozen=True, slots=True)
class Provenance:
    connector_id: str
    source_url: str
    retrieved_at: datetime

    def require(self) -> None:
        if self.connector_id != CONNECTOR_ID or not self.source_url.startswith("https://"):
            raise ProvenanceError("wayback result missing provenance")
        if ARCHIVE_HOST not in self.source_url:
            raise ProvenanceError("wayback provenance must name the CDX host")
        if "/web/" in self.source_url:
            raise ProvenanceError("wayback provenance must be the index, not a replay")


@dataclass(frozen=True, slots=True)
class Capture:
    capture_date: str
    original_url: str
    status_code: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class WaybackSummary:
    domain: str
    status: ConnectorStatus
    detail: str | None
    captures: tuple[Capture, ...]
    replay_fetched: bool
    provenance: Provenance

    def require_provenance(self) -> None:
        if self.status is ConnectorStatus.available:
            self.provenance.require()
            for capture in self.captures:
                if not _TIMESTAMP_RE.match(capture.capture_date):
                    raise ProvenanceError("capture is missing a capture date")


async def search_domain(
    domain: str, *, client: ProviderClient | None, enabled: bool, limit: int = DEFAULT_LIMIT
) -> WaybackSummary:
    """Search the CDX index. ``enabled=False`` never calls ``client``."""
    name = domain.strip().lower().rstrip(".")
    bounded = min(max(limit, 1), MAX_LIMIT)
    if not enabled:
        return _summary(
            name, ConnectorStatus.disabled, "connector is disabled", (), cdx_url(name, bounded)
        )
    if client is None:
        return _summary(
            name, ConnectorStatus.error, "connector client is missing", (), cdx_url(name, bounded)
        )
    if not _DOMAIN_RE.match(name):
        return _summary(
            name, ConnectorStatus.error, "domain is not a hostname", (), cdx_url(name, bounded)
        )
    url = cdx_url(name, bounded)
    if "/web/" in url:
        return _summary(name, ConnectorStatus.error, "replay URLs are not requested", (), url)
    try:
        response = await client.get(url, allow_hosts=frozenset({ARCHIVE_HOST}))
    except EgressError as exc:
        text = str(exc).lower()
        status = ConnectorStatus.degraded if "rate limited" in text else ConnectorStatus.error
        return _summary(name, status, str(exc), (), url)
    if response.status_code == 429:
        return _summary(
            name, ConnectorStatus.degraded, "provider rate limited the search", (), url
        )
    if response.status_code != 200:
        return _summary(
            name, ConnectorStatus.error, f"provider returned HTTP {response.status_code}", (), url
        )
    captures = _captures(response.body)
    summary = _summary(name, ConnectorStatus.available, None, captures, url)
    summary.require_provenance()
    return summary


def cdx_url(domain: str, limit: int) -> str:
    query = urlencode(
        {
            "url": f"{domain}/*",
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype",
            "collapse": "urlkey",
            "limit": str(limit),
            "gzip": "false",
        }
    )
    return f"{CDX_URL}?{query}"


def _captures(body: bytes) -> tuple[Capture, ...]:
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return ()
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
        return ()
    header = [str(cell) for cell in rows[0]]
    if "timestamp" not in header or "original" not in header:
        return ()
    index = {name: position for position, name in enumerate(header)}
    found: list[Capture] = []
    for row in rows[1:]:
        if not isinstance(row, list):
            continue
        timestamp = _cell(row, index.get("timestamp"))
        original = _cell(row, index.get("original"))
        if not _TIMESTAMP_RE.match(timestamp) or not original:
            continue
        found.append(
            Capture(
                capture_date=timestamp,
                original_url=original[:500],
                status_code=_cell(row, index.get("statuscode"))[:8],
                mime_type=_cell(row, index.get("mimetype"))[:80],
            )
        )
        if len(found) >= MAX_LIMIT:
            break
    return tuple(found)


def _cell(row: list[object], position: int | None) -> str:
    if position is None or position >= len(row) or not isinstance(row[position], str):
        return ""
    return row[position]


def _summary(
    domain: str,
    status: ConnectorStatus,
    detail: str | None,
    captures: tuple[Capture, ...],
    source_url: str,
) -> WaybackSummary:
    summary = WaybackSummary(
        domain=domain,
        status=status,
        detail=detail,
        captures=captures,
        replay_fetched=False,
        provenance=Provenance(
            connector_id=CONNECTOR_ID,
            source_url=source_url,
            retrieved_at=datetime.now(UTC),
        ),
    )
    if status is ConnectorStatus.available:
        summary.require_provenance()
    return summary
