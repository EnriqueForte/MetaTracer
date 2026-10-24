import { defineConfig, devices } from "@playwright/test";

/**
 * Auth + viewer e2e (MIN-01, T3). Needs a real authenticated API, so it boots:
 *   1. FastAPI with METATRACER_AUTH_ENABLED=true (scripts/e2e-auth-server.mjs)
 *   2. The Next standalone server (scripts/serve-standalone.mjs)
 *
 * Run: npx playwright test --config=playwright.auth.config.ts
 */
const AUTH_API_PORT = 8000;
const AUTH_WEB_PORT = 3000;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  testMatch: "e2e/auth.spec.ts",
  use: { baseURL: `http://127.0.0.1:${AUTH_WEB_PORT}` },
  webServer: [
    {
      command: "node scripts/e2e-auth-server.mjs",
      url: `http://127.0.0.1:${AUTH_API_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "node scripts/serve-standalone.mjs",
      url: `http://127.0.0.1:${AUTH_WEB_PORT}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { PORT: String(AUTH_WEB_PORT), HOSTNAME: "127.0.0.1" },
    },
  ],
  projects: [{ name: "chromium-auth", use: { ...devices["Desktop Chrome"] } }],
});
