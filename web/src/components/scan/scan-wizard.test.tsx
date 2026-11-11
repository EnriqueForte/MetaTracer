import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { ScanWizard } from "@/components/scan/scan-wizard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ScanWizard scope gate", () => {
  it("does not enable confirm until the checkbox is checked", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ scopes: [] }), { status: 200 })),
    );
    render(<ScanWizard />);
    fireEvent.click(screen.getByRole("button", { name: "Iniciar escaneo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Indica al menos un objetivo.");

    fireEvent.change(screen.getByLabelText("Objetivos"), { target: { value: "example.com" } });
    fireEvent.change(screen.getByLabelText("Dominios de alcance autorizado"), {
      target: { value: "example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar escaneo" }));

    const confirm = screen.getByRole("button", { name: "Confirmar e iniciar escaneo" });
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("heading", { name: "Confirmar alcance autorizado" })).toBeInTheDocument();
  });

  it.each([
    [403, "El servidor rechazó la confirmación de alcance."],
    [404, "El alcance guardado ya no existe; elige otro o escribe los dominios."],
    [409, "Ya hay otro escaneo en curso; espera a que termine."],
    [429, "Demasiadas peticiones: espera unos segundos y reintenta."],
  ])("renders HTTP %s as text", async (status, message) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/runs")) return new Response("{}", { status });
        return new Response(JSON.stringify({ scopes: [] }), { status: 200 });
      }),
    );
    render(<ScanWizard />);
    fireEvent.change(screen.getByLabelText("Objetivos"), { target: { value: "example.com" } });
    fireEvent.change(screen.getByLabelText("Dominios de alcance autorizado"), {
      target: { value: "example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar escaneo" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar e iniciar escaneo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});
