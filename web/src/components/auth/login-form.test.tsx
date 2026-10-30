import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { LoginForm } from "@/components/auth/login-form";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LoginForm", () => {
  it("points at first-run setup when the API says setup is open", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/api/auth/me")) {
          return new Response(JSON.stringify({ detail: "authentication required", setup_available: true }), {
            status: 401,
            headers: { "x-csrf-token": "csrf" },
          });
        }
        return new Response("{}", { status: 404 });
      }),
    );
    render(<LoginForm />);
    expect(await screen.findByRole("link", { name: "Create the first account" })).toHaveAttribute(
      "href",
      "/setup",
    );
    expect(screen.queryByRole("link", { name: "Create your account" })).not.toBeInTheDocument();
  });

  it("offers invitation registration when auth is on and setup is closed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/api/auth/me")) {
          return new Response(JSON.stringify({ detail: "authentication required", setup_available: false }), {
            status: 401,
            headers: { "x-csrf-token": "csrf" },
          });
        }
        return new Response("{}", { status: 404 });
      }),
    );
    render(<LoginForm />);
    expect(await screen.findByRole("link", { name: "Create your account" })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.queryByRole("link", { name: "Create the first account" })).not.toBeInTheDocument();
  });
});
