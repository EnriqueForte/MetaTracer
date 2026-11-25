"use client";

import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

import type { GraphLayer, GraphNode } from "@/lib/api/graph";

const KIND_COLOR: Record<string, string> = {
  page: "--mt-chart-2",
  asset: "--mt-chart-1",
  local_root: "--mt-chart-3",
  value: "--mt-chart-4",
};

const KIND_SHAPE: Record<string, string> = {
  page: "round-octagon",
  asset: "ellipse",
  local_root: "barrel",
  value: "round-tag",
};

const MONO_STACK = "Cascadia Code, IBM Plex Mono, ui-monospace, Consolas, monospace";

const KIND_ORDER = [
  "email",
  "gps_point",
  "internal_endpoint",
  "software_version",
  "document_id",
  "device_serial",
  "author_string",
];

const LABEL_MAX = 28;
const MIN_SLOT = 176;
const VALUE_ROW = 92;
const ASSET_ROW = 100;
const PAD = 56;
const FALLBACK_BOX = { width: 960, height: 520 };
/** Content column of a 1920×1080 shell (sidebar 232 + paddings). */
const NORMAL_CANVAS_WIDTH = 1600;

/** Canvas label: basename of a URL, truncated shared value. Full text stays in the payload. */
export function shortGraphLabel(entry: GraphNode): string {
  const raw = entry.label.trim();
  if (entry.kind === "value") {
    return raw.length > LABEL_MAX ? `${raw.slice(0, LABEL_MAX - 1)}…` : raw;
  }
  try {
    const url = new URL(raw);
    const leaf = url.pathname.split("/").filter(Boolean).pop();
    return leaf || url.host || raw;
  } catch {
    const leaf = raw.split(/[/\\]/).filter(Boolean).pop();
    return leaf || raw;
  }
}

function cssToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function nodeData(entry: GraphNode) {
  return {
    id: entry.id,
    label: shortGraphLabel(entry),
    kind: entry.kind,
    color: cssToken(KIND_COLOR[entry.kind] ?? "--mt-chart-1", "#6ad6ea"),
    shape: KIND_SHAPE[entry.kind] ?? "ellipse",
    payload: entry,
  };
}

function viewportOf(element: HTMLElement): { width: number; height: number } {
  const width = element.clientWidth > 0 ? element.clientWidth : FALLBACK_BOX.width;
  return {
    width: Math.min(width, NORMAL_CANVAS_WIDTH),
    height: element.clientHeight > 0 ? element.clientHeight : FALLBACK_BOX.height,
  };
}

function crawlLayout(box: { width: number; height: number }): cytoscape.LayoutOptions {
  return {
    name: "breadthfirst",
    animate: false,
    fit: true,
    padding: 24,
    directed: true,
    spacingFactor: 1.45,
    boundingBox: { x1: 0, y1: 0, w: box.width, h: box.height },
  };
}

function frameGraph(cy: cytoscape.Core, padding: number, zoomBoost = 1) {
  cy.resize();
  const bb = cy.elements().boundingBox({ includeLabels: true });
  const viewW = cy.width();
  const viewH = cy.height();
  const boxW = bb.w;
  const boxH = bb.h;
  if (!(boxW > 0 && boxH > 0 && viewW > 0 && viewH > 0)) {
    cy.fit(undefined, padding);
    if (zoomBoost === 1) return;
    cy.zoom(cy.zoom() * zoomBoost);
    cy.center();
    return;
  }
  const innerW = Math.max(viewW - padding * 2, 1);
  const innerH = Math.max(viewH - padding * 2, 1);
  const maxZoom = Math.min(innerW / boxW, innerH / boxH);
  const zoom = maxZoom * zoomBoost;
  cy.zoom(zoom);
  cy.pan({
    x: padding + (innerW - boxW * zoom) / 2 - bb.x1 * zoom,
    y: padding + (innerH - boxH * zoom) / 2 - bb.y1 * zoom,
  });
}

function kindRank(kind: string | null): number {
  const index = KIND_ORDER.indexOf(kind ?? "");
  return index === -1 ? KIND_ORDER.length : index;
}

function columnCount(itemCount: number, usable: number): number {
  return Math.max(1, Math.min(itemCount, Math.floor(usable / MIN_SLOT) || 1));
}

