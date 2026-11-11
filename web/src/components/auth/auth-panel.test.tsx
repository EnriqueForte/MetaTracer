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
    [LoginForm, "Iniciar sesión"],
    [RegisterForm, "Crear tu cuenta"],
    [SetupForm, "Configuración inicial"],
  ] as const)("keeps %s on one panel without a rail", (Form, title) => {
    stubAuth();
    render(<Form />);
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(document.querySelectorAll(".mt-auth-panel")).toHaveLength(1);
    expect(screen.queryByRole("navigation", { name: "Primary" })).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Cómo funciona MetaTracer" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Canal de captura/ })).toBeInTheDocument();
    expect(screen.getByText("Alcance confirmado")).toBeInTheDocument();
    expect(screen.getByText("Informe bounty")).toBeInTheDocument();
    expect(screen.getByText("Enrique Forte")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Perfil de GitHub de Enrique Forte" })).toHaveAttribute(
      "href",
      "https://github.com/enriqueforte",
    );
  });
});
