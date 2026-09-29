import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScopesView } from "@/components/scopes/scopes-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ScopesView", () => {
  it("lists saved scopes in a dense table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            scopes: [
              {
                id: "s1",
                name: "acme",
                description: "engagement",
                domains: ["example.com"],
                total_domains: 1,
              },
            ],
          }),
          { status: 200 },
        ),
      ),
    );
    render(<ScopesView />);
    expect(await screen.findByRole("columnheader", { name: "Domains" })).toHaveClass("py-1");
    expect(screen.getByText("example.com").className).toContain("mt-tech");
    expect(screen.getByText("1 domain(s)")).toBeInTheDocument();
  });
});
