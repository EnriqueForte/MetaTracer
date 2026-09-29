"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, csrfTokenFromCookie } from "@/lib/api/browser";
import { BASE_PATH } from "@/lib/constants";

export function RegisterForm() {
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void apiFetch("/api/auth/me");
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
    <main id="main-content" className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-4 px-4 py-16">
      <div className="flex flex-col gap-4 rounded-md border border-mt-border bg-mt-surface p-4">
        <div>
          <p className="text-xs text-mt-muted">MetaTracer</p>
          <h1 className="mt-title">Create your account</h1>
          <p className="text-sm text-mt-fg">Redeem the invitation code you received.</p>
        </div>
        {error ? <p role="alert" className="text-sm text-mt-danger">{error}</p> : null}
        <form className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <label htmlFor="code" className="text-xs font-semibold text-mt-muted">Invitation code</label>
          <Input id="code" required autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} />
          <label htmlFor="username" className="text-xs font-semibold text-mt-muted">Username</label>
          <Input id="username" required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
          <label htmlFor="password" className="text-xs font-semibold text-mt-muted">Password</label>
          <Input id="password" type="password" required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
          <p className="text-xs text-mt-muted">Minimum 8 characters.</p>
          <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
        </form>
      </div>
      <p className="text-xs text-mt-muted">
        Have an account already? <Link href="/login" className="text-mt-accent-hover underline">Back to sign in</Link>
      </p>
    </main>
  );
}
