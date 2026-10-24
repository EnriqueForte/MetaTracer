/** True only when GET /api/auth/me says this installation has auth disabled. */
export function installationHasAuthOff(status: number, body: unknown): boolean {
  if (status !== 200 || !body || typeof body !== "object") return false;
  return (body as { authenticated?: unknown }).authenticated === false;
}

/**
 * True when the first-run setup flow is still open (T9).
 *
 * The API reports `setup_available` on GET /api/auth/me (200 and 401 alike):
 * auth ON, no operator provisioned from the environment, and a live setup
 * token. Without it the /setup page must not render a form that can only 404.
 */
export function setupIsAvailable(body: unknown): boolean {
  if (!body || typeof body !== "object") return false;
  return (body as { setup_available?: unknown }).setup_available === true;
}
