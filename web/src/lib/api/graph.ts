import { getJson, isObject } from "@/lib/api/client";
import type { GraphNodeKind } from "@/lib/api/types";

export type { GraphNodeKind };

export type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  label: string;
  url: string | null;
  asset_id: string | null;
  correlation_kind: string | null;
  extraction_status: string | null;
};

export type GraphEdge = {
  from_id: string;
  to_id: string;
  kind: string;
};

export type GraphLayer = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  notice: string | null;
};

export type GraphMetrics = {
  by_content_type: Record<string, number>;
  by_finding_type: Record<string, number>;
  by_extraction_status: Record<string, number>;
};

export type RunGraph = {
  run_id: string;
  crawl: GraphLayer;
  correlations: GraphLayer;
  metrics: GraphMetrics;
};

const NODE_KINDS = new Set<GraphNodeKind>(["page", "asset", "local_root", "value"]);

function isNode(value: unknown): value is GraphNode {
  if (!isObject(value) || typeof value.id !== "string" || typeof value.label !== "string") return false;
  return NODE_KINDS.has(value.kind as GraphNodeKind);
}

function isEdge(value: unknown): value is GraphEdge {
  return (
    isObject(value) &&
    typeof value.from_id === "string" &&
    typeof value.to_id === "string" &&
    typeof value.kind === "string"
  );
}

function isLayer(value: unknown): value is GraphLayer {
  return (
    isObject(value) &&
    Array.isArray(value.nodes) &&
    value.nodes.every(isNode) &&
    Array.isArray(value.edges) &&
    value.edges.every(isEdge) &&
    typeof value.truncated === "boolean"
  );
}

function isCountMap(value: unknown): value is Record<string, number> {
  if (!isObject(value)) return false;
  return Object.values(value).every((entry) => typeof entry === "number");
}

export function isRunGraph(value: unknown): value is RunGraph {
  if (!isObject(value) || typeof value.run_id !== "string") return false;
  if (!isLayer(value.crawl) || !isLayer(value.correlations)) return false;
  if (!isObject(value.metrics)) return false;
  return (
    isCountMap(value.metrics.by_content_type) &&
    isCountMap(value.metrics.by_finding_type) &&
    isCountMap(value.metrics.by_extraction_status)
  );
}

export function fetchRunGraph(runId: string): Promise<RunGraph> {
  return getJson(`/api/runs/${encodeURIComponent(runId)}/graph`, isRunGraph);
}

const KIND_FILTER_ORDER = [
  "email",
  "gps_point",
  "internal_endpoint",
  "software_version",
  "document_id",
  "device_serial",
  "author_string",
];

/** Distinct correlation kinds present as value nodes, in contract order. */
export function correlationKindsIn(layer: GraphLayer): string[] {
  const seen = new Set<string>();
  for (const node of layer.nodes) {
    if (node.kind === "value" && node.correlation_kind) seen.add(node.correlation_kind);
  }
  return KIND_FILTER_ORDER.filter((kind) => seen.has(kind)).concat(
    [...seen].filter((kind) => !KIND_FILTER_ORDER.includes(kind)).sort(),
  );
}

/** Keep one correlation kind and the assets still linked to those values. */
export function filterCorrelationLayer(layer: GraphLayer, kind: string | "all"): GraphLayer {
  if (kind === "all") return layer;
  const valueIds = new Set(
    layer.nodes
      .filter((node) => node.kind === "value" && node.correlation_kind === kind)
      .map((node) => node.id),
  );
  const edges = layer.edges.filter((edge) => valueIds.has(edge.from_id) || valueIds.has(edge.to_id));
  const keep = new Set(valueIds);
  for (const edge of edges) {
    keep.add(edge.from_id);
    keep.add(edge.to_id);
  }
  return {
    ...layer,
    nodes: layer.nodes.filter((node) => keep.has(node.id)),
    edges,
  };
}
