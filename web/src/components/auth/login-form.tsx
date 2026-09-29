"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, csrfTokenFromCookie } from "@/lib/api/browser";
import { BASE_PATH } from "@/lib/constants";

async function ensureCsrf(): Promise<"on" | "off" | "in"> {
  const response = await apiFetch("/api/auth/me");
  if (response.status === 401) return "on";
  if (!response.ok) return "on";
  const payload: unknown = await response.json();
  if (payload && typeof payload === "object" && (payload as { authenticated?: unknown }).authenticated === true) {
    return "in";
  }
  return "off";
}

export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authOn, setAuthOn] = useState(false);

  useEffect(() => {
    void ensureCsrf().then((state) => {
      if (state === "in") window.location.assign(`${BASE_PATH}/`);
      setAuthOn(state === "on");
    });
  }, []);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfTokenFromCookie(),
        },
        body: JSON.stringify({ username, password }),
      });
      if (response.ok) {
        window.location.assign(`${BASE_PATH}/`);
        return;
      }
      setError(
        response.status === 401
          ? "Invalid username or password."
          : response.status === 429
            ? "Too many attempts; wait a moment and retry."
            : `Login failed (HTTP ${response.status}).`,
      );
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
          <h1 className="mt-title">Sign in</h1>
          <p className="text-sm text-mt-fg">MetaTracer control panel access.</p>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-mt-danger">{error}</p>
        ) : null}
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label htmlFor="username" className="text-xs font-semibold text-mt-muted">Username</label>
          <Input id="username" name="username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
          <label htmlFor="password" className="text-xs font-semibold text-mt-muted">Password</label>
          <Input id="password" name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          <Button type="submit" className="w-full" disabled={busy}>{busy ? "Checking…" : "Sign in"}</Button>
        </form>
        {authOn ? (
          <p className="text-xs text-mt-muted">
            Have an invitation code?{" "}
            <Link href="/register" className="text-mt-accent-hover underline">Create your account</Link>
          </p>
        ) : null}
      </div>
      <p className="text-xs text-mt-muted">Authentication protects the Web UI and API. The CLI on localhost does not require login.</p>
    </main>
  );
}
