import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";
import { renderWithProviders as render } from "@/test/render";

vi.mock("cytoscape", () => ({
  default: vi.fn(() => ({
    container: () => ({ style: { setProperty: vi.fn() } }),
    on: vi.fn(),
    destroy: vi.fn(),
    resize: vi.fn(),
    fit: vi.fn(),
    zoom: vi.fn(() => 1),
    center: vi.fn(),
    width: () => 0,
    height: () => 0,
    pan: vi.fn(),
    nodes: () => ({ length: 0, forEach() {} }),
    elements: () => ({
      addClass: vi.fn(),
      removeClass: vi.fn(),
      boundingBox: () => ({ x1: 0, y1: 0, w: 0, h: 0 }),
    }),
  })),
}));

import { LiveScanGraph } from "./live-scan-graph";

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
  vi.unstubAllGlobals();
});

function stubGraph(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }
      if (url.includes("/api/runs/run-1") && !url.includes("/graph")) {
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            status: "running",
            target: "example.com",
            scope: ["example.com"],
            reasoning_depth: "standard",
            total_assets: 0,
            total_findings: 0,
            error_message: null,
            completed_at: null,
            asset_issues: [],
          }),
          { status: 200 },
        );
      }
      if (url.includes("/graph")) {
        return new Response(JSON.stringify(body), { status });
      }
      return new Response("{}", { status: 404 });
    }),
  );
}

describe("LiveScanGraph", () => {
  it("shows empty copy when the crawl has no edges yet", async () => {
    stubGraph({
      run_id: "run-1",
      crawl: { nodes: [], edges: [], truncated: false, notice: null },
      correlations: { nodes: [], edges: [], truncated: false, notice: null },
      metrics: { by_content_type: {}, by_finding_type: {}, by_extraction_status: {} },
    });
    render(
      <RunWorkspaceShell runId="run-1">
        <LiveScanGraph runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("region", { name: "Grafos del escaneo" })).toBeInTheDocument();
    expect(screen.getByText("Aún no hay conexiones")).toBeInTheDocument();
  });

  it("offers a kind filter when the scan has more than one shared-value type", async () => {
    stubGraph({
      run_id: "run-1",
      crawl: { nodes: [], edges: [], truncated: false, notice: null },
      correlations: {
        nodes: [
          {
            id: "value:mail",
            kind: "value",
            label: "ada@example.com",
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
        ],
        edges: [{ from_id: "asset:a", to_id: "value:mail", kind: "email" }],
        truncated: false,
        notice: null,
      },
      metrics: { by_content_type: {}, by_finding_type: {}, by_extraction_status: {} },
    });
    render(
      <RunWorkspaceShell runId="run-1">
        <LiveScanGraph runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("group", { name: "Tipo de valor compartido" })).toBeInTheDocument();
    expect(screen.getAllByRole("list", { name: "Leyenda del grafo" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Valor")).toBeInTheDocument();
    expect(screen.getAllByText("Documento").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Correo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Versión de software" })).toBeInTheDocument();
  });
});
