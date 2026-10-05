import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => nav,
}));

import { AppShell } from "@/components/shell/app-shell";

function stubMedia() {
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function stub(role: "operator" | "viewer") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/notifications")) {
        return new Response(
          JSON.stringify({
            total: 1,
            notifications: [
              {
                id: 0,
                kind: "completed",
                run_id: "run-42",
                target: "acme.com",
                total_assets: 3,
                total_findings: 2,
                error_message: null,
                created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
              },
            ],
          }),
          { status: 200 },
        );
      }
      if (url.includes("/api/runs")) {
        return new Response(
          JSON.stringify({
            total: 1,
            runs: [
              {
                run_id: "abcdef12-0000-4000-8000-000000000000",
                status: "completed",
                target: "acme.com",
                scope: ["acme.com"],
                total_assets: 1,
                total_findings: 0,
                started_at: "2026-10-01T10:00:00Z",
                completed_at: "2026-10-01T10:01:00Z",
              },
            ],
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ authenticated: true, username: "ada", role }), { status: 200 });
    }),
  );
}

afterEach(() => {
  cleanup();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("AppShell (TASK-35)", () => {
  it("links each notification to its run with a relative time", async () => {
    stubMedia();
    stub("operator");
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    const panel = await screen.findByRole("region", { name: "Notifications panel" });
    const link = await within(panel).findByRole("link");
    expect(link).toHaveAttribute("href", "/runs/run-42");
    expect(link).toHaveTextContent("5 min ago");
    expect(within(panel).getByRole("button", { name: "Dismiss notification" })).toBeInTheDocument();
  });

  it("hides Dismiss from a viewer", async () => {
    stubMedia();
    stub("viewer");
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    await screen.findByText("ada");
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    const panel = await screen.findByRole("region", { name: "Notifications panel" });
    await within(panel).findByRole("link");
    expect(within(panel).queryByRole("button", { name: "Dismiss notification" })).not.toBeInTheDocument();
  });

  it("opens the palette with Ctrl+K and jumps to a run by id prefix", async () => {
    stubMedia();
    stub("operator");
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    await screen.findByText("ada");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = await screen.findByRole("combobox", { name: "Search commands or runs" });
    expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: "abcdef12" } });
    const option = await screen.findByRole("option", { name: /Open run acme.com/ });
    expect(option).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(nav.push).toHaveBeenCalledWith("/runs/abcdef12-0000-4000-8000-000000000000");
  });

  it("shows the shortcut help with ? outside inputs", async () => {
    stubMedia();
    stub("operator");
    render(
      <AppShell>
        <input aria-label="Page field" />
      </AppShell>,
    );
    await screen.findByText("ada");
    fireEvent.keyDown(screen.getByLabelText("Page field"), { key: "?" });
    expect(screen.queryByRole("heading", { name: "Keyboard shortcuts" })).not.toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "?" });
    expect(await screen.findByRole("heading", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });

  it("expands the full ethical notice", async () => {
    stubMedia();
    stub("operator");
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    const pill = screen.getByRole("button", { name: "Authorized use only" });
    fireEvent.click(pill);
    expect(pill).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/explicitly authorized to test/)).toBeInTheDocument();
  });
});
