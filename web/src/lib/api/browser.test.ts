import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, csrfTokenFromCookie } from "@/lib/api/browser";

function setCsrfMeta(value: string | null) {
  const existing = document.querySelector('meta[name="csrf-token"]');
  if (existing) existing.remove();
  if (value === null) return;
  const meta = document.createElement("meta");
  meta.name = "csrf-token";
  meta.content = value;
  document.head.appendChild(meta);
}

afterEach(() => {
  setCsrfMeta(null);
  vi.unstubAllGlobals();
});

describe("csrfTokenFromCookie", () => {
  it("reads the token from the in-page meta tag", () => {
    setCsrfMeta("abc123");
    expect(csrfTokenFromCookie()).toBe("abc123");
  });

  it("returns an empty string when no meta tag is present", () => {
    expect(csrfTokenFromCookie()).toBe("");
  });

  it("does not depend on document.cookie (not a browser API)", () => {
    // jsdom exposes document.cookie for compatibility; a real browser does not.
    // The implementation must read the meta tag, never the cookie shim, so
    // the token still works when the property is undefined.
    setCsrfMeta("token-from-meta");
    const original = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(document, "cookie", { value: undefined });
    try {
      expect(csrfTokenFromCookie()).toBe("token-from-meta");
    } finally {
      if (original) Object.defineProperty(Document.prototype, "cookie", original);
      else delete (document as unknown as Record<string, unknown>).cookie;
    }
  });
});

describe("apiFetch", () => {
  it("adds the x-csrf-token header on mutating methods", async () => {
    setCsrfMeta("csrf-xyz");
    const headersRef: HeadersInit[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        headersRef.push(init.headers as HeadersInit);
        return new Response("{}", { status: 200 });
      }),
    );

    await apiFetch("/api/scopes", { method: "POST", body: "{}" });
    const headers = new Headers(headersRef[0]);
    expect(headers.get("x-csrf-token")).toBe("csrf-xyz");

    // GET must not carry the CSRF header.
    await apiFetch("/api/scopes");
    expect(new Headers(headersRef[1]).has("x-csrf-token")).toBe(false);
  });

  it("omits the header when no token is available", async () => {
    setCsrfMeta(null);
    const seen: HeadersInit[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        seen.push(init.headers as HeadersInit);
        return new Response("{}", { status: 200 });
      }),
    );
    await apiFetch("/api/scopes", { method: "DELETE" });
    expect(new Headers(seen[0]).get("x-csrf-token")).toBe("");
  });
});