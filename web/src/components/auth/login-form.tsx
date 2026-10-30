"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthPanel } from "@/components/auth/auth-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, csrfTokenFromCookie } from "@/lib/api/browser";
import { setupIsAvailable } from "@/lib/api/auth-mode";
import { persistCsrfToken } from "@/lib/session";
import { BASE_PATH } from "@/lib/constants";

type Gate = { auth: "on" | "off" | "in"; setup: boolean };

async function ensureCsrf(): Promise<Gate> {
  const response = await apiFetch("/api/auth/me");
  // GET /me mints+returns the pre-session CSRF token in the response header
  // (401) or body (200); persist it so csrfTokenFromCookie() can echo it.
  if (response.status === 401) {
    persistCsrfToken(response.headers.get("x-csrf-token"));
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    return { auth: "on", setup: setupIsAvailable(payload) };
  }
  if (!response.ok) return { auth: "on", setup: false };
  const payload: unknown = await response.json();
  if (payload && typeof payload === "object" && (payload as { authenticated?: unknown }).authenticated === true) {
    persistCsrfToken(
      typeof (payload as { csrf_token?: unknown }).csrf_token === "string"
        ? (payload as { csrf_token: string }).csrf_token
        : null,
    );
    return { auth: "in", setup: false };
  }
  return { auth: "off", setup: setupIsAvailable(payload) };
}

export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authOn, setAuthOn] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);

  useEffect(() => {
    void ensureCsrf().then((state) => {
      if (state.auth === "in") window.location.assign(`${BASE_PATH}/`);
      setAuthOn(state.auth === "on");
      setSetupOpen(state.setup);
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
    <AuthPanel
      title="Sign in"
      lede="Control panel for authorized metadata discovery. A scan still requires a confirmed scope."
      note={
        <p>Authentication protects the Web UI and API. The CLI on localhost does not require login.</p>
      }
    >
      {error ? (
        <p role="alert" className="text-sm text-mt-danger">{error}</p>
      ) : null}
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="username" className="text-xs text-mt-muted">Username</label>
        <Input id="username" name="username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
        <label htmlFor="password" className="text-xs text-mt-muted">Password</label>
        <Input id="password" name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Checking…" : "Sign in"}</Button>
      </form>
      {setupOpen ? (
        <p className="text-xs text-mt-muted">
          This installation has no operator yet.{" "}
          <Link href="/setup" className="text-mt-accent-hover underline">
            Create the first account
          </Link>
        </p>
      ) : null}
      {authOn && !setupOpen ? (
        <p className="text-xs text-mt-muted">
          Have an invitation code?{" "}
          <Link href="/register" className="text-mt-accent-hover underline">Create your account</Link>
        </p>
      ) : null}
    </AuthPanel>
  );
}
