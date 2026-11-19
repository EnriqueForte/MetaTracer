"""Read-only scan graph: crawl edges, correlation bipartite, inventory metrics.

TASK-55. The crawler persists ``discovery_edge`` rows; this module never
invents a link. Correlation nodes are shared values, not identities.
``evidence_snippet`` is never included.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import (
    Asset,
    CorrelationKind,
    DiscoveryEdge,
    DiscoveryEdgeKind,
    ExtractionStatus,
    Finding,
    GraphNodeKind,
)
from metatracer.db.repositories import (
    AssetRepository,
    DiscoveryEdgeRepository,
    FindingRepository,
    RunRepository,
)
from metatracer.services.correlation import NOTICE, CorrelationGroup, groups_touching_run

MAX_GRAPH_NODES = 400
MAX_GRAPH_EDGES = 800
_LABEL_MAX = 48


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    kind: GraphNodeKind
    label: str
    url: str | None = None
    asset_id: str | None = None
    correlation_kind: CorrelationKind | None = None
    extraction_status: ExtractionStatus | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    from_id: str
    to_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class GraphLayer:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    truncated: bool
    notice: str | None = None


@dataclass(frozen=True, slots=True)
class GraphMetrics:
    by_content_type: dict[str, int] = field(default_factory=dict)
    by_finding_type: dict[str, int] = field(default_factory=dict)
    by_extraction_status: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunGraph:
    run_id: str
    crawl: GraphLayer
    correlations: GraphLayer
    metrics: GraphMetrics


class RunGraphService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, run_id: str) -> RunGraph:
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
            if run is None:
                raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")
            assets = await AssetRepository(session).list_by_run(run_id)
            edges = await DiscoveryEdgeRepository(session).list_by_run(run_id)
            findings = await FindingRepository(session).list_by_run(run_id)
            groups = await groups_touching_run(session, run_id)
        by_url = _asset_index(assets)
        return RunGraph(
            run_id=run_id,
            crawl=_crawl_layer(edges, by_url),
            correlations=_correlation_layer(groups, run_id),
            metrics=_metrics(assets, findings),
        )


def _asset_index(assets: list[Asset]) -> dict[str, Asset]:
    index: dict[str, Asset] = {}
    for asset in assets:
        if asset.source_url:
            index.setdefault(asset.source_url, asset)
        if asset.final_url:
            index.setdefault(asset.final_url, asset)
    return index


def _crawl_layer(edges: list[DiscoveryEdge], by_url: dict[str, Asset]) -> GraphLayer:
    nodes: dict[str, GraphNode] = {}
    drawn: list[GraphEdge] = []
    truncated = False
    local_parents = {edge.from_url for edge in edges if edge.kind is DiscoveryEdgeKind.local}
    for edge in edges:
        if len(drawn) >= MAX_GRAPH_EDGES:
            truncated = True
            break
        pending = [url for url in (edge.from_url, edge.to_url) if url not in nodes]
        if len(nodes) + len(pending) > MAX_GRAPH_NODES:
            truncated = True
            break
        for url in (edge.from_url, edge.to_url):
            if url in nodes:
                continue
            nodes[url] = _crawl_node(url, by_url, local_parents)
        drawn.append(GraphEdge(from_id=edge.from_url, to_id=edge.to_url, kind=str(edge.kind)))
    return GraphLayer(nodes=tuple(nodes.values()), edges=tuple(drawn), truncated=truncated)


def _crawl_node(url: str, by_url: dict[str, Asset], local_parents: set[str]) -> GraphNode:
    asset = by_url.get(url)
    if asset is not None:
        return GraphNode(
            id=url,
            kind=GraphNodeKind.asset,
            label=_label(url),
            url=url,
            asset_id=asset.id,
            extraction_status=asset.extraction_status,
        )
    kind = GraphNodeKind.local_root if url in local_parents else GraphNodeKind.page
    return GraphNode(id=url, kind=kind, label=_label(url), url=url)


def _correlation_layer(groups: list[CorrelationGroup], run_id: str) -> GraphLayer:
    nodes: dict[str, GraphNode] = {}
    drawn: list[GraphEdge] = []
    truncated = False
    notice: str | None = None
    for group in groups:
        notice = group.notice or NOTICE.format(count=group.occurrences)
        here = [member for member in group.members if member.run_id == run_id]
        if not here:
            continue
        value_id = _value_node_id(group.kind, group.value_norm)
        member_ids = [f"asset:{member.asset_id}" for member in here]
        pending_ids = [value_id, *[mid for mid in member_ids if mid not in nodes]]
        extra_nodes = len({pid for pid in pending_ids if pid not in nodes})
        extra_edges = len(member_ids)
        if len(nodes) + extra_nodes > MAX_GRAPH_NODES or len(drawn) + extra_edges > MAX_GRAPH_EDGES:
            truncated = True
            break
        nodes[value_id] = GraphNode(
            id=value_id,
            kind=GraphNodeKind.value,
            label=_clip(group.value_norm),
            correlation_kind=group.kind,
        )
        for member in here:
            asset_id = f"asset:{member.asset_id}"
            if asset_id not in nodes:
                nodes[asset_id] = GraphNode(
                    id=asset_id,
                    kind=GraphNodeKind.asset,
                    label=_label(member.asset_url),
                    url=member.asset_url,
                    asset_id=member.asset_id,
                )
            drawn.append(GraphEdge(from_id=asset_id, to_id=value_id, kind=str(group.kind)))
    return GraphLayer(
        nodes=tuple(nodes.values()),
        edges=tuple(drawn),
        truncated=truncated,
        notice=notice,
    )


def _metrics(assets: list[Asset], findings: list[Finding]) -> GraphMetrics:
    by_content_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_finding_type: dict[str, int] = {}
    for asset in assets:
        mime = (asset.content_type or "").split(";", 1)[0].strip().lower() or "unknown"
        by_content_type[mime] = by_content_type.get(mime, 0) + 1
        status = str(asset.extraction_status)
        by_status[status] = by_status.get(status, 0) + 1
    for finding in findings:
        key = str(finding.finding_type)
        by_finding_type[key] = by_finding_type.get(key, 0) + 1
    return GraphMetrics(
        by_content_type=by_content_type,
        by_finding_type=by_finding_type,
        by_extraction_status=by_status,
    )


def _value_node_id(kind: CorrelationKind, value_norm: str) -> str:
    digest = hashlib.sha256(f"{kind}:{value_norm}".encode()).hexdigest()[:16]
    return f"value:{kind}:{digest}"


def _label(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else url
    return _clip(name or url)


def _clip(value: str) -> str:
    text = value.strip()
    if len(text) <= _LABEL_MAX:
        return text
    return f"{text[: _LABEL_MAX - 3]}..."
