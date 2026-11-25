import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GraphLayer, GraphNode } from "@/lib/api/graph";

type CytoscapeMount = {
  elements?: Array<{ data?: { kind?: string }; position?: { x: number; y: number } }>;
};

const { cytoscapeMock } = vi.hoisted(() => {
  const cytoscapeMock = vi.fn((_options?: CytoscapeMount) => ({
    container: () => ({ style: { setProperty: vi.fn() } }),
    on: vi.fn(),
    destroy: vi.fn(),
    resize: vi.fn(),
    fit: vi.fn(),
    zoom: vi.fn((_level?: number) => 1),
    center: vi.fn(),
    width: vi.fn(() => 0),
    height: vi.fn(() => 0),
    pan: vi.fn(),
    getElementById: () => ({ position: vi.fn() }),
    layout: () => ({ run: vi.fn() }),
    nodes: () => ({ length: 0, forEach() {} }),
    elements: () => ({
      addClass: vi.fn(),
      removeClass: vi.fn(),
      boundingBox: () => ({ x1: 0, y1: 0, w: 0, h: 0 }),
    }),
    connectedEdges: () => ({ addClass: vi.fn() }),
  }));
  return { cytoscapeMock };
});

vi.mock("cytoscape", () => ({ default: cytoscapeMock }));

import { NetworkGraph, shortGraphLabel } from "./network-graph";

beforeEach(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as typeof ResizeObserver;
  }
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const layer: GraphLayer = {
  nodes: [
    {
      id: "page:https://example.com/",
      kind: "page",
      label: "https://example.com/",
      url: "https://example.com/",
      asset_id: null,
      correlation_kind: null,
      extraction_status: null,
    },
    {
      id: "asset:doc-1",
      kind: "asset",
      label: "https://example.com/a.pdf",
      url: "https://example.com/a.pdf",
      asset_id: "doc-1",
      correlation_kind: null,
      extraction_status: "ok",
    },
  ],
  edges: [{ from_id: "page:https://example.com/", to_id: "asset:doc-1", kind: "document" }],
  truncated: false,
  notice: null,
};

describe("shortGraphLabel", () => {
  it("keeps a shared value and uses the URL basename for assets", () => {
    const value: GraphNode = {
      id: "v",
      kind: "value",
      label: "redaccion@puertomontevideo.example",
      url: null,
      asset_id: null,
      correlation_kind: "email",
      extraction_status: null,
    };
    const asset: GraphNode = {
      id: "a",
      kind: "asset",
      label: "https://example.com/docs/acta.html",
      url: "https://example.com/docs/acta.html",
      asset_id: "doc-1",
      correlation_kind: null,
      extraction_status: "ok",
    };
    expect(shortGraphLabel(value)).toBe("redaccion@puertomontevideo.…");
    expect(shortGraphLabel(asset)).toBe("acta.html");
    expect(
      shortGraphLabel({
        ...value,
        label: "un-valor-compartido-muy-largo-que-no-cabe-entero-en-el-canvas",
      }),
    ).toMatch(/…$/);
  });
});

