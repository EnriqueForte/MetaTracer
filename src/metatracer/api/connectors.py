"""Connector catalogue (Fase 4). RDAP is context, not a scan.

Nothing here adds a host to ``allowed_scope``. A disabled connector returns
before the HTTP client is constructed.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from metatracer.connectors.commoncrawl import CONNECTOR_ID as CRAWL_ID
from metatracer.connectors.commoncrawl import INDEX_HOST
from metatracer.connectors.commoncrawl import search_domain as search_commoncrawl
from metatracer.connectors.egress import ProviderClient
from metatracer.connectors.rdap import CONNECTOR_ID as RDAP_ID
from metatracer.connectors.rdap import IANA_HOST, lookup_domain
from metatracer.connectors.wayback import ARCHIVE_HOST, search_domain
from metatracer.connectors.wayback import CONNECTOR_ID as WAYBACK_ID
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.db.models import ConnectorSetting

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

_RDAP_NOTICE = (
    "Sends the domain name to the RDAP service named by the IANA bootstrap. "
    "Registrant data is often redacted. This does not add the domain to a scan scope "
    "and does not request any URL found in the record."
)
_WAYBACK_NOTICE = (
    "Sends the domain name to the Wayback CDX index. Results are historical captures "
    "with a capture date. Archived pages are not downloaded and are not current exposure."
)
_CRAWL_NOTICE = (
    "Sends the domain name to the Common Crawl index, one request at a time. "
    "Results are historical index rows with a capture date. WARC files are not downloaded."
)


class ConnectorCard(BaseModel):
    id: str
    label: str
    kind: str
    enabled: bool
    sends: list[str]
    egress_hosts: list[str]
    notice: str


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorCard]


class ConnectorToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class RdapLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=253)


class ProvenanceResponse(BaseModel):
    connector_id: str
    source_url: str
    retrieved_at: str


class RdapLookupResponse(BaseModel):
    domain: str
    status: str
    detail: str | None
    registrar: str | None
    statuses: list[str]
    nameservers: list[str]
    events: list[list[str]]
    provenance: ProvenanceResponse


class WaybackCaptureResponse(BaseModel):
    capture_date: str
    original_url: str
    status_code: str
    mime_type: str


class WaybackSearchResponse(BaseModel):
    domain: str
    status: str
    detail: str | None
    replay_fetched: bool
    captures: list[WaybackCaptureResponse]
    provenance: ProvenanceResponse


def _rdap_card(enabled: bool) -> ConnectorCard:
    return ConnectorCard(
        id=RDAP_ID,
        label="RDAP",
        kind="context",
        enabled=enabled,
        sends=["domain name"],
        egress_hosts=[IANA_HOST],
        notice=_RDAP_NOTICE,
    )


class CommonCrawlHitResponse(BaseModel):
    capture_date: str
    original_url: str
    status_code: str
    mime_type: str


class CommonCrawlSearchResponse(BaseModel):
    domain: str
    status: str
    detail: str | None
    warc_fetched: bool
    hits: list[CommonCrawlHitResponse]
    provenance: ProvenanceResponse


def _wayback_card(enabled: bool) -> ConnectorCard:
    return ConnectorCard(
        id=WAYBACK_ID,
        label="Wayback CDX",
        kind="discovery",
        enabled=enabled,
        sends=["domain name"],
        egress_hosts=[ARCHIVE_HOST],
        notice=_WAYBACK_NOTICE,
    )


def _crawl_card(enabled: bool) -> ConnectorCard:
    return ConnectorCard(
        id=CRAWL_ID,
        label="Common Crawl",
        kind="discovery",
        enabled=enabled,
        sends=["domain name"],
        egress_hosts=[INDEX_HOST],
        notice=_CRAWL_NOTICE,
    )


async def _is_enabled(request: Request, connector_id: str) -> bool:
    async with request.app.state.session_factory() as session:
        row = await session.get(ConnectorSetting, connector_id)
        return bool(row and row.enabled)


async def _set_enabled(request: Request, connector_id: str, enabled: bool) -> None:
    async with request.app.state.session_factory() as session:
        row = await session.get(ConnectorSetting, connector_id)
        if row is None:
            session.add(ConnectorSetting(connector_id=connector_id, enabled=enabled))
        else:
            row.enabled = enabled
            session.add(row)
        await session.commit()


@router.get("")
async def list_connectors(request: Request) -> ConnectorListResponse:
    return ConnectorListResponse(
        connectors=[
            _rdap_card(await _is_enabled(request, RDAP_ID)),
            _wayback_card(await _is_enabled(request, WAYBACK_ID)),
            _crawl_card(await _is_enabled(request, CRAWL_ID)),
        ]
    )


@router.put("/rdap")
async def set_rdap(body: ConnectorToggle, request: Request) -> ConnectorCard:
    await _set_enabled(request, RDAP_ID, body.enabled)
    return _rdap_card(body.enabled)


@router.put("/wayback")
async def set_wayback(body: ConnectorToggle, request: Request) -> ConnectorCard:
    await _set_enabled(request, WAYBACK_ID, body.enabled)
    return _wayback_card(body.enabled)


@router.put("/commoncrawl")
async def set_commoncrawl(body: ConnectorToggle, request: Request) -> ConnectorCard:
    await _set_enabled(request, CRAWL_ID, body.enabled)
    return _crawl_card(body.enabled)


@router.post("/rdap/lookup")
async def rdap_lookup(body: RdapLookupRequest, request: Request) -> RdapLookupResponse:
    enabled = await _is_enabled(request, RDAP_ID)
    client = ProviderClient(
        NetworkSafetyGuard(request.app.state.settings.allow_loopback),
    )
    if not enabled:
        # Build the client only after the flag is known to be false? The
        # lookup returns before any method on the client runs.
        summary = await lookup_domain(body.domain, client=client, enabled=False)
    else:
        summary = await lookup_domain(body.domain, client=client, enabled=True)
    return RdapLookupResponse(
        domain=summary.domain,
        status=summary.status,
        detail=summary.detail,
        registrar=summary.registrar,
        statuses=list(summary.statuses),
        nameservers=list(summary.nameservers),
        events=[list(pair) for pair in summary.events],
        provenance=ProvenanceResponse(
            connector_id=summary.provenance.connector_id,
            source_url=summary.provenance.source_url,
            retrieved_at=summary.provenance.retrieved_at.isoformat(),
        ),
    )


@router.post("/wayback/search")
async def wayback_search(body: RdapLookupRequest, request: Request) -> WaybackSearchResponse:
    enabled = await _is_enabled(request, WAYBACK_ID)
    client = ProviderClient(NetworkSafetyGuard(request.app.state.settings.allow_loopback))
    summary = await search_domain(body.domain, client=client, enabled=enabled)
    return WaybackSearchResponse(
        domain=summary.domain,
        status=summary.status,
        detail=summary.detail,
        replay_fetched=summary.replay_fetched,
        captures=[
            WaybackCaptureResponse(
                capture_date=item.capture_date,
                original_url=item.original_url,
                status_code=item.status_code,
                mime_type=item.mime_type,
            )
            for item in summary.captures
        ],
        provenance=ProvenanceResponse(
            connector_id=summary.provenance.connector_id,
            source_url=summary.provenance.source_url,
            retrieved_at=summary.provenance.retrieved_at.isoformat(),
        ),
    )


@router.post("/commoncrawl/search")
async def commoncrawl_search(
    body: RdapLookupRequest, request: Request
) -> CommonCrawlSearchResponse:
    enabled = await _is_enabled(request, CRAWL_ID)
    client = ProviderClient(NetworkSafetyGuard(request.app.state.settings.allow_loopback))
    summary = await search_commoncrawl(body.domain, client=client, enabled=enabled)
    return CommonCrawlSearchResponse(
        domain=summary.domain,
        status=summary.status,
        detail=summary.detail,
        warc_fetched=summary.warc_fetched,
        hits=[
            CommonCrawlHitResponse(
                capture_date=item.capture_date,
                original_url=item.original_url,
                status_code=item.status_code,
                mime_type=item.mime_type,
            )
            for item in summary.hits
        ],
        provenance=ProvenanceResponse(
            connector_id=summary.provenance.connector_id,
            source_url=summary.provenance.source_url,
            retrieved_at=summary.provenance.retrieved_at.isoformat(),
        ),
    )
