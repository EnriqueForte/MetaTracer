import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { SearchView, isGlobalSearch, searchUrl } from "./search-view";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/search");
  vi.unstubAllGlobals();
});

const payload = {
  query: "acme",
  kind: "all",
  mode: "lexical",
  findings: {
    total: 1,
    has_more: false,
    next_cursor: null,
    items: [
      {
        kind: "finding",
        id: "f1",
        run_id: "run-1",
        asset_id: "a1",
        asset_url: "https://t.com/a.jpg",
        finding_type: "email",
        type_label: "Email",
        title: "Email Address Disclosure",
        field_source: "pdfinfo:Author",
        evidence_snippet: "ops@acme-corp.internal",
        severity: "medium",
        triage_status: "open",
        created_at: "2026-11-12T00:00:00Z",
      },
    ],
  },
  metadata: { total: 0, items: [], has_more: false, next_cursor: null },
};

describe("global search helpers", () => {
  it("guards the API shape and builds the query string", () => {
    expect(isGlobalSearch(payload)).toBe(true);
    expect(isGlobalSearch({ hits: [] })).toBe(false);
    expect(searchUrl({ q: "acme", kind: "findings" })).toBe("/api/search?q=acme&kind=findings");
  });
});

describe("SearchView", () => {
  it("searches persisted findings without crawling", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/search")) {
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      return new Response("{}", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SearchView />);
    expect(screen.getByRole("heading", { name: "Buscar" })).toBeInTheDocument();
    expect(screen.getByText("Escribe una consulta")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Consulta de búsqueda" }), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("ops@acme-corp.internal")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Email Address Disclosure" })).toHaveAttribute(
      "href",
      "/runs/run-1/findings",
    );
    const called = String(fetchMock.mock.calls[0]?.[0]);
    expect(called).toContain("/api/search?");
    expect(called).toContain("q=acme");
  });
});
