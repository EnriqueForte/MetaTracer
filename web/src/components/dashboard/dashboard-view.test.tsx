import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { DashboardView } from "@/components/dashboard/dashboard-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function statsPayload(runsTotal: number) {
  return {
    runs: { total: runsTotal, completed: runsTotal, failed: 0 },
    assets: { total: 4, with_issues: 1 },
    findings: {
      total: 10,
      unclassified: 2,
      severity_breakdown: { critical: 1, high: 4, medium: 3, low: 0, info: 0, unclassified: 2 },
      by_type: { gps: 4, email: 6 },
    },
    top_domains: [{ domain: "example.com", count: 3 }],
    top_evidence: [
      {
        signature: "abc",
        evidence_snippet: "Latitude: 1",
        finding_type: "gps",
        occurrences: 2,
      },
    ],
    agent_usage: {
      calls: 1,
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
      latency_ms: 20,
    },
  };
}

function stubStats(runsTotal: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(statsPayload(runsTotal)), { status: 200 })),
  );
}

function swatchClass(label: string): string {
  const item = screen.getByText(label).closest("li");
  return item?.querySelector("[data-swatch]")?.className ?? "";
}

function barClass(label: string): string {
  const row = screen.getByText(label).closest("[data-chart-row]");
  return row?.querySelector("[data-bar]")?.className ?? "";
}

describe("DashboardView", () => {
  it("paints severity with its own color and keeps agent usage in a strip", async () => {
    stubStats(2);
    render(<DashboardView />);
    expect(await screen.findByText("Completados 2 · Fallidos 0")).toBeInTheDocument();
    expect(swatchClass("Crítica")).toContain("bg-mt-sev-critical");
    expect(swatchClass("Alta")).toContain("bg-mt-sev-high");
    expect(swatchClass("Crítica")).not.toContain("bg-mt-accent");
    expect(barClass("Correo")).toContain("bg-mt-chart-2");
    expect(screen.getByRole("img", { name: "10 hallazgos" })).toBeInTheDocument();
    expect(screen.getByText("example.com")).toBeInTheDocument();
    expect(screen.getByText(/2 hallazgos sin severidad/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir escaneos completados" })).toHaveAttribute(
      "href",
      "/runs?status=completed",
    );
    expect(screen.getByRole("link", { name: "Abrir comparación" })).toHaveAttribute("href", "/runs/compare");
    expect(screen.getByText("Latitude: 1")).toBeInTheDocument();
    expect(screen.getByText("Uso de IA")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Uso del agente" })).not.toBeInTheDocument();
  });

  it("sends failed scans to the failed history filter", async () => {
    const payload = statsPayload(3);
    payload.runs.failed = 2;
    payload.findings.unclassified = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })),
    );
    render(<DashboardView />);
    expect(await screen.findByRole("link", { name: "Revisar escaneos fallidos" })).toHaveAttribute(
      "href",
      "/runs?status=failed",
    );
  });

  it("shows a single empty state when there are no runs", async () => {
    stubStats(0);
    render(<DashboardView />);
    expect(await screen.findByText("Aún no hay escaneos")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar el primer escaneo" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: "Nuevo escaneo" })).not.toBeInTheDocument();
    expect(screen.queryByText("Completados 0 · Fallidos 0")).not.toBeInTheDocument();
  });

  it("renders hostile evidence and domains as text", async () => {
    const payload = statsPayload(1);
    payload.top_evidence[0].evidence_snippet = "<img src=x onerror=alert(1)>";
    payload.top_domains[0].domain = "<script>alert(1)</script>";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })),
    );
    const { container } = render(<DashboardView />);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
