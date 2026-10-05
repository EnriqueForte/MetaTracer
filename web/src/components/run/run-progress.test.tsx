import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunProgress } from "@/components/run/run-progress";

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

function runBody(status: string) {
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
  };
}

function stub(status: string) {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/findings")) {
        return new Response(JSON.stringify({ findings: [] }), { status: 200 });
      }
      return new Response(JSON.stringify(runBody(status)), { status: 200 });
    }),
  );
}

describe("RunProgress", () => {
  it("shows a live activity panel that follows stored counts and stream steps", async () => {
    stub("running");
    render(<RunProgress runId="run-1" />);
    const panel = await screen.findByRole("region", { name: "Scan activity" });
    expect(panel).toHaveTextContent("Reading saved documents");
    expect(panel).toHaveTextContent("Documents");
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
    expect(panel).toHaveTextContent("Discovery");
    expect(panel).toHaveTextContent("Crawling");
    expect(panel).toHaveTextContent("https://example.com/a");
    expect(screen.queryByRole("heading", { name: "Reports" })).not.toBeInTheDocument();
  });

  it("names classification when the stream reports that step", async () => {
    stub("running");
    render(<RunProgress runId="run-1" />);
    const panel = await screen.findByRole("region", { name: "Scan activity" });
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
    expect(panel).toHaveTextContent("Classification and AI analysis");
    expect(panel).toHaveTextContent("Classifying");
  });

  it("puts the five exports in the run bar", async () => {
    stub("completed");
    render(<RunProgress runId="run-1" />);
    expect(await screen.findByRole("link", { name: "Download Markdown" })).toHaveAttribute(
      "href",
      "/api/runs/run-1/export?format=md",
    );
    expect(screen.getByRole("link", { name: "Download JSON" })).toHaveAttribute(
      "href",
      "/api/runs/run-1/export?format=json",
    );
    expect(screen.getByRole("link", { name: "Download HTML" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Bounty TXT" })).toBeInTheDocument();
    expect(screen.getByText("The report file is regenerated on the server.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reports" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Scan activity" })).not.toBeInTheDocument();
  });
});
