import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { UsersView } from "@/components/users/users-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UsersView role gating (T3)", () => {
  it("shows only the operator-required state for a viewer, with no admin controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/auth/me")) {
          return new Response(JSON.stringify({ authenticated: true, username: "visitor", role: "viewer", csrf_token: "t" }), { status: 200 });
        }
        return new Response(JSON.stringify({ users: [] }), { status: 200 });
      }),
    );
    render(<UsersView />);
    expect(await screen.findByText("Operator role required")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Users" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create" })).not.toBeInTheDocument();
  });
});

describe("UsersView invitations", () => {
  it("shows an invitation code once as text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        // Session bootstrap: an operator so the admin surface renders (T3).
        if (url.includes("/api/auth/me")) {
          return new Response(JSON.stringify({ authenticated: true, username: "op", role: "operator", csrf_token: "t" }), { status: 200 });
        }
        if (url.includes("/api/invitations") && init?.method === "POST") {
          return new Response(JSON.stringify({ code: "ONCE-CODE" }), { status: 201 });
        }
        if (url.includes("/api/invitations")) {
          return new Response(JSON.stringify({ invitations: [] }), { status: 200 });
        }
        return new Response(JSON.stringify({ users: [] }), { status: 200 });
      }),
    );
    render(<UsersView />);
    fireEvent.click(await screen.findByRole("tab", { name: "Invitations" }));
    fireEvent.click(screen.getByRole("button", { name: "Create invitation" }));
    expect(await screen.findByText("ONCE-CODE")).toBeInTheDocument();
    expect(screen.getAllByText("ONCE-CODE")).toHaveLength(1);
    expect(screen.getByText("ONCE-CODE").closest("p")?.className).toContain("mt-tech");
  });
});
