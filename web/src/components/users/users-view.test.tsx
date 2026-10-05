import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { UsersView } from "@/components/users/users-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UsersView invitations", () => {
  it("shows an invitation code once as text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
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