function slotXs(cols: number, width: number): number[] {
  const usable = Math.max(width - PAD * 2, MIN_SLOT);
  if (cols <= 1) return [width / 2];
  return Array.from({ length: cols }, (_, index) => PAD + (index / (cols - 1)) * usable);
}

function spreadGrid(
  items: GraphNode[],
  originY: number,
  rowHeight: number,
  width: number,
): cytoscape.ElementDefinition[] {
  const cols = columnCount(items.length, Math.max(width - PAD * 2, MIN_SLOT));
  const xs = slotXs(cols, width);
  const rows = Math.ceil(items.length / cols) || 1;
  const lastCount = items.length % cols || cols;
  return items.map((entry, index) => {
    const row = Math.floor(index / cols);
    const col = index % cols;
    const centered = row === rows - 1 && lastCount < cols ? Math.floor((cols - lastCount) / 2) : 0;
    return {
      data: nodeData(entry),
      position: { x: xs[col + centered] ?? xs[col] ?? width / 2, y: originY + row * rowHeight },
    };
  });
}

function correlationLayout(
  layer: GraphLayer,
  box: { width: number; height: number },
): {
  layout: cytoscape.LayoutOptions;
  nodes: cytoscape.ElementDefinition[];
} {
  const values = layer.nodes.filter((entry) => entry.kind === "value");
  const rest = layer.nodes.filter((entry) => entry.kind !== "value");
  if (values.length === 0) {
    return {
      layout: {
        name: "cose",
        animate: false,
        fit: true,
        padding: 28,
        randomize: false,
        nodeRepulsion: () => 14000,
        idealEdgeLength: () => 160,
        nodeOverlap: 40,
        gravity: 0.18,
        numIter: 1400,
        componentSpacing: 120,
        boundingBox: { x1: 0, y1: 0, w: box.width, h: box.height },
      },
      nodes: layer.nodes.map((entry) => ({ data: nodeData(entry) })),
    };
  }
  const degree = new Map<string, number>();
  for (const edge of layer.edges) {
    degree.set(edge.from_id, (degree.get(edge.from_id) ?? 0) + 1);
    degree.set(edge.to_id, (degree.get(edge.to_id) ?? 0) + 1);
  }
  const sortedValues = [...values].sort((left, right) => {
    const kind = kindRank(left.correlation_kind) - kindRank(right.correlation_kind);
    if (kind !== 0) return kind;
    const connected = (degree.get(right.id) ?? 0) - (degree.get(left.id) ?? 0);
    if (connected !== 0) return connected;
    return left.label.localeCompare(right.label);
  });
  const sortedAssets = [...rest].sort((left, right) => left.label.localeCompare(right.label));
  const width = Math.max(box.width, FALLBACK_BOX.width);
  const height = Math.max(box.height, FALLBACK_BOX.height);
  const usable = Math.max(width - PAD * 2, MIN_SLOT);
  const valueRows = Math.ceil(sortedValues.length / columnCount(sortedValues.length, usable)) || 1;
  const assetRows = Math.ceil(sortedAssets.length / columnCount(sortedAssets.length, usable)) || 1;
  const valuesHeight = valueRows * VALUE_ROW;
  const assetsHeight = assetRows * ASSET_ROW;
  const band = Math.max(140, height - PAD * 2 - valuesHeight - assetsHeight);
  return {
    layout: { name: "preset", fit: true, padding: 24, animate: false },
    nodes: [
      ...spreadGrid(sortedValues, PAD, VALUE_ROW, width),
      ...spreadGrid(sortedAssets, PAD + valuesHeight + band, ASSET_ROW, width),
    ],
  };
}

