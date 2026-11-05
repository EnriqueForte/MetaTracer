import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

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
    expect(panel).toHaveTextContent("Discovery");
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
    expect(panel).toHaveTextContent("Downloading");
    expect(panel).toHaveTextContent("Fetching documents");
    expect(panel).not.toHaveTextContent("Crawling");
    // Progress is the server's step over the pipeline total, not a decorative
    // sweep: the bar exposes it to assistive tech.
    const bar = screen.getByRole("progressbar", { name: "Scan progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "3");
    expect(bar).toHaveAttribute("aria-valuemax", "7");
    expect(bar).toHaveAttribute("aria-valuetext", "Step 3 of 7");
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

  it("shows shared values on a finished run", async () => {
    stub("completed");
    render(<RunProgress runId="run-1" />);
    expect(await screen.findByRole("region", { name: "Shared values" })).toBeInTheDocument();
    expect(screen.getByText("No shared value links this run to another asset.")).toBeInTheDocument();
  });

  it("puts the five exports in the run bar", async () => {
    stub("completed");
    render(<RunProgress runId="run-1" />);
    expect(await screen.findByRole("link", { name: "Download Markdown" })).toHaveAttribute(
      "href",
      "/api/runs/run-1/export?format=md&redact=contacts",
    );
    expect(screen.getByRole("link", { name: "Download JSON" })).toHaveAttribute(
      "href",
      "/api/runs/run-1/export?format=json&redact=contacts",
    );
    expect(screen.getByRole("link", { name: "Download HTML" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Bounty TXT" })).toBeInTheDocument();
    expect(screen.getByLabelText("Redaction")).toHaveValue("contacts");
    expect(screen.getByText("The report file is regenerated on the server.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reports" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Scan activity" })).not.toBeInTheDocument();
  });

  it("shows Abort scan only for an operator while the run is active", async () => {
    stub("running", "operator");
    render(<RunProgress runId="run-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Abort scan" }));
    expect(await screen.findByRole("heading", { name: "Abort this scan?" })).toBeInTheDocument();
  });

  it("hides Abort scan from a viewer", async () => {
    stub("running", "viewer");
    render(<RunProgress runId="run-1" />);
    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abort scan" })).not.toBeInTheDocument();
  });

  it("hides Delete run from a viewer on a finished run", async () => {
    stub("completed", "viewer");
    render(<RunProgress runId="run-1" />);
    expect(await screen.findByRole("link", { name: "Download Markdown" })).toBeInTheDocument();
    await screen.findByText("Completed");
    expect(screen.queryByRole("button", { name: "Delete run" })).not.toBeInTheDocument();
  });

  it("hides Abort scan once the run is completed", async () => {
    stub("completed", "operator");
    render(<RunProgress runId="run-1" />);
    expect(await screen.findByRole("link", { name: "Download Markdown" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abort scan" })).not.toBeInTheDocument();
  });
});
