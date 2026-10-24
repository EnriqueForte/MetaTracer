import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Certifies MIN-01 (V2 CSRF) and T3 (viewer role gating) end-to-end with real
 * auth. Runs ONLY under playwright.auth.config.ts (project chromium-auth),
 * which starts FastAPI with METATRACER_AUTH_ENABLED=true and Next on :3000
 * under basePath /v2.
 */

const PASSWORD = process.env.METATRACER_AUTH_PASSWORD ?? "test-password-123";

/**
 * API login as the double-submit flow does: GET /me mints the pre-session
 * CSRF cookie + header, then POST credentials echoing the token. Returns the
 * CSRF token from the login body, valid for that request session's cookies.
 */
async function apiLogin(request: APIRequestContext, username: string, password: string): Promise<string> {
  const me = await request.get("/api/auth/me");
  const meHeaders = me.headers();
  const csrf = meHeaders["x-csrf-token"] ?? "";
  const res = await request.post("/api/auth/login", {
    headers: { "X-CSRF-Token": csrf },
    data: { username, password },
  });
  expect(res.status()).toBe(200);
  return (res.json() as Promise<{ csrf_token?: string }>).then((body) => body.csrf_token ?? csrf);
}

test("login boots a session and mutations carry the CSRF token (MIN-01)", async ({ page }) => {
  // baseURL already ends in /v2, but page.goto("<relative>") would resolve
  // against the HOST (http://127.0.0.1:3000/login), not the base path. Use
  // the full path so the request lands under the /v2 base path.
  await page.goto("/v2/login");

  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  await page.getByLabel("Username").fill("operator");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText(/Signed in as|Sign out/)).toBeVisible({ timeout: 10_000 });

  // The real MIN-01 probe: an operator mutation (create a scope) must NOT get
  // 403 CSRF. Mirrors the UI: read the token from the in-page meta.
  const response = await page.evaluate(async () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta?.getAttribute("content") ?? "";
    return fetch("/api/scopes", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ name: "e2e-csrf-probe", domains: ["example.com"] }),
    }).then((r) => ({ status: r.status }));
  });
  expect(response.status).toBe(201);
});

test("viewer cannot open admin controls nor mutate (T3)", async ({ browser }) => {
  // 1. As operator (API session): create a viewer account through the real
  //    admin endpoint. The request context keeps the login cookies.
  const operator = await browser.newContext();
  const opRequest = operator.request;
  const opCsrf = await apiLogin(opRequest, "operator", PASSWORD);
  const create = await opRequest.post("/api/users", {
    headers: { "X-CSRF-Token": opCsrf },
    data: { username: "viewer-t3", password: "viewer-password-123", role: "viewer" },
  });
  expect(create.status()).toBe(201);
  await operator.close();

  // 2. Sign in as the viewer in a fresh page.
  const viewerPage = await browser.newPage();
  await viewerPage.goto("/v2/login");
  await viewerPage.getByLabel("Username").fill("viewer-t3");
  await viewerPage.getByLabel("Password").fill("viewer-password-123");
  await viewerPage.getByRole("button", { name: "Sign in" }).click();
  await expect(viewerPage.getByText(/Signed in as|Sign out/)).toBeVisible({ timeout: 10_000 });

  // 3. The Users admin screen must be gated: no tabs, no create buttons.
  await viewerPage.goto("/v2/users");
  await expect(viewerPage.getByText("Operator role required")).toBeVisible();
  await expect(viewerPage.getByRole("tab", { name: "Users" })).toHaveCount(0);
  await expect(viewerPage.getByRole("button", { name: "Create" })).toHaveCount(0);

  // 4. Even a raw mutation attempt stays rejected server-side.
  const attempt = await viewerPage.evaluate(async () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta?.getAttribute("content") ?? "";
    return fetch("/api/users", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ username: "nope", password: "password-123", role: "operator" }),
    }).then((r) => ({ status: r.status }));
  });
  expect(attempt.status).toBe(403);

  await viewerPage.close();
});
