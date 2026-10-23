"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthPanel } from "@/components/auth/auth-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, csrfTokenFromCookie } from "@/lib/api/browser";
import { persistCsrfToken } from "@/lib/session";
import { BASE_PATH } from "@/lib/constants";

export function RegisterForm() {
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    // Bootstrap: GET /me mints the pre-session CSRF token (header on 401,
    // body on 200) and persists it for csrfTokenFromCookie() in submit().
    void apiFetch("/api/auth/me")
      .then(async (response) => {
        if (response.status === 401) {
          persistCsrfToken(response.headers.get("x-csrf-token"));
          return;
        }
        if (!response.ok) return;
        const payload: unknown = await response.json();
        if (payload && typeof payload === "object") {
          const csrf = (payload as { csrf_token?: unknown }).csrf_token;
          persistCsrfToken(typeof csrf === "string" ? csrf : null);
        }
      })
      .catch(() => {});
  }, []);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfTokenFromCookie() },
        body: JSON.stringify({ code, username, password }),
      });
      if (response.ok) {
        window.location.assign(`${BASE_PATH}/`);
        return;
      }
      const payload: unknown = await response.json().catch(() => null);
      const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : null;
      setError(typeof detail === "string" ? detail : `Registration failed (HTTP ${response.status}).`);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthPanel
      title="Create your account"
      lede="Redeem the invitation code you received."
      note={
        <p>
          Have an account already? <Link href="/login" className="text-mt-accent-hover underline">Back to sign in</Link>
        </p>
      }
    >
      {error ? <p role="alert" className="text-sm text-mt-danger">{error}</p> : null}
      <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label htmlFor="code" className="text-xs text-mt-muted">Invitation code</label>
        <Input id="code" required autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} />
        <label htmlFor="username" className="text-xs text-mt-muted">Username</label>
        <Input id="username" required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
        <label htmlFor="password" className="text-xs text-mt-muted">Password</label>
        <Input id="password" type="password" required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        <p className="text-xs text-mt-muted">Minimum 8 characters.</p>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
      </form>
    </AuthPanel>
  );
}
