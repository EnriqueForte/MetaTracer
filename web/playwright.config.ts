import { defineConfig, devices } from "@playwright/test";

/**
 * Wizard e2e (auth OFF). The auth/viewer specs live in playwright.auth.config.ts
 * because they need a second API with a different posture.
 *
 * `next start` refuses to run when `output: 'standalone'` is set (the Docker
 * image needs standalone), so both configs boot the generated server through
 * scripts/serve-standalone.mjs, which also copies public/ and .next/static
 * next to server.js exactly like the image build does.
 */
const PORT = 3456;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  testMatch: "e2e/wizard.spec.ts",
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  webServer: {
    command: "node scripts/serve-standalone.mjs",
    url: `http://127.0.0.1:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { PORT: String(PORT), HOSTNAME: "127.0.0.1" },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
