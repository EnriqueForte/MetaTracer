import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { HistoryView } from "@/components/history/history-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
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
    const status = screen.getByRole("columnheader", { name: "Estado" });
    expect(status.className).not.toContain("uppercase");
    expect(status.className).toContain("py-1");
    const table = screen.getByRole("table", { name: "Historial local de escaneos" });
    expect(table).toHaveTextContent("Abortado");
    expect(table.querySelector("td")?.className).toContain("py-1.5");
  });

  it("opens the status filter from the URL", async () => {
    window.history.replaceState(null, "", "/runs?status=failed");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ total: 0, has_more: false, next_cursor: null, runs: [] }),
          { status: 200 },
        ),
      ),
    );
    render(<HistoryView />);
    expect(await screen.findByRole("button", { name: "Filtrar por estado Fallido" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows Delete run only to an operator on a finished scan", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/auth/me")) {
          return new Response(
            JSON.stringify({ authenticated: true, username: "ada", role: "operator" }),
            { status: 200 },
          );
        }
        return new Response(
          JSON.stringify({
            total: 2,
            has_more: false,
            next_cursor: null,
            runs: [
              {
                run_id: "done",
                status: "completed",
                target: "done.example",
                scope: ["done.example"],
                total_assets: 1,
                total_findings: 0,
                started_at: "2026-09-29T12:00:00Z",
              },
              {
                run_id: "live",
                status: "running",
                target: "live.example",
                scope: ["live.example"],
                total_assets: 0,
                total_findings: 0,
                started_at: "2026-09-29T12:00:00Z",
              },
            ],
          }),
          { status: 200 },
        );
      }),
    );
    render(<HistoryView />);
    expect(await screen.findByRole("button", { name: "Eliminar escaneo" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Eliminar escaneo" })).toHaveLength(1);
  });
});
