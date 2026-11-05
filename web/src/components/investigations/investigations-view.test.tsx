import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestigationDetail } from "@/components/investigations/investigation-detail";
import { InvestigationsView } from "@/components/investigations/investigations-view";
import { baseCommands } from "@/components/shell/command-palette";
import { renderWithProviders as render } from "@/test/render";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const GROUP = {
  id: "inv-1",
  name: "Acme 2026",
  description: null,
  status: "open" as const,
  created_at: "2026-11-05T10:00:00Z",
  run_count: 1,
  runs: [
    {
      run_id: "run-aa",
      run_ref: "aabbccdd",
      status: "completed",
      target: "https://acme.test",
      started_at: "2026-11-05T10:00:00Z",
    },
  ],
};

function stubMe(role: "operator" | "viewer") {
  return {
    authenticated: true,
    username: "ada",
    role,
    csrf_token: "t",
  };
}

function stubFetch(role: "operator" | "viewer", groups = [GROUP]) {
  let status: "open" | "closed" = "open";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify(stubMe(role)), { status: 200 });
      }
      if (url.endsWith("/api/investigations") && method === "GET") {
        return new Response(
          JSON.stringify({ total: groups.length, investigations: groups }),
          { status: 200 },
        );
      }
      if (url.includes("/api/investigations/inv-1") && method === "PUT") {
        status = "closed";
        return new Response(JSON.stringify({ ...GROUP, status }), { status: 200 });
      }
      if (url.includes("/api/investigations/inv-1") && method === "GET") {
        return new Response(JSON.stringify({ ...GROUP, status }), { status: 200 });
      }
      return new Response("missing", { status: 404 });
    }),
  );
}

describe("InvestigationsView", () => {
  it("lists groups with a link to the detail page", async () => {
    stubFetch("operator");
    render(<InvestigationsView />);
    const link = await screen.findByRole("link", { name: "Acme 2026" });
    expect(link).toHaveAttribute("href", "/investigations/inv-1");
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
  });

  it("hides create for viewers", async () => {
    stubFetch("viewer");
    render(<InvestigationsView />);
    expect(await screen.findByRole("link", { name: "Acme 2026" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create" })).not.toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    stubFetch("operator", []);
    render(<InvestigationsView />);
    expect(await screen.findByText("No investigations yet")).toBeInTheDocument();
  });
});

describe("InvestigationDetail", () => {
  it("links grouped runs and can close without applying triage", async () => {
    stubFetch("operator");
    render(<InvestigationDetail investigationId="inv-1" />);
    const runLink = await screen.findByRole("link", { name: "aabbccdd" });
    expect(runLink).toHaveAttribute("href", "/runs/run-aa");
    expect(screen.getByText(/never applied/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close investigation" }));
    expect(await screen.findByText("Closed")).toBeInTheDocument();
  });

  it("hides close for viewers", async () => {
    stubFetch("viewer");
    render(<InvestigationDetail investigationId="inv-1" />);
    expect(await screen.findByRole("link", { name: "aabbccdd" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close investigation" })).not.toBeInTheDocument();
  });
});

describe("command palette", () => {
  it("includes Investigations for every actor", () => {
    expect(baseCommands("viewer").some((item) => item.href === "/investigations")).toBe(true);
    expect(baseCommands("operator").some((item) => item.href === "/investigations")).toBe(true);
  });
});
