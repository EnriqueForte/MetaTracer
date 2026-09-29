import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace: vi.fn() }),
}));

import { AppShell } from "@/components/shell/app-shell";

afterEach(() => {
  cleanup();
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
    expect(screen.getByRole("link", { name: "Classic UI" })).toHaveAttribute("href", "/");
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
});
