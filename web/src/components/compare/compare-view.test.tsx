import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { CompareView } from "./compare-view";

const comparison = {
  a: { run_id: "run-a", target: "acme.com", status: "completed", started_at: "2026-02-01T00:00:00Z", total_findings: 1 },
  b: { run_id: "run-b", target: "acme.com", status: "completed", started_at: "2026-03-01T00:00:00Z", total_findings: 2 },
  new: [],
  resolved: [
    {
      finding_id: "gone",
      run_id: "run-a",
      finding_type: "email",
      severity: "low",
      evidence_snippet: "old@acme.com",
      asset_url: "https://acme.com/a.pdf",
      triage_status: "open",
    },
  ],
  persistent: [],
  reappeared: [
    {
      finding_id: "back",
      run_id: "run-b",
      finding_type: "email",
      severity: "medium",
      evidence_snippet: "back@acme.com",
      asset_url: "https://acme.com/a.pdf",
      triage_status: "open",
      prior_run_id: "run-0",
    },
  ],
  severity_changed: [
    {
      finding_id: "kept",
      run_id: "run-b",
      finding_type: "email",
      severity: "high",
      previous_severity: "medium",
      evidence_snippet: "kept@acme.com",
      asset_url: "https://acme.com/a.pdf",
      triage_status: "open",
    },
  ],
  limits_hit_a: [],
  limits_hit_b: ["max_pages"],
  coverage_recorded_a: true,
  coverage_recorded_b: true,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("CompareView", () => {
  it("separates a returning finding from a severity change and names the crawl limit", async () => {
    window.history.replaceState(null, "", "/runs/compare?a=run-a&b=run-b");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/runs")) {
          return new Response(JSON.stringify({ runs: [], total: 0 }), { status: 200 });
        }
        return new Response(JSON.stringify(comparison), { status: 200 });
      }),
    );
    renderWithProviders(<CompareView />);
    expect(await screen.findByRole("region", { name: "Reappeared" })).toBeInTheDocument();
    expect(screen.getByText("back@acme.com")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Severity changed" })).toBeInTheDocument();
    expect(screen.getByText(/Severity changed from Medium to High/i)).toBeInTheDocument();
    expect(screen.getByText(/page cap/i)).toBeInTheDocument();
    expect(screen.getByText(/may not have been requested/i)).toBeInTheDocument();
  });
});