describe("NetworkGraph", () => {
  it("mounts cytoscape with a non-animated built-in layout", () => {
    render(
      <NetworkGraph layer={layer} layout="breadthfirst" label="Grafo de descubrimiento" onSelect={() => undefined} />,
    );
    expect(screen.getByRole("img", { name: "Grafo de descubrimiento" })).toBeInTheDocument();
    expect(cytoscapeMock).toHaveBeenCalledTimes(1);
    expect(cytoscapeMock).toHaveBeenCalledWith(
      expect.objectContaining({
        layout: expect.objectContaining({
          name: "breadthfirst",
          animate: false,
          spacingFactor: 1.45,
          boundingBox: expect.objectContaining({ w: expect.any(Number) }),
        }),
        pixelRatio: "auto",
        style: expect.arrayContaining([
          expect.objectContaining({
            selector: "node",
            style: expect.objectContaining({
              "font-family": expect.stringMatching(/mono|Cascadia|Consolas/i),
              "font-weight": 600,
            }),
          }),
        ]),
      }),
    );
  });

  it("caps the crawl bounding box to a 1920 content column on an ultrawide host", () => {
    const width = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
    const height = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 3200 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 640 });
    try {
      render(
        <NetworkGraph layer={layer} layout="breadthfirst" label="Grafo de descubrimiento" onSelect={() => undefined} />,
      );
      expect(cytoscapeMock).toHaveBeenCalledWith(
        expect.objectContaining({
          layout: expect.objectContaining({ boundingBox: expect.objectContaining({ w: 1600, h: 640 }) }),
        }),
      );
    } finally {
      if (width) Object.defineProperty(HTMLElement.prototype, "clientWidth", width);
      else delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth;
      if (height) Object.defineProperty(HTMLElement.prototype, "clientHeight", height);
      else delete (HTMLElement.prototype as { clientHeight?: number }).clientHeight;
    }
  });

  it("frames the crawl graph from the labelled bounding box so edge names stay inside", () => {
    const boundingBox = vi.fn(() => ({ x1: 0, y1: 0, w: 1000, h: 400 }));
    const zoom = vi.fn((_level?: number) => 1);
    const pan = vi.fn((_position?: { x: number; y: number }) => undefined);
    cytoscapeMock.mockImplementationOnce(() => ({
      container: () => ({ style: { setProperty: vi.fn() } }),
      on: vi.fn(),
      destroy: vi.fn(),
      resize: vi.fn(),
      fit: vi.fn(),
      zoom,
      center: vi.fn(),
      width: vi.fn(() => 800),
      height: vi.fn(() => 640),
      pan,
      getElementById: () => ({ position: vi.fn() }),
      layout: () => ({ run: vi.fn() }),
      nodes: () => ({ length: 0, forEach() {} }),
      elements: () => ({ addClass: vi.fn(), removeClass: vi.fn(), boundingBox }),
      connectedEdges: () => ({ addClass: vi.fn() }),
    }));
    render(
      <NetworkGraph layer={layer} layout="breadthfirst" label="Grafo de descubrimiento" onSelect={() => undefined} />,
    );
    expect(boundingBox).toHaveBeenCalledWith({ includeLabels: true });
    expect(zoom.mock.calls[0]?.[0]).toBeCloseTo(0.752);
    expect(pan.mock.calls[0]?.[0]).toEqual({
      x: expect.closeTo(24),
      y: expect.closeTo(169.6),
    });
  });

  it("lays out shared values above assets in a wrapping grid, not two tall columns", () => {
    const correlated: GraphLayer = {
      nodes: [
        {
          id: "value:mail",
          kind: "value",
          label: "redaccion@example.com",
          url: null,
          asset_id: null,
          correlation_kind: "email",
          extraction_status: null,
        },
        {
          id: "value:ver",
          kind: "value",
          label: "wordpress 6.4.2",
          url: null,
          asset_id: null,
          correlation_kind: "software_version",
          extraction_status: null,
        },
        {
          id: "asset:a",
          kind: "asset",
          label: "https://example.com/a.pdf",
          url: "https://example.com/a.pdf",
          asset_id: "a",
          correlation_kind: null,
          extraction_status: "ok",
        },
        {
          id: "asset:b",
          kind: "asset",
          label: "https://example.com/b.pdf",
          url: "https://example.com/b.pdf",
          asset_id: "b",
          correlation_kind: null,
          extraction_status: "ok",
        },
      ],
      edges: [
        { from_id: "asset:a", to_id: "value:mail", kind: "email" },
        { from_id: "asset:b", to_id: "value:ver", kind: "software_version" },
      ],
      truncated: false,
      notice: null,
    };
    render(
      <NetworkGraph layer={correlated} layout="cose" label="Grafo de correlación" onSelect={() => undefined} />,
    );
    expect(cytoscapeMock).toHaveBeenCalledWith(
      expect.objectContaining({
        layout: expect.objectContaining({ name: "preset", animate: false }),
      }),
    );
    const mounted = cytoscapeMock.mock.calls[0]?.[0];
    const values = (mounted?.elements ?? []).filter((entry) => entry.data?.kind === "value" && entry.position);
    const assets = (mounted?.elements ?? []).filter((entry) => entry.data?.kind === "asset" && entry.position);
    expect(Math.max(...values.map((entry) => entry.position!.y))).toBeLessThan(
      Math.min(...assets.map((entry) => entry.position!.y)),
    );
    expect(new Set(values.map((entry) => entry.position!.x)).size).toBeGreaterThan(1);
    expect(new Set(assets.map((entry) => entry.position!.x)).size).toBeGreaterThan(1);
    const valueSpan =
      Math.max(...values.map((entry) => entry.position!.x)) - Math.min(...values.map((entry) => entry.position!.x));
    expect(valueSpan).toBeGreaterThan(400);
  });
});
