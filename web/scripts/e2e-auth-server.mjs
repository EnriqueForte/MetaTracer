/**
 * E2E auth server for Playwright (MIN-01): starts the FastAPI app with auth
 * ENABLED and a provisioned operator, on the default 127.0.0.1:8000 that
 * Next's /api rewrites already target.
 *
 * Used as the `webServer` of the `chromium-auth` project (playwright.config.ts)
 * so the auth spec runs against a REAL authenticated API:
 *   npx playwright test e2e/auth.spec.ts --project=chromium-auth
 *
 * The operator is provisioned via METATRACER_AUTH_PASSWORD (default
 * test-password-123, matching auth.spec.ts). The database is a throwaway file
 * under <repo>/data/ (git-ignored) and is deleted on shutdown.
 */
import { spawn } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { pythonExecutable, waitForPort } from "./dev-with-api.mjs";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..");

const AUTH_PORT = 8000;
const DB_FILENAME = ".e2e-auth.db";
const DEFAULT_PASSWORD = "test-password-123";
const PASSWORD = process.env.METATRACER_AUTH_PASSWORD ?? DEFAULT_PASSWORD;

const python = pythonExecutable(repoRoot);
if (!python) {
  process.stderr.write(
    `No virtualenv Python found; install the project first:\n` +
      `  python -m venv .venv\n  ${
        process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python"
      } -m pip install -e ".[dev]"\n`,
  );
  process.exit(1);
}

const dbFile = path.join(repoRoot, "data", DB_FILENAME);
if (existsSync(dbFile)) rmSync(dbFile, { force: true });

// SQLAlchemy absolute-path URL: 3 slashes on Windows ("/F:/..."), 4 on POSIX.
const dbUrl =
  (process.platform === "win32" ? "sqlite+aiosqlite:///" : "sqlite+aiosqlite:////") +
  dbFile.replaceAll("\\", "/");

const env = {
  ...process.env,
  METATRACER_AUTH_ENABLED: "true",
  METATRACER_AUTH_PASSWORD: PASSWORD,
  METATRACER_DATABASE_URL: dbUrl,
  METATRACER_BIND_HOST: "127.0.0.1",
  METATRACER_LOG_LEVEL: "WARNING",
};

const child = spawn(python, ["-m", "metatracer", "serve"], {
  cwd: repoRoot,
  env,
  stdio: "inherit",
});

let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  if (child.exitCode === null && child.signalCode === null) child.kill();
  rmSync(dbFile, { force: true });
  setTimeout(() => process.exit(code), 500);
}
child.on("exit", (code) => {
  if (!stopping) stop(code ?? 1);
});
process.on("SIGTERM", () => stop(0));
process.on("SIGINT", () => stop(0));

try {
  await waitForPort(AUTH_PORT, { timeoutMs: 60_000 });
  if (stopping) process.exit(0);
  process.stdout.write(`e2e auth API ready on http://127.0.0.1:${AUTH_PORT}\n`);
  // Keep the server alive until Playwright tears the webServer down.
  await new Promise(() => {});
} catch (error) {
  if (!stopping) {
    process.stderr.write(
      `${error instanceof Error ? error.message : "API did not start"}\n`,
    );
    stop(1);
  }
}