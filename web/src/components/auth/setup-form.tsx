"use client";

import { useEffect, useState } from "react";

import { AuthPanel } from "@/components/auth/auth-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, csrfTokenFromCookie } from "@/lib/api/browser";
import { persistCsrfToken } from "@/lib/session";
import { BASE_PATH } from "@/lib/constants";

export function SetupForm() {
  const [setupToken, setSetupToken] = useState("");
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
      const response = await fetch("/api/auth/setup", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfTokenFromCookie() },
        body: JSON.stringify({ setup_token: setupToken, username, password }),
      });
      if (response.ok) {
        window.location.assign(`${BASE_PATH}/`);
        return;
      }
      const payload: unknown = await response.json().catch(() => null);
      const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : null;
      setError(typeof detail === "string" ? detail : `La configuración inicial falló (HTTP ${response.status}).`);
    } catch {
      setError("No se pudo contactar con el servidor.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthPanel
      title="Configuración inicial"
      lede="Crea el primer operador con el token de configuración del registro del servidor."
    >
      {error ? <p role="alert" className="text-sm text-mt-danger">{error}</p> : null}
      <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label htmlFor="setup-token" className="text-xs text-mt-muted">Token de configuración</label>
        <Input id="setup-token" type="password" required autoComplete="off" value={setupToken} onChange={(event) => setSetupToken(event.target.value)} />
        <label htmlFor="username" className="text-xs text-mt-muted">Usuario</label>
        <Input id="username" required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
        <label htmlFor="password" className="text-xs text-mt-muted">Contraseña</label>
        <Input id="password" type="password" required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        <p className="text-xs text-mt-muted">Mínimo 8 caracteres.</p>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creando…" : "Crear operador"}</Button>
      </form>
    </AuthPanel>
  );
}
