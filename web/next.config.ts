import type { NextConfig } from "next";

import { apiOrigin } from "./src/lib/api/origin";

process.env.NEXT_TELEMETRY_DISABLED = "1";

/**
 * Production must not use unsafe-eval. next dev (React Refresh) does.
 * Measured again after `next build`; do not relax FastAPI's CSP to match.
 */
function contentSecurityPolicy(): string {
  const scriptSrc =
    process.env.NODE_ENV === "development"
      ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
      : "script-src 'self' 'unsafe-inline'";
  return [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
  ].join("; ");
}

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy() },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
];

const nextConfig: NextConfig = {
  basePath: "/v2",
  // Standalone output for the Docker image (web/Dockerfile): a self-contained
  // server.js that needs no node_modules tree at runtime. Harmless in dev.
  output: "standalone",
  // next dev allows HMR only from localhost. Opening 127.0.0.1 otherwise
  // answers the dev socket with a bare "Unauthorized", hydration never
  // finishes, and the shell stays on the server-rendered scan page.
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: `${apiOrigin()}/api/:path*`,
          basePath: false,
        },
      ],
    };
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
