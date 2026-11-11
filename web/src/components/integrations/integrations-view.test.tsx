import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { IntegrationsView } from "./integrations-view";

const wayback = {
  id: "wayback",
  label: "Wayback CDX",
  kind: "discovery",
  enabled: false,
  status: "disabled",
  sends: ["domain name"],
  egress_hosts: ["web.archive.org"],
  notice: "Archived pages are not downloaded and are not current exposure.",
};
const card = {
  id: "rdap",
  label: "RDAP",
  kind: "context",
  enabled: false,
  status: "disabled",
  sends: ["domain name"],
  egress_hosts: ["data.iana.org"],
  notice: "Sends the domain name to the RDAP service. This does not add the domain to a scan scope.",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("IntegrationsView", () => {
  it("shows RDAP as disabled and does not offer a lookup until it is enabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ connectors: [card, wayback] }), { status: 200 })),
    );
    renderWithProviders(<IntegrationsView />);
    const rdap = await screen.findByRole("region", { name: "RDAP" });
    expect(rdap).toHaveTextContent("desactivado");
    expect(screen.getByText(/does not add the domain to a scan scope/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Probar conexión" })).toBeDisabled();
    expect(screen.getByText(/not current exposure/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buscar capturas" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Activar RDAP" }));
  });
});
