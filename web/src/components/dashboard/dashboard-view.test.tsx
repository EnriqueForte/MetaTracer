import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    expect(await screen.findByText("Completed 2 · Failed 0")).toBeInTheDocument();
    expect(swatchClass("Critical")).toContain("bg-mt-sev-critical");
    expect(swatchClass("High")).toContain("bg-mt-sev-high");
    expect(swatchClass("Critical")).not.toContain("bg-mt-accent");
    expect(barClass("Email")).toContain("bg-mt-chart-2");
    expect(screen.getByRole("img", { name: "10 findings" })).toBeInTheDocument();
    expect(screen.getByText("example.com")).toBeInTheDocument();
    expect(screen.getByText("Latitude: 1")).toBeInTheDocument();
    const agent = screen.getByRole("region", { name: "Agent usage" });
    expect(agent).toHaveTextContent("Calls 1");
    expect(agent.className).not.toContain("text-2xl");
  });

  it("shows a single empty state when there are no runs", async () => {
    stubStats(0);
    render(<DashboardView />);
    expect(await screen.findByText(/No data yet/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "New scan" })).toHaveLength(1);
    expect(screen.queryByText("Completed 0 · Failed 0")).not.toBeInTheDocument();
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