export function NetworkGraph({
  layer,
  layout,
  label,
  onSelect,
}: {
  layer: GraphLayer;
  layout: "breadthfirst" | "cose";
  label: string;
  onSelect: (node: GraphNode | null) => void;
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = host.current;
    if (!node || layer.nodes.length === 0) return;
    const fg = cssToken("--mt-fg", "#eaeff6");
    const border = cssToken("--mt-border", "#1c2430");
    const strong = cssToken("--mt-border-strong", "#5c6e84");
    const accent = cssToken("--mt-accent", "#3cc4dc");
    const bg = cssToken("--mt-bg", "#06080c");
    const elevated = cssToken("--mt-elevated", "#131a24");
    const mono = cssToken("--mt-font-mono", MONO_STACK) || MONO_STACK;
    const box = viewportOf(node);
    const built =
      layout === "cose"
        ? correlationLayout(layer, box)
        : { layout: crawlLayout(box), nodes: layer.nodes.map((entry) => ({ data: nodeData(entry) })) };
    const correlated = layout === "cose";
    const cy = cytoscape({
      container: node,
      elements: [
        ...built.nodes,
        ...layer.edges.map((edge, index) => ({
          data: {
            id: `e-${index}-${edge.from_id}-${edge.to_id}`,
            source: edge.from_id,
            target: edge.to_id,
          },
        })),
      ],
      layout: built.layout,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            color: fg,
            "font-family": mono,
            "font-size": correlated ? 12 : 13,
            "font-weight": 600,
            "text-wrap": correlated ? "ellipsis" : "wrap",
            "text-max-width": correlated ? "170px" : "120px",
            "text-valign": "bottom",
            "text-margin-y": correlated ? 8 : 9,
            "text-background-color": bg,
            "text-background-opacity": 0.92,
            "text-background-padding": "3px",
            "text-background-shape": "roundrectangle",
            "min-zoomed-font-size": correlated ? 8 : 10,
            "background-color": "data(color)",
            "border-width": 1,
            "border-color": border,
            // Cytoscape maps this at runtime; the bundled types only list NodeShape literals.
            shape: "data(shape)" as cytoscape.Css.Node["shape"],
            width: correlated ? 26 : 22,
            height: correlated ? 26 : 22,
          },
        },
        {
          selector: 'node[kind = "value"]',
          style: {
            "background-color": elevated,
            "border-width": 2,
            "border-color": "data(color)",
          },
        },
        {
          selector: "node.hot",
          style: {
            "border-width": 2,
            "border-color": accent,
            width: 32,
            height: 32,
          },
        },
        {
          selector: ".faded",
          style: { opacity: 0.12 },
        },
        {
          selector: "edge",
          style: correlated
            ? {
                width: 1.15,
                "line-color": strong,
                "curve-style": "haystack",
                "haystack-radius": 0.55,
                opacity: layer.edges.length > 18 ? 0.32 : 0.5,
              }
            : {
                width: 1.5,
                "line-color": strong,
                "target-arrow-color": strong,
                "target-arrow-shape": "triangle",
                "curve-style": "bezier",
                "arrow-scale": 0.9,
                opacity: 0.72,
              },
        },
        {
          selector: "edge.hot",
          style: {
            opacity: 1,
            "line-color": accent,
            "target-arrow-color": accent,
          },
        },
      ],
      minZoom: 0.2,
      maxZoom: 3,
      textureOnViewport: false,
      pixelRatio: "auto",
    });
    cy.container()?.style.setProperty("background", bg);
    frameGraph(cy, 24);
    cy.on("tap", "node", (event) => {
      const payload = event.target.data("payload") as GraphNode | undefined;
      onSelect(payload ?? null);
    });
    cy.on("tap", (event) => {
      if (event.target === cy) onSelect(null);
    });
    cy.on("mouseover", "node", (event) => {
      const target = event.target;
      cy.elements().addClass("faded");
      target.removeClass("faded").neighborhood().removeClass("faded");
      target.addClass("hot");
      target.connectedEdges().addClass("hot");
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("faded hot");
    });
    const observer = new ResizeObserver(() => {
      if (correlated) {
        const placed = correlationLayout(layer, viewportOf(node));
        for (const entry of placed.nodes) {
          const id = entry.data.id;
          if (typeof id !== "string" || !entry.position) continue;
          cy.getElementById(id).position(entry.position);
        }
        frameGraph(cy, 24);
        return;
      }
      frameGraph(cy, 24);
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
      cy.destroy();
    };
  }, [layer, layout, onSelect]);

  if (layer.nodes.length === 0) return null;

  return <div ref={host} className="mt-graph-canvas mt-graph-canvas-network" role="img" aria-label={label} />;
}
