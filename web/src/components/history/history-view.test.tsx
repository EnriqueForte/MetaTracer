import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HistoryView } from "@/components/history/history-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("HistoryView", () => {
  it("renders runs in a dense table, including aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            total: 1,
            has_more: false,
            next_cursor: null,
            runs: [
              {
                run_id: "run-1",
                status: "aborted",
                target: "example.com",
                scope: ["example.com"],
                total_assets: 2,
                total_findings: 1,
                started_at: "2026-09-29T12:00:00Z",
              },
            ],
          }),
          { status: 200 },
        ),
      ),
    );
    render(<HistoryView />);
    expect(await screen.findByRole("link", { name: "example.com" })).toHaveAttribute("href", "/runs/run-1");
    const status = screen.getByRole("columnheader", { name: "Status" });
    expect(status.className).not.toContain("uppercase");
    expect(status.className).toContain("py-1");
    const table = screen.getByRole("table", { name: "Local scan history" });
    expect(table).toHaveTextContent("Aborted");
    expect(table.querySelector("td")?.className).toContain("py-1.5");
  });
});
