import { notFound } from "next/navigation";

import { RegisterForm } from "@/components/auth/register-form";
import { installationHasAuthOff } from "@/lib/api/auth-mode";
import { apiOrigin } from "@/lib/api/origin";

export const dynamic = "force-dynamic";

export default async function RegisterPage() {
  try {
    const response = await fetch(`${apiOrigin()}/api/auth/me`, { cache: "no-store" });
    const body: unknown = await response.json().catch(() => null);
    if (installationHasAuthOff(response.status, body)) notFound();
  } catch {
    // The API is down. The form stays; the POST fails closed.
  }
  return <RegisterForm />;
}
