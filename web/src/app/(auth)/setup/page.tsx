import { notFound, redirect } from "next/navigation";

import { SetupForm } from "@/components/auth/setup-form";
import { installationHasAuthOff, setupIsAvailable } from "@/lib/api/auth-mode";
import { apiOrigin } from "@/lib/api/origin";

export const dynamic = "force-dynamic";

/**
 * First-run setup (T9). Mirrors the three gates of the V1 page so the form is
 * never rendered where it could only 404:
 *
 * - auth OFF ................ the setup flow does not exist -> 404
 * - already provisioned ..... setup is closed -> /login
 * - API unreachable ......... the form stays; the POST fails closed
 *
 * redirect()/notFound() throw framework signals, so they run OUTSIDE the
 * fetch try/catch: catching them would swallow the navigation.
 */
export default async function SetupPage() {
  let status = 0;
  let body: unknown = null;
  try {
    const response = await fetch(`${apiOrigin()}/api/auth/me`, { cache: "no-store" });
    status = response.status;
    body = await response.json().catch(() => null);
  } catch {
    // The API is down. The form stays; the POST fails closed.
  }

  if (installationHasAuthOff(status, body)) notFound();
  if (status === 200 && !setupIsAvailable(body)) redirect("/login");
  return <SetupForm />;
}