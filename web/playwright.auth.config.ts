import { defineConfig, devices } from "@playwright/test";

/**
 * Auth e2e config (MIN-01 / T1, T3 viewer): runs ONLY auth.spec.ts against a
 * real authenticated API + Next under /v2.
 *
 * Two webServers, in order:
 *   1. FastAPI with METATRACER_AUTH_ENABLED=true (scripts/e2e-auth-server.mjs)
 *      on 127.0.0.1:8000 — the API Next's /api rewrites target.
 *   2. Next production start on 127.0.0.1:3000 (basePath /v2).
 *
 * Run:  npx playwright test --config=playwright.auth.config.ts
 */
const AUTH_API_PORT = 8000;
const AUTH_WEB_PORT = 3000;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  testMatch: "e2e/auth.spec.ts",
  use: { baseURL: `http://127.0.0.1:${AUTH_WEB_PORT}/v2` },
  webServer: [
    {
      command: "node scripts/e2e-auth-server.mjs",
      url: `http://127.0.0.1:${AUTH_API_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3000",
      url: `http://127.0.0.1:${AUTH_WEB_PORT}/v2/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [{ name: "chromium-auth", use: { ...devices["Desktop Chrome"] } }],
});