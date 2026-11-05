import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { FindingsPanel } from "@/components/run/findings-panel";

function finding(id: string, snippet: string) {
  return {
    id,
    title: `Finding ${id}`,
    finding_type: "email",
    type_label: "Email",
    severity: "medium",
    confidence: "high",
    field_source: "pdfinfo:Author",
    evidence_snippet: snippet,
    asset_source_url: "https://acme.com/a.pdf",
    asset_final_url: "https://acme.com/a.pdf",
    asset_content_type: "application/pdf",
    severity_justification: "",
    impact_analysis: "",
    remediation_advice: "",
    reproduction_steps: [],
    triage_status: "open",
    triage_note: null,
    triaged_by: null,
    triaged_at: null,
  };
}

function stub(role: "operator" | "viewer") {
  const posts: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: true, username: "ada", role }), { status: 200 });
      }
      if (url.endsWith("/findings/triage") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        posts.push({ url, body });
        return new Response(
          JSON.stringify({
            updated: Array.isArray(body.finding_ids) ? body.finding_ids.length : 0,
            missing: [],
            triage_status: body.status,
            findings: (body.finding_ids as string[]).map((id) => ({
              finding_id: id,
              triage_status: body.status,
              triage_note: body.note,
              triaged_by: "u1",
              triaged_at: "2026-11-05T19:00:00Z",
              severity: "medium",
              evidence_snippet: `${id}@acme.com`,
            })),
          }),
          { status: 200 },
        );
      }
      if (url.includes("/triage")) {
        return new Response("{}", { status: 200 });
      }
      return new Response(
        JSON.stringify({
          findings: [finding("one", "one@acme.com"), finding("two", "two@acme.com")],
        }),
        { status: 200 },
      );
    }),
  );
  return posts;
}

beforeEach(() => window.history.replaceState(null, "", "/runs/run-1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Bulk triage (TASK-42)", () => {
  it("lets an operator apply triage to selected rows without sending severity", async () => {
    const posts = stub("operator");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    expect(await screen.findByText("one@acme.com")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select finding one" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select finding two" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply to selected" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toBe("/api/runs/run-1/findings/triage");
    expect(posts[0].body).toEqual({
      finding_ids: ["one", "two"],
      status: "false_positive",
      note: null,
    });
    expect(posts[0].body).not.toHaveProperty("severity");
  });

  it("hides bulk selection from a viewer", async () => {
    stub("viewer");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    expect(await screen.findByText("one@acme.com")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Select finding one" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Bulk triage" })).not.toBeInTheDocument();
  });

  it("selects the active row with x", async () => {
    stub("operator");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    const table = await screen.findByRole("table");
    const rows = within(table)
      .getAllByRole("row")
      .filter((row) => row.hasAttribute("data-index"));
    fireEvent.focus(rows[0]);
    fireEvent.keyDown(document.body, { key: "x" });
    expect(screen.getByRole("region", { name: "Bulk triage" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select finding one" })).toBeChecked();
  });
});
