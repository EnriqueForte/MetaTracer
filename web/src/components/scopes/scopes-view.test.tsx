import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { importScopesFile, MAX_IMPORT_BYTES, ScopesView } from "@/components/scopes/scopes-view";

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

describe("importScopesFile errors (TASK-35)", () => {
  it("rejects an oversized file before uploading", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["{}"], "big.json");
    Object.defineProperty(file, "size", { value: MAX_IMPORT_BYTES + 1 });
    await expect(importScopesFile(file)).rejects.toThrow("File too large: the limit is 5 MiB.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects invalid JSON before uploading", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(importScopesFile(new File(["{nope"], "bad.json"))).rejects.toThrow(
      "The file is not valid JSON.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API detail on a 422", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "entry 0: 'name' must be 1..64 characters" }), { status: 422 })),
    );
    await expect(importScopesFile(new File(["{}"], "x.json"))).rejects.toThrow(
      "Import failed: entry 0: 'name' must be 1..64 characters",
    );
  });
});
