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

/** The routing table both entrypoints must honour. */
const ROUTES = [
  { path: "/", expected: "api" },
  { path: "/runs", expected: "api" },
  { path: "/dashboard", expected: "api" },
  { path: "/login", expected: "api" },
  { path: "/users", expected: "api" },
  { path: "/api/health", expected: "api" },
  { path: "/api/runs/abc/stream", expected: "api" },
  { path: "/static/metatracer.css", expected: "api" },
  { path: "/static/alpine-csp-3.17.4.min.js", expected: "api" },
  { path: "/v2", expected: "v2" },
  { path: "/v2/", expected: "v2" },
  { path: "/v2/login", expected: "v2" },
  { path: "/v2/runs/abc", expected: "v2" },
  { path: "/v2evil", expected: "api" },
];

describe("routing contract shared with the Caddy entrypoint", () => {
  for (const route of ROUTES) {
    it(`${route.path} -> ${route.expected}`, () => {
      assert.equal(routePath(route.path), route.expected);
    });
  }
});

describe("Caddyfile declares the same matchers in the right order", () => {
  it("routes /api, /static and /v2 before the catch-all", () => {
    const api = caddyfile.indexOf("handle /api/*");
    const statics = caddyfile.indexOf("handle /static/*");
    const v2 = caddyfile.indexOf("handle /v2/*");
    const catchAll = caddyfile.indexOf("\n\thandle {");
    assert.ok(api > 0, "missing handle /api/*");
    assert.ok(statics > 0, "missing handle /static/*");
    assert.ok(v2 > 0, "missing handle /v2/*");
    assert.ok(catchAll > api && catchAll > statics && catchAll > v2, "catch-all must come last");
  });

  it("disables proxy buffering on the API so SSE is not frozen", () => {
    // flush_interval -1 is what keeps GET /api/runs/{id}/stream live.
    const apiBlock = caddyfile.slice(caddyfile.indexOf("handle /api/*"), caddyfile.indexOf("handle /static/*"));
    assert.match(apiBlock, /flush_interval -1/);
    assert.match(apiBlock, /reverse_proxy web:8000/);
  });

  it("proxies Web V2 to the Next service", () => {
    assert.match(caddyfile, /reverse_proxy web-v2:3000/);
  });
});
