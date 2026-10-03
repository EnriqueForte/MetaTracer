import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FindingsPanel } from "@/components/run/findings-panel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const finding = {
  id: "f1",
  title: "GPS in photo",
  finding_type: "gps",
  type_label: "GPS",
  severity: null,
  confidence: "high",
  field_source: "EXIF",
  evidence_snippet: "<script>alert(1)</script>",
  asset_source_url: "javascript:alert(1)",
  asset_final_url: "https://example.com/a.jpg",
  asset_content_type: "image/jpeg",
  severity_justification: "<img src=x onerror=alert(1)>",
  impact_analysis: "Impact text",
  remediation_advice: "",
  reproduction_steps: ["Step <b>one</b>"],
};

describe("FindingsPanel hostile content", () => {
  it("renders snippets as text and does not link javascript URLs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ findings: [finding] }), { status: 200 })),
    );
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    expect(await screen.findByText("Unclassified")).toBeInTheDocument();
    fireEvent.click(screen.getByText("<script>alert(1)</script>"));
    expect(screen.getAllByText("<script>alert(1)</script>").length).toBeGreaterThan(0);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(screen.getByText("Step <b>one</b>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    const hostile = screen.getByText("javascript:alert(1)");
    expect(hostile.closest("a")).toBeNull();
    expect(screen.getByRole("link", { name: "https://example.com/a.jpg" })).toHaveAttribute(
      "href",
      "https://example.com/a.jpg",
    );
  });

  it("groups findings by their real asset URL", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ findings: [finding] }), { status: 200 })),
    );
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    expect(await screen.findByRole("heading", { name: "Assets with findings" })).toBeInTheDocument();
    expect(screen.getByText("GPS · Unclassified")).toBeInTheDocument();
  });

  it("keeps a load error distinct from an empty result", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));
    render(<FindingsPanel runId="run-2" totalAssets={0} />);
    expect(await screen.findByText("Findings unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No findings")).not.toBeInTheDocument();
  });
});
