import { cleanup, fireEvent, render as plainRender, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { CompareView } from "@/components/compare/compare-view";
import { SeverityTrend, type TrendPoint } from "@/components/dashboard/severity-trend";
import { GpsMap, parseGpsLine } from "@/components/run/findings/gps-map";
import type { Finding } from "@/components/run/findings/model";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function gps(id: string, snippet: string): Finding {
  return {
    id,
    title: `GPS ${id}`,
    finding_type: "gps",
    type_label: "GPS",
    severity: "high",
    confidence: "high",
    field_source: "EXIF:GPSInfo",
    evidence_snippet: snippet,
    asset_source_url: "https://acme.com/p.jpg",
    asset_final_url: "https://acme.com/p.jpg",
    asset_content_type: "image/jpeg",
    severity_justification: "",
    impact_analysis: "",
    remediation_advice: "",
    reproduction_steps: [],
    triage_status: "open",
  };
}

describe("GPS map (TASK-35)", () => {
  it("parses only well-formed, in-range, non-null-island lines", () => {
    expect(parseGpsLine("Latitude: 40.416775, Longitude: -3.703790")).toEqual({ lat: 40.416775, lon: -3.70379 });
    expect(parseGpsLine("Latitude: 40.4, Longitude: -3.7, Altitude: 650")).not.toBeNull();
    expect(parseGpsLine("Latitude: 0.000001, Longitude: 0.000001")).toBeNull();
    expect(parseGpsLine("Latitude: 95, Longitude: 0")).toBeNull();
    expect(parseGpsLine("<script>alert(1)</script>")).toBeNull();
    expect(parseGpsLine("lat 40 lon -3")).toBeNull();
  });

  it("draws one marker per valid finding and opens it", () => {
    const onOpen = vi.fn();
    const { container } = plainRender(
      <GpsMap
        findings={[
          gps("ok", "Latitude: 40.416775, Longitude: -3.703790"),
          gps("bad", "Latitude: <img src=x onerror=alert(1)>, Longitude: 1"),
        ]}
        onOpen={onOpen}
      />,
    );
    const markers = screen.getAllByRole("button", { name: /GPS finding at/ });
    expect(markers).toHaveLength(1);
    fireEvent.keyDown(markers[0], { key: "Enter" });
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "ok" }));
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("image")).toBeNull();
  });

  it("renders nothing when no GPS line parses", () => {
    const { container } = plainRender(<GpsMap findings={[gps("bad", "not a line")]} onOpen={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Severity trend (TASK-35)", () => {
  it("summarizes the window and lists the per-day data for assistive tech", () => {
    const points: TrendPoint[] = [
      { date: "2026-10-04", critical: 0, high: 1, medium: 0, low: 0, info: 0, unclassified: 0 },
      { date: "2026-10-05", critical: 1, high: 0, medium: 2, low: 0, info: 0, unclassified: 1 },
    ];
    plainRender(<SeverityTrend points={points} />);
    expect(screen.getByRole("img", { name: "5 findings over the last 2 days" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Findings per day by severity" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });
});

describe("Compare runs (TASK-35)", () => {
  it("shows new, resolved and persistent sections for the pair in the URL", async () => {
    window.history.replaceState(null, "", "/runs/compare?a=run-a&b=run-b");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.startsWith("/api/compare")) {
          const run = (id: string) => ({ run_id: id, target: "acme.com", status: "completed", started_at: "2026-10-01T10:00:00Z", total_findings: 1 });
          const item = (snippet: string, run: string) => ({ finding_id: snippet, run_id: run, finding_type: "email", severity: "medium", evidence_snippet: snippet, asset_url: "https://acme.com/a.pdf" });
          return new Response(
            JSON.stringify({
              a: run("run-a"),
              b: run("run-b"),
              new: [item("<b>fresh</b>@acme.com", "run-b")],
              resolved: [item("old@acme.com", "run-a")],
              persistent: [],
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({ total: 0, runs: [] }), { status: 200 });
      }),
    );
    render(<CompareView />);
    const fresh = await screen.findByRole("region", { name: "New" });
    expect(within(fresh).getByText("<b>fresh</b>@acme.com")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Resolved" })).getByText("old@acme.com")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Persistent" })).getByText("No finding appears in both runs.")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });
});
