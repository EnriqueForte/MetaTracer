import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { FindingsPanel } from "@/components/run/findings-panel";
import { VIRTUAL_THRESHOLD } from "@/components/run/findings/findings-table";

function finding(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    title: `Finding ${id}`,
    finding_type: "email",
    type_label: "Email",
    severity: "high",
    confidence: "high",
    field_source: "pdfinfo:Author",
    evidence_snippet: `user-${id}@acme.com`,
    asset_source_url: `https://acme.com/${id}.pdf`,
    asset_final_url: `https://acme.com/${id}.pdf`,
    asset_content_type: "application/pdf",
    severity_justification: "",
    impact_analysis: "",
    remediation_advice: "",
    reproduction_steps: [],
    ...overrides,
  };
}

function stub(findings: unknown[], role: "operator" | "viewer" | null = "operator") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(
          JSON.stringify(role ? { authenticated: true, username: "ada", role } : { authenticated: false }),
          { status: 200 },
        );
      }
      if (url.includes("/api/feedback/")) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify({ findings }), { status: 200 });
    }),
  );
}

beforeEach(() => {
  window.history.replaceState(null, "", "/runs/run-1");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("FindingsPanel triage ergonomics (TASK-35)", () => {
  it("filters to unclassified findings only", async () => {
    stub([finding("a"), finding("b", { severity: null, evidence_snippet: "unclassified-evidence" })]);
    render(<FindingsPanel runId="run-1" totalAssets={2} />);
    const chip = await screen.findByRole("button", { name: "Unclassified (1)" });
    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "true");
    const table = screen.getByRole("table");
    expect(within(table).getByText("unclassified-evidence")).toBeInTheDocument();
    expect(within(table).queryByText("user-a@acme.com")).not.toBeInTheDocument();
  });

  it("writes filters to the URL and restores them on reload", async () => {
    stub([finding("a"), finding("b", { severity: "low", evidence_snippet: "low-evidence" })]);
    const first = render(<FindingsPanel runId="run-1" totalAssets={2} />);
    fireEvent.click(await screen.findByRole("button", { name: "Low (1)" }));
    expect(window.location.search).toBe("?severity=low");
    first.unmount();

    render(<FindingsPanel runId="run-1" totalAssets={2} />);
    const table = await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "Low (1)" })).toHaveAttribute("aria-pressed", "true");
    expect(within(table).getByText("low-evidence")).toBeInTheDocument();
    expect(within(table).queryByText("user-a@acme.com")).not.toBeInTheDocument();
  });

  it("groups only the filtered findings by asset and opens a badge in the sheet", async () => {
    stub([finding("a"), finding("b", { severity: "low" })]);
    render(<FindingsPanel runId="run-1" totalAssets={2} />);
    fireEvent.click(await screen.findByRole("button", { name: "Low (1)" }));
    const assets = screen.getByText("Assets with findings").closest("details") as HTMLElement;
    expect(within(assets).queryByText("https://acme.com/a.pdf")).not.toBeInTheDocument();
    fireEvent.click(within(assets).getByRole("button", { name: "Email · Low" }));
    expect(await screen.findByRole("heading", { name: "Finding b" })).toBeInTheDocument();
  });

  it("opens a row with Space as well as Enter", async () => {
    stub([finding("a")]);
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    const cell = await screen.findByText("user-a@acme.com");
    fireEvent.keyDown(cell.closest("tr") as HTMLElement, { key: " " });
    expect(await screen.findByRole("heading", { name: "Finding a" })).toBeInTheDocument();
  });

  it("hides the feedback form from a viewer", async () => {
    stub([finding("a")], "viewer");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    fireEvent.click(await screen.findByText("user-a@acme.com"));
    expect(await screen.findByRole("heading", { name: "Finding a" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Feedback" })).not.toBeInTheDocument();
  });

  it("shows the feedback form to an operator", async () => {
    stub([finding("a")], "operator");
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    await screen.findByText("user-a@acme.com");
    await act(async () => {
      await Promise.resolve();
    });
    fireEvent.click(screen.getByText("user-a@acme.com"));
    expect(await screen.findByRole("heading", { name: "Feedback" })).toBeInTheDocument();
  });

  it("focuses search with / and moves rows with j/k, but not inside inputs", async () => {
    stub([finding("a"), finding("b")]);
    render(<FindingsPanel runId="run-1" totalAssets={2} />);
    await screen.findByText("user-a@acme.com");
    fireEvent.keyDown(window, { key: "j" });
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(window, { key: "j" });
    expect(rows[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(window, { key: "k" });
    expect(rows[0]).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(document.body, { key: "/" });
    const search = screen.getByLabelText("Search findings");
    expect(document.activeElement).toBe(search);
    fireEvent.keyDown(search, { key: "j" });
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    expect(rows[1]).toHaveAttribute("aria-selected", "false");
  });

  it("renders only a window of rows for large runs", async () => {
    const many = Array.from({ length: VIRTUAL_THRESHOLD + 100 }, (_, index) => finding(`f${index}`));
    stub(many);
    render(<FindingsPanel runId="run-1" totalAssets={1} />);
    await screen.findByText("user-f0@acme.com");
    const bodyRows = screen.getAllByRole("row").filter((row) => row.hasAttribute("data-index"));
    expect(bodyRows.length).toBeLessThan(100);
    expect(screen.queryByText(`user-f${VIRTUAL_THRESHOLD + 99}@acme.com`)).not.toBeInTheDocument();
  });
});
