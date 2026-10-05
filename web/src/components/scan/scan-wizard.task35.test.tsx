import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { ScanWizard } from "@/components/scan/scan-wizard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stub(role: "operator" | "viewer" = "operator") {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: true, username: "ada", role }), { status: 200 });
      }
      if (url.includes("/api/runs")) {
        calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return new Response("{}", { status: 409 });
      }
      return new Response(
        JSON.stringify({
          scopes: [{ id: "s1", name: "acme", description: null, domains: ["acme.com"], total_domains: 1, created_at: "" }],
        }),
        { status: 200 },
      );
    }),
  );
  return calls;
}

describe("ScanWizard scope source (TASK-35)", () => {
  it("disables manual domains while saved scopes are selected and sends only scope_ids", async () => {
    const calls = stub();
    render(<ScanWizard />);
    fireEvent.change(screen.getByLabelText("Targets"), { target: { value: "acme.com" } });
    fireEvent.change(screen.getByLabelText("Authorized scope domains"), { target: { value: "other.com" } });
    fireEvent.change(screen.getByLabelText("Authorized scope domains"), { target: { value: "" } });
    fireEvent.click(await screen.findByRole("checkbox", { name: /acme/ }));
    expect(screen.getByLabelText("Authorized scope domains")).toBeDisabled();
    expect(screen.getByText("Using saved scopes — manual domains are ignored.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /I confirm/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm and start scan" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    const body = calls[0].body as Record<string, unknown>;
    expect(body.scope_ids).toEqual(["s1"]);
    expect(body).not.toHaveProperty("scope_domains");
  });

  it("disables saved scopes while manual domains are typed", async () => {
    stub();
    render(<ScanWizard />);
    const checkbox = await screen.findByRole("checkbox", { name: /acme/ });
    fireEvent.change(screen.getByLabelText("Authorized scope domains"), { target: { value: "acme.com" } });
    expect(checkbox).toBeDisabled();
    expect(screen.getByText("Using manual domains — saved scopes are ignored.")).toBeInTheDocument();
  });

  it("keeps focus inside the scope dialog and returns it on Escape", async () => {
    stub();
    render(<ScanWizard />);
    fireEvent.change(screen.getByLabelText("Targets"), { target: { value: "acme.com" } });
    fireEvent.change(screen.getByLabelText("Authorized scope domains"), { target: { value: "acme.com" } });
    const start = screen.getByRole("button", { name: "Start scan" });
    start.focus();
    fireEvent.click(start);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" })));

    // Focus leaving the dialog is pulled back in (focus trap).
    start.focus();
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.activeElement).toBe(start);
  });

  it("tells a viewer that scans are operator-only", async () => {
    stub("viewer");
    render(<ScanWizard />);
    expect(await screen.findByText(/Viewer accounts can review runs but cannot start scans/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start scan" })).toBeDisabled();
  });
});
