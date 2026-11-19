import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

vi.mock("@/components/run/graph/live-scan-graph", () => ({
  LiveScanGraph: () => <section aria-label="Grafos del escaneo" />,
}));

import { RunProgress } from "@/components/run/run-progress";
import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";

type FakeSource = {
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  close: () => void;
};

let source: FakeSource | null = null;

class FakeEventSource {
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    source = this;
  }
  close() {}
}

afterEach(() => {
  cleanup();
  source = null;
  vi.unstubAllGlobals();
});

function runBody(status: string, extra: Record<string, unknown> = {}) {
  return {
    run_id: "run-1",
    status,
    target: "example.com",
    scope: ["example.com"],
    reasoning_depth: "standard",
    total_assets: 1,
    total_findings: 0,
    error_message: null,
    completed_at: status === "completed" ? "2026-09-29T12:00:00Z" : null,
    asset_issues: [],
    ...extra,
  };
}

function stub(status: string, role?: "operator" | "viewer") {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        if (!role) {
          return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
        }
        return new Response(
          JSON.stringify({ authenticated: true, username: "ada", role }),
          { status: 200 },
        );
      }
      if (url.includes("/abort")) {
        return new Response(JSON.stringify(runBody("aborted")), { status: 200 });
      }
      if (url.includes("/findings")) {
        return new Response(JSON.stringify({ findings: [] }), { status: 200 });
      }
      if (url.includes("/correlations")) {
        return new Response(JSON.stringify({ run_id: "run-1", total: 0, groups: [] }), { status: 200 });
      }
      if (url.includes("/graph")) {
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            crawl: { nodes: [], edges: [], truncated: false, notice: null },
            correlations: { nodes: [], edges: [], truncated: false, notice: null },
            metrics: { by_content_type: {}, by_finding_type: {}, by_extraction_status: {} },
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify(runBody(status)), { status: 200 });
    }),
  );
}

describe("RunProgress", () => {
  it("shows a live activity panel that follows stored counts and stream steps", async () => {
    stub("running");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    const panel = await screen.findByRole("region", { name: "Actividad del escaneo" });
    expect(await screen.findByRole("region", { name: "Grafos del escaneo" })).toBeInTheDocument();
    expect(panel).toHaveTextContent("Leyendo documentos guardados");
    expect(panel).toHaveTextContent("Documentos");
    expect(panel).toHaveTextContent("1");
    expect(screen.queryByRole("list", { name: "Progress" })).not.toBeInTheDocument();
    await act(async () => {
      source?.onmessage?.({
        data: JSON.stringify({
          stage: "discovery",
          message: "Crawling",
          current_asset: "https://example.com/a",
          current_step: 2,
          total_steps: 7,
        }),
      });
    });
    expect(panel).toHaveTextContent("Descubrimiento");
    expect(panel).toHaveTextContent("Crawling");
    expect(panel).toHaveTextContent("https://example.com/a");
    await act(async () => {
      source?.onmessage?.({
        data: JSON.stringify({
          stage: "downloading",
          message: "Fetching documents",
          current_asset: null,
          current_step: 3,
          total_steps: 7,
        }),
      });
    });
    expect(panel).toHaveTextContent("Descarga");
    expect(panel).toHaveTextContent("Fetching documents");
    expect(panel).not.toHaveTextContent("Crawling");
    // Progress is the server's step over the pipeline total, not a decorative
    // sweep: the bar exposes it to assistive tech.
    const bar = screen.getByRole("progressbar", { name: "Progreso del escaneo" });
    expect(bar).toHaveAttribute("aria-valuenow", "3");
    expect(bar).toHaveAttribute("aria-valuemax", "7");
    expect(bar).toHaveAttribute("aria-valuetext", "Paso 3 de 7");
  });

  it("names classification when the stream reports that step", async () => {
    stub("running");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    const panel = await screen.findByRole("region", { name: "Actividad del escaneo" });
    await act(async () => {
      source?.onmessage?.({
        data: JSON.stringify({
          stage: "ai_analysis",
          message: "Classifying",
          current_asset: null,
          current_step: 6,
          total_steps: 7,
        }),
      });
    });
    expect(panel).toHaveTextContent("Clasificación y análisis con IA");
    expect(panel).toHaveTextContent("Classifying");
  });

  it("shows shared values on a finished run", async () => {
    stub("completed");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("region", { name: "Valores compartidos" })).toBeInTheDocument();
    expect(screen.getByText("Ningún valor compartido")).toBeInTheDocument();
    expect(screen.getByText("Ningún valor enlaza este escaneo con otro activo.")).toBeInTheDocument();
  });

  it("puts the five exports in the run bar", async () => {
    stub("completed");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("link", { name: "Descargar Markdown" })).toHaveAttribute(
      "href",
      "/api/runs/run-1/export?format=md&redact=contacts",
    );
    expect(screen.getByRole("link", { name: "Descargar JSON" })).toHaveAttribute(
      "href",
      "/api/runs/run-1/export?format=json&redact=contacts",
    );
    expect(screen.getByRole("link", { name: "Descargar HTML" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Descargar CSV" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Descargar Bounty TXT" })).toBeInTheDocument();
    expect(screen.getByLabelText("Redacción")).toHaveValue("contacts");
    expect(screen.getByText("El fichero del informe se regenera en el servidor.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reports" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Actividad del escaneo" })).not.toBeInTheDocument();
  });

  it("shows Abort scan only for an operator while the run is active", async () => {
    stub("running", "operator");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Abortar escaneo" }));
    expect(await screen.findByRole("heading", { name: "¿Abortar este escaneo?" })).toBeInTheDocument();
  });

  it("hides Abort scan from a viewer", async () => {
    stub("running", "viewer");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByText("En curso")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abortar escaneo" })).not.toBeInTheDocument();
  });

  it("hides Delete run from a viewer on a finished run", async () => {
    stub("completed", "viewer");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("link", { name: "Descargar Markdown" })).toBeInTheDocument();
    await screen.findByText("Completado");
    expect(screen.queryByRole("button", { name: "Eliminar escaneo" })).not.toBeInTheDocument();
  });

  it("links Comparar to the previous same-scope run when the API names it", async () => {
    stub("completed");
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }
      if (url.includes("/findings")) {
        return new Response(JSON.stringify({ findings: [] }), { status: 200 });
      }
      if (url.includes("/correlations")) {
        return new Response(JSON.stringify({ run_id: "run-1", total: 0, groups: [] }), { status: 200 });
      }
      if (url.includes("/graph")) {
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            crawl: { nodes: [], edges: [], truncated: false, notice: null },
            correlations: { nodes: [], edges: [], truncated: false, notice: null },
            metrics: { by_content_type: {}, by_finding_type: {}, by_extraction_status: {} },
          }),
          { status: 200 },
        );
      }
      return new Response(
        JSON.stringify(runBody("completed", { previous_run_id: "run-0" })),
        { status: 200 },
      );
    });
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("link", { name: "Comparar" })).toHaveAttribute(
      "href",
      "/runs/compare?b=run-1&a=run-0",
    );
  });

  it("hides Abort scan once the run is completed", async () => {
    stub("completed", "operator");
    render(
      <RunWorkspaceShell runId="run-1">
        <RunProgress runId="run-1" />
      </RunWorkspaceShell>,
    );
    expect(await screen.findByRole("link", { name: "Descargar Markdown" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abortar escaneo" })).not.toBeInTheDocument();
  });
});
