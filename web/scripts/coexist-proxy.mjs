import http from "node:http";
import { pathToFileURL } from "node:url";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
]);

export function routePath(rawUrl) {
  if (typeof rawUrl !== "string" || !rawUrl.startsWith("/") || rawUrl.startsWith("//")) {
    return "reject";
  }
  const path = rawUrl.split("?")[0];
  if (path.includes("\\") || path.includes("://")) return "reject";
  if (path === "/v2" || path.startsWith("/v2/")) return "v2";
  return "api";
}

export function loopbackOrigin(raw, label) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${label} is not an absolute URL`);
  }
  if (url.protocol !== "http:") throw new Error(`${label} must be http`);
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(`${label} must be an origin only`);
  }
  if (url.pathname !== "/" && url.pathname !== "") {
    throw new Error(`${label} must not include a path`);
  }
  if (url.hostname !== "127.0.0.1" && url.hostname !== "::1") {
    throw new Error(`${label} must stay on loopback`);
  }
  return url;
}

export function sameOriginHost(header) {
  if (typeof header !== "string") return null;
  const trimmed = header.trim();
  const lower = trimmed.toLowerCase();
  if (lower === "127.0.0.1" || lower.startsWith("127.0.0.1:")) return trimmed;
  if (lower === "[::1]" || lower.startsWith("[::1]:")) return trimmed;
  return null;
}

export function forwardHeaders(headers) {
  const hop = new Set(HOP_BY_HOP);
  const connection = headers.connection;
  if (typeof connection === "string") {
    for (const name of connection.split(",")) hop.add(name.trim().toLowerCase());
  }
  const out = {};
  for (const [key, value] of Object.entries(headers)) {
    if (hop.has(key.toLowerCase())) continue;
    if (value === undefined) continue;
    out[key] = value;
  }
  return out;
}

export function createCoexistProxy({ apiOrigin, v2Origin }) {
  const api = loopbackOrigin(apiOrigin, "METATRACER_API_ORIGIN");
  const v2 = loopbackOrigin(v2Origin, "METATRACER_V2_ORIGIN");

  return http.createServer((req, res) => {
    const kind = routePath(req.url ?? "");
    if (kind === "reject") {
      res.writeHead(400);
      res.end();
      return;
    }
    const upstream = kind === "v2" ? v2 : api;
    const host = sameOriginHost(req.headers.host);
    if (!host) {
      res.writeHead(400);
      res.end();
      return;
    }
    const headers = forwardHeaders(req.headers);
    // FastAPI builds /static links from this Host. It must stay the browser
    // origin (8080), or CSP blocks the CSS served as if it came from :8000.
    headers.host = host;
    const proxyReq = http.request(
      {
        protocol: upstream.protocol,
        hostname: upstream.hostname,
        port: upstream.port,
        method: req.method,
        path: req.url,
        headers,
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode ?? 502, forwardHeaders(proxyRes.headers));
        proxyRes.pipe(res);
      },
    );
    proxyReq.on("error", () => {
      if (!res.headersSent) res.writeHead(502);
      res.end();
    });
    req.pipe(proxyReq);
  });
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const apiOrigin = process.env.METATRACER_API_ORIGIN ?? "http://127.0.0.1:8000";
  const v2Origin = process.env.METATRACER_V2_ORIGIN ?? "http://127.0.0.1:3000";
  const port = Number(process.env.METATRACER_COEXIST_PORT ?? 8080);
  const server = createCoexistProxy({ apiOrigin, v2Origin });
  server.listen(port, "127.0.0.1", () => {
    process.stdout.write(`coexist proxy http://127.0.0.1:${port}  / -> ${apiOrigin}  /v2 -> ${v2Origin}\n`);
  });
}
