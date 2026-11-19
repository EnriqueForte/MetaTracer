import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import { routePath } from "./coexist-proxy.mjs";

/**
 * The production entrypoint (deploy/Caddyfile) and the dev proxy
 * (scripts/coexist-proxy.mjs) must route the SAME paths to the same upstream,
 * or a flow that works with `npm run dev` breaks in the container (T10).
 *
 * This test pins the shared contract and reads the Caddyfile to prove the
 * blocks are declared in the order Caddy needs (specific before catch-all).
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const caddyfile = readFileSync(path.resolve(here, "../../deploy/Caddyfile"), "utf8");
const nextConfig = readFileSync(path.resolve(here, "../next.config.ts"), "utf8");

/** The routing table both entrypoints must honour.
 *
 * T11 cut-over: Next.js owns the origin root, so everything that is not /api
 * or /static goes to Web V2. The dev proxy (coexist-proxy.mjs) keeps its
 * /v2 prefix for local side-by-side work; the production table is asserted
 * separately against the Caddyfile below.
 */
const ROUTES = [
  { path: "/api/health", expected: "api" },
  { path: "/api/runs/abc/stream", expected: "api" },
  { path: "/static/metatracer.css", expected: "api" },
  { path: "/v2", expected: "v2" },
  { path: "/v2/login", expected: "v2" },
];

describe("routing contract shared with the Caddy entrypoint", () => {
  for (const route of ROUTES) {
    it(`${route.path} -> ${route.expected}`, () => {
      assert.equal(routePath(route.path), route.expected);
    });
  }
});

describe("Caddyfile declares the same matchers in the right order", () => {
  it("routes /api and /static before the Next catch-all", () => {
    const api = caddyfile.indexOf("handle /api/*");
    const statics = caddyfile.indexOf("handle /static/*");
    const catchAll = caddyfile.indexOf("\n\thandle {");
    assert.ok(api > 0, "missing handle /api/*");
    assert.ok(statics > 0, "missing handle /static/*");
    assert.ok(catchAll > api && catchAll > statics, "catch-all must come last");
  });

  it("sends the root and app routes to Web V2 (T11 cut-over)", () => {
    // The catch-all is the Next upstream: V1 serves no HTML any more.
    const catchAllBlock = caddyfile.slice(caddyfile.indexOf("\n\thandle {"));
    assert.match(catchAllBlock, /reverse_proxy web-v2:3000/);
    assert.doesNotMatch(catchAllBlock, /reverse_proxy web:8000/);
  });

  it("disables proxy buffering on the API so SSE is not frozen", () => {
    // flush_interval -1 is what keeps GET /api/runs/{id}/stream live.
    const apiBlock = caddyfile.slice(caddyfile.indexOf("handle /api/*"), caddyfile.indexOf("handle /static/*"));
    assert.match(apiBlock, /flush_interval -1/);
    assert.match(apiBlock, /reverse_proxy web:8000/);
  });

  it("no longer exposes a /v2 prefix (Next serves from the root)", () => {
    assert.doesNotMatch(caddyfile, /handle \/v2/);
  });
});

describe("Next production CSP (TASK-55)", () => {
  it("does not grant unsafe-eval outside development", () => {
    assert.match(nextConfig, /script-src 'self' 'unsafe-inline'/);
    const productionSrc = nextConfig.match(/: "script-src 'self' 'unsafe-inline'"/);
    assert.ok(productionSrc, "production script-src must omit unsafe-eval");
  });
});
