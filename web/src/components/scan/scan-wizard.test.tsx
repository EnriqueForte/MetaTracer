import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter at least one target.");

    fireEvent.change(screen.getByLabelText("Targets"), { target: { value: "example.com" } });
    fireEvent.change(screen.getByLabelText("Authorized scope domains"), {
      target: { value: "example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));

    const confirm = screen.getByRole("button", { name: "Confirm and start scan" });
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("heading", { name: "Confirm authorized scope" })).toBeInTheDocument();
  });

  it.each([
    [403, "The scope confirmation was rejected by the server."],
    [409, "Another scan is already running; wait for it to finish."],
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
    fireEvent.change(screen.getByLabelText("Targets"), { target: { value: "example.com" } });
    fireEvent.change(screen.getByLabelText("Authorized scope domains"), {
      target: { value: "example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm and start scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});
