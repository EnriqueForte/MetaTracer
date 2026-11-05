import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { FindingsPanel } from "@/components/run/findings-panel";

function finding(id: string, triage: string, snippet: string) {
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
    triage_status: triage,
    triage_note: null,
    triaged_by: null,
    triaged_at: null,
  };
}

function stub(role: "operator" | "viewer") {
  const puts: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: true, username: "ada", role }), { status: 200 });
      }
      if (url.includes("/triage")) {
        const body = JSON.parse(String(init?.body));
        puts.push({ url, body });
        return new Response(
          JSON.stringify({
            finding_id: "real",
            triage_status: body.status,
            triage_note: body.note,
            triaged_by: "u1",
            triaged_at: "2026-10-05T19:00:00Z",
            severity: "medium",
            evidence_snippet: "real@acme.com",
          }),
          { status: 200 },
        );
      }
      if (url.includes("/api/feedback/")) return new Response("{}", { status: 404 });
      return new Response(
        JSON.stringify({ findings: [finding("noise", "false_positive", "noise@acme.com"), finding("real", "open", "real@acme.com")] }),
        { status: 200 },
      );
    }),
  );
  return puts;
}

beforeEach(() => window.history.replaceState(null, "", "/runs/run-1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Finding triage in Web V2 (TASK-35)", () => {
  it("hides dismissed findings by default and shows them on toggle", async () => {
    stub("operator");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("real@acme.com")).toBeInTheDocument();
    expect(within(table).queryByText("noise@acme.com")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show dismissed (1)" }));
    expect(within(screen.getByRole("table")).getByText("noise@acme.com")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("False positive")).toBeInTheDocument();
    expect(window.location.search).toContain("dismissed=1");
  });

  it("opens a finding without giving triage and feedback the same React key", async () => {
    stub("operator");
    const errors: string[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      errors.push(args.map(String).join(" "));
    });
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    fireEvent.click(await screen.findByText("real@acme.com"));
    await screen.findByRole("region", { name: "Triage" });
    expect(errors.some((line) => line.includes("same key"))).toBe(false);
    spy.mockRestore();
  });

  it("lets an operator mark a finding as false positive and updates the list", async () => {
    const puts = stub("operator");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    fireEvent.click(await screen.findByText("real@acme.com"));
    const triage = await screen.findByRole("region", { name: "Triage" });
    fireEvent.change(within(triage).getByLabelText("Status"), { target: { value: "false_positive" } });
    fireEvent.change(within(triage).getByLabelText("Note (optional)"), { target: { value: "vendor" } });
    fireEvent.click(within(triage).getByRole("button", { name: "Save triage" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].url).toBe("/api/runs/run-1/findings/real/triage");
    expect(puts[0].body).toEqual({ status: "false_positive", note: "vendor" });
    expect(puts[0].body).not.toHaveProperty("severity");
    expect(await within(triage).findByText("False positive", { selector: "span" })).toBeInTheDocument();
  });

  it("offers another run's triage as a suggestion and applies it only on click", async () => {
    const puts = stub("operator");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/auth/me")) {
          return new Response(JSON.stringify({ authenticated: true, username: "ada", role: "operator" }), {
            status: 200,
          });
        }
        if (url.includes("/triage")) {
          const body = JSON.parse(String(init?.body));
          puts.push({ url, body });
          return new Response(
            JSON.stringify({
              finding_id: "real",
              triage_status: body.status,
              triage_note: body.note,
              triaged_by: "u1",
              triaged_at: "2026-10-05T19:00:00Z",
              severity: "medium",
              evidence_snippet: "real@acme.com",
            }),
            { status: 200 },
          );
        }
        const suggested = {
          ...finding("real", "open", "real@acme.com"),
          triage_suggestion: {
            status: "confirmed",
            from_run_id: "run-a",
            from_finding_id: "prior",
            note: "checked on the first run",
            triaged_at: "2026-10-01T00:00:00Z",
          },
        };
        return new Response(JSON.stringify({ findings: [suggested] }), { status: 200 });
      }),
    );
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    expect(await screen.findByText("Suggested: Confirmed")).toBeInTheDocument();
    fireEvent.click(screen.getByText("real@acme.com"));
    const triage = await screen.findByRole("region", { name: "Triage" });
    expect(within(triage).getByText(/Suggested from another run/i)).toBeInTheDocument();
    expect(within(triage).getByText(/does not change severity or evidence/i)).toBeInTheDocument();
    fireEvent.click(within(triage).getByRole("button", { name: "Apply suggestion" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].body).toEqual({ status: "confirmed", note: "checked on the first run" });
    expect(puts[0].body).not.toHaveProperty("severity");
  });

  it("shows the triage status read-only to a viewer", async () => {
    stub("viewer");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    fireEvent.click(await screen.findByText("real@acme.com"));
    const triage = await screen.findByRole("region", { name: "Triage" });
    expect(within(triage).getByText("Open")).toBeInTheDocument();
    expect(within(triage).queryByRole("button", { name: "Save triage" })).not.toBeInTheDocument();
  });
});
