import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

const navState = vi.hoisted(() => ({ pathname: "/dashboard" }));

vi.mock("next/navigation", () => ({
  usePathname: () => navState.pathname,
  useRouter: () => ({ replace: vi.fn() }),
}));

import { AppShell } from "@/components/shell/app-shell";

afterEach(() => {
  cleanup();
  navState.pathname = "/dashboard";
  vi.unstubAllGlobals();
});

function stubMedia() {
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

describe("AppShell coexistence", () => {
  it("tells a signed-in operator that sign out closes the classic session", async () => {
    stubMedia();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/notifications")) {
          return new Response(JSON.stringify({ notifications: [] }), { status: 200 });
        }
        return new Response(
          JSON.stringify({ authenticated: true, username: "ada", role: "operator" }),
          { status: 200 },
        );
      }),
    );
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(
      await screen.findByText("Signing out also ends the session used by the classic UI."),
    ).toBeInTheDocument();
    expect(screen.getByText("Security Intelligence")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("API reachable");
    expect(screen.getByRole("link", { name: "Classic UI" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Reconnaissance" })).not.toHaveAttribute("aria-current");
  });

  it("keeps the classic link when auth is off and does not offer sign out", async () => {
    stubMedia();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/notifications")) {
          return new Response(JSON.stringify({ notifications: [] }), { status: 200 });
        }
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }),
    );
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(await screen.findByRole("link", { name: "Classic UI" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.queryByText("Signing out also ends the session used by the classic UI.")).not.toBeInTheDocument();
  });

  it("marks History while a run is open", async () => {
    stubMedia();
    navState.pathname = "/runs/abc";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ notifications: [] }), { status: 200 })),
    );
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(await screen.findByRole("link", { name: "History" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Reconnaissance" })).not.toHaveAttribute("aria-current");
  });
});
