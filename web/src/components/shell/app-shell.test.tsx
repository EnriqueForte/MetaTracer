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
      await screen.findByText("Signing out ends this session on every surface."),
    ).toBeInTheDocument();
    expect(screen.getByText("Security Intelligence")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("API reachable");
    expect(screen.queryByRole("link", { name: "Classic UI" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(screen.getByText("Administration")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New scan" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Investigations" })).toHaveAttribute(
      "href",
      "/investigations",
    );
    expect(screen.getByText("Enrique Forte")).toBeInTheDocument();
    expect(screen.getByText("@T3r0s3c")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GitHub profile of Enrique Forte" })).toHaveAttribute(
      "href",
      "https://github.com/enriqueforte",
    );
    expect(screen.getByRole("link", { name: "LinkedIn profile of Enrique Forte" })).toHaveAttribute(
      "href",
      "https://www.linkedin.com/in/enriqueforte",
    );
  });

  it("hides the sign out control when auth is off (T11: no classic UI link)", async () => {
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
    expect(screen.queryByRole("link", { name: "Classic UI" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.queryByText("Signing out ends this session on every surface.")).not.toBeInTheDocument();
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
    expect(screen.getByRole("link", { name: "New scan" })).not.toHaveAttribute("aria-current");
  });
});
