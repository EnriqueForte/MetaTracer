import { defineConfig, devices } from "@playwright/test";

const AUTH_API_PORT = 8000; // the auth server script binds 127.0.0.1:8000
const AUTH_WEB_PORT = 3000; // Next dev default; auth.spec.ts hits /v2 on it

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3456" },
      webServer: {
        command: "npm run start -- --hostname 127.0.0.1 --port 3456",
        url: "http://127.0.0.1:3456/v2",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
    },
    {
      // MIN-01: real authenticated API + Next. The auth spec needs both:
      // the API (auth ON, operator provisioned) and Next proxying /api to it.
      name: "chromium-auth",
      use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${AUTH_WEB_PORT}/v2` },
      testMatch: "e2e/auth.spec.ts",
      webServer: [
        {
          command: "node scripts/e2e-auth-server.mjs",
          url: `http://127.0.0.1:${AUTH_API_PORT}/api/auth/me`,
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
    },
  ],
});