import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  // Minimal rejection: only the wizard spec must pass here, auth OFF default.
  // The auth e2e lives in playwright.auth.config.ts (separate webServers).
  testMatch: "e2e/wizard.spec.ts",
  use: { baseURL: "http://127.0.0.1:3456" },
  webServer: {
    command: "npm run start -- --hostname 127.0.0.1 --port 3456",
    url: "http://127.0.0.1:3456/v2",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
