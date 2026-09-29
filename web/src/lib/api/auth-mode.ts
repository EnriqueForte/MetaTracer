/** True only when GET /api/auth/me says this installation has auth disabled. */
export function installationHasAuthOff(status: number, body: unknown): boolean {
  if (status !== 200 || !body || typeof body !== "object") return false;
  return (body as { authenticated?: unknown }).authenticated === false;
}
