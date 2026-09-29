import assert from "node:assert/strict";
import http from "node:http";
import { after, describe, it } from "node:test";

import { createCoexistProxy, forwardHeaders, loopbackOrigin, routePath, sameOriginHost } from "./coexist-proxy.mjs";

describe("coexist proxy routing", () => {
  it("sends /v2 to Next and everything else to the API", () => {
    assert.equal(routePath("/v2"), "v2");
    assert.equal(routePath("/v2/runs/abc"), "v2");
    assert.equal(routePath("/v2?x=1"), "v2");
    assert.equal(routePath("/"), "api");
    assert.equal(routePath("/api/health"), "api");
    assert.equal(routePath("/static/metatracer.css"), "api");
    assert.equal(routePath("/runs"), "api");
    assert.equal(routePath("/v2evil"), "api");
  });

  it("rejects scheme-relative and non-path targets", () => {
    assert.equal(routePath("//evil.example/v2"), "reject");
    assert.equal(routePath("http://evil.example/"), "reject");
    assert.equal(routePath(""), "reject");
  });

  it("only accepts a loopback http origin", () => {
    assert.equal(loopbackOrigin("http://127.0.0.1:8000", "API").origin, "http://127.0.0.1:8000");
    assert.throws(() => loopbackOrigin("http://example.com", "API"));
    assert.throws(() => loopbackOrigin("https://127.0.0.1:8000", "API"));
    assert.throws(() => loopbackOrigin("http://127.0.0.1:8000/api", "API"));
  });

  it("keeps a loopback Host and rejects any other", () => {
    assert.equal(sameOriginHost("127.0.0.1:8080"), "127.0.0.1:8080");
    assert.equal(sameOriginHost("[::1]:8080"), "[::1]:8080");
    assert.equal(sameOriginHost("evil.example"), null);
    assert.equal(sameOriginHost("example.com:8080"), null);
  });

  it("drops hop-by-hop headers and does not invent new ones", () => {
    const forwarded = forwardHeaders({
      host: "127.0.0.1:8080",
      connection: "close, x-secret",
      "x-secret": "nope",
      cookie: "metatracer_session=abc",
      accept: "text/html",
    });
    assert.equal(forwarded.connection, undefined);
    assert.equal(forwarded["x-secret"], undefined);
    assert.equal(forwarded.cookie, "metatracer_session=abc");
    assert.equal(forwarded.accept, "text/html");
    assert.equal(Object.hasOwn(forwarded, "x-forwarded-for"), false);
  });
});

describe("coexist proxy forwarding", () => {
  const servers = [];

  after(async () => {
    await Promise.all(servers.map((server) => new Promise((resolve) => server.close(resolve))));
  });

  it("serves / from the API and /v2 from Next on one port", async () => {
    const api = http.createServer((req, res) => {
      res.end(`api ${req.url} host=${req.headers.host}`);
    });
    const v2 = http.createServer((req, res) => {
      res.end(`v2 ${req.url}`);
    });
    const apiPort = await new Promise((resolve) => {
      api.listen(0, "127.0.0.1", () => resolve(api.address().port));
    });
    const v2Port = await new Promise((resolve) => {
      v2.listen(0, "127.0.0.1", () => resolve(v2.address().port));
    });
    const proxy = createCoexistProxy({
      apiOrigin: `http://127.0.0.1:${apiPort}`,
      v2Origin: `http://127.0.0.1:${v2Port}`,
    });
    const proxyPort = await new Promise((resolve) => {
      proxy.listen(0, "127.0.0.1", () => resolve(proxy.address().port));
    });
    servers.push(api, v2, proxy);

    const root = await fetch(`http://127.0.0.1:${proxyPort}/`);
    const preview = await fetch(`http://127.0.0.1:${proxyPort}/v2/runs`);
    assert.equal(await root.text(), `api / host=127.0.0.1:${proxyPort}`);
    assert.equal(await preview.text(), "v2 /v2/runs");
  });
});
