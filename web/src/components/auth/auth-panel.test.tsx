import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { RegisterForm } from "@/components/auth/register-form";
import { SetupForm } from "@/components/auth/setup-form";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubAuth() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ authenticated: false }), { status: 200 })),
  );
}

describe("Auth surfaces", () => {
  it.each([
    [LoginForm, "Sign in"],
    [RegisterForm, "Create your account"],
    [SetupForm, "Initial setup"],
  ] as const)("keeps %s on one panel without a rail", (Form, title) => {
    stubAuth();
    render(<Form />);
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(document.querySelectorAll(".mt-auth-panel")).toHaveLength(1);
    expect(screen.queryByRole("navigation", { name: "Primary" })).not.toBeInTheDocument();
  });
});
