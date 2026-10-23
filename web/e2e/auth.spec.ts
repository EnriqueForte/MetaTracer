import { expect, test } from "@playwright/test";

/**
 * Certifies MIN-01 (V2 CSRF) end-to-end with real auth.
 * Runs ONLY under the `chromium-auth` project (playwright.config.ts), which
 * starts the FastAPI app with METATRACER_AUTH_ENABLED=true and Next on :3000
 * under basePath /v2. baseURL is project-provided and already ends in /v2,
 * so paths here are relative to the base path.
 */

const PASSWORD = process.env.METATRACER_AUTH_PASSWORD ?? "test-password-123";

test("login boots a session and mutations carry the CSRF token (MIN-01)", async ({ page }) => {
  // baseURL already ends in /v2, but page.goto("<relative>") would resolve
  // against the HOST (http://127.0.0.1:3000/login), not the base path. Use
  // the full path so the request lands under the /v2 base path.
  await page.goto("/v2/login");

  // The pre-session GET /api/auth/me mints the CSRF cookie+header even signed out.
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  await page.getByLabel("Username").fill("operator");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();

  // Successful login redirects to the shell (signed in as operator).
  await expect(page.getByText(/Signed in as|Sign out/)).toBeVisible({ timeout: 10_000 });

  // The real MIN-01 probe: an operator mutation (create a scope) must NOT get
  // 403 CSRF. This mirrors the UI: the token is read from the in-page meta
  // (what csrfTokenFromCookie does after the login bootstrap) and echoed in
  // the X-CSRF-Token header.
  const response = await page.evaluate(async () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta?.getAttribute("content") ?? "";
    return fetch("/api/scopes", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ name: "e2e-csrf-probe", domains: ["example.com"] }),
    }).then((r) => ({ status: r.status, body: r.text() }));
  });
  expect(response.status).toBe(201);
});