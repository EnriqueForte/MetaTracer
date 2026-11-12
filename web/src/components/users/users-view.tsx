"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { errorMessage, getJson, hasArray, sendJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { InvitationListResponse, UserListResponse, UserResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";

type Account = UserResponse;

const userSchema = z.object({
  username: z.string().trim().min(1, "Indica un usuario.").max(64, "Los usuarios tienen como máximo 64 caracteres."),
  password: z.string().min(8, "Las contraseñas necesitan al menos 8 caracteres."),
  role: z.enum(["operator", "viewer"]),
});

const inviteSchema = z.object({
  role: z.enum(["operator", "viewer"]),
  hours: z.number().int("Usa horas enteras.").min(1, "Al menos 1 hora.").max(720, "Como máximo 720 horas (30 días)."),
});

export function UsersView() {
  const actor = useActor();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"users" | "invitations">("users");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"operator" | "viewer">("viewer");
  const [inviteRole, setInviteRole] = useState<"operator" | "viewer">("viewer");
  const [inviteHours, setInviteHours] = useState(24);
  const [freshCode, setFreshCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [formError, setFormError] = useState("");
  const [actionError, setActionError] = useState("");

  const users = useQuery({
    queryKey: queryKeys.users,
    queryFn: () => getJson<UserListResponse>("/api/users", hasArray("users")),
    // Never fetch as viewer: parity with Webhooks/Knowledge (T3).
    enabled: actor === "operator",
  });
  const forbidden = users.error instanceof ApiError && users.error.status === 403;
  const invites = useQuery({
    queryKey: queryKeys.invitations,
    queryFn: () => getJson<InvitationListResponse>("/api/invitations", hasArray("invitations")),
    enabled: users.isSuccess,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.users });
    void queryClient.invalidateQueries({ queryKey: queryKeys.invitations });
  };

  const createUser = useMutation({
    mutationFn: (body: z.infer<typeof userSchema>) => sendJson("/api/users", "POST", body),
    onSuccess: () => {
      setUsername("");
      setPassword("");
      refresh();
    },
    onError: (error) => setActionError(errorMessage(error, "No se pudo crear el usuario")),
  });
  const changeRole = useMutation({
    mutationFn: ({ id, next }: { id: string; next: Account["role"] }) =>
      sendJson(`/api/users/${encodeURIComponent(id)}`, "PATCH", { role: next }),
    onSuccess: refresh,
    onError: (error) => setActionError(errorMessage(error, "No se pudo cambiar el rol")),
  });
  const removeUser = useMutation({
    mutationFn: (id: string) => sendJson(`/api/users/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: refresh,
    onError: (error) => setActionError(errorMessage(error, "No se pudo eliminar el usuario")),
  });
  const createInvite = useMutation({
    mutationFn: (body: { role: string; ttl_seconds: number }) =>
      sendJson<{ code?: unknown }>("/api/invitations", "POST", body),
    onSuccess: (payload) => {
      if (payload && typeof payload.code === "string") setFreshCode(payload.code);
      setCopied(false);
      refresh();
    },
    onError: (error) => setActionError(errorMessage(error, "No se pudo crear la invitación")),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => sendJson(`/api/invitations/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: refresh,
    onError: (error) => setActionError(errorMessage(error, "No se pudo revocar la invitación")),
  });

  function submitUser() {
    setFormError("");
    setActionError("");
    const parsed = userSchema.safeParse({ username, password, role });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Revisa el formulario.");
      return;
    }
    createUser.mutate(parsed.data);
  }

  function submitInvite() {
    setFormError("");
    setActionError("");
    setFreshCode("");
    const parsed = inviteSchema.safeParse({ role: inviteRole, hours: inviteHours });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Revisa el formulario.");
      return;
    }
    createInvite.mutate({ role: parsed.data.role, ttl_seconds: Math.round(parsed.data.hours * 3600) });
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(freshCode);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const loadError =
    users.isError && !forbidden ? errorMessage(users.error, "No se pudieron cargar los usuarios") : "";
  const error = formError || actionError;
  const busy = createUser.isPending || createInvite.isPending;
  const accountRows = users.data?.users ?? [];
  const inviteRows = invites.data?.invitations ?? [];

  if (actor !== "operator") {
    // Parity with Webhooks/Knowledge: a viewer landing here by URL sees the
    // read-only state, never admin controls the API would reject (T3).
    return (
      <div className="flex min-w-0 flex-col gap-3">
        <h1 className="mt-title">Usuarios e invitaciones</h1>
        <p role="alert" className="text-sm text-mt-warning">Se requiere el rol de operador</p>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="mt-title">Usuarios e invitaciones</h1>
        <div role="tablist" aria-label="Secciones de administración" className="flex gap-2">
          <Button variant={tab === "users" ? "primary" : "secondary"} role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>Usuarios</Button>
          <Button variant={tab === "invitations" ? "primary" : "secondary"} role="tab" aria-selected={tab === "invitations"} onClick={() => setTab("invitations")}>Invitaciones</Button>
        </div>
      </div>
      {error ? <ErrorState message={error} /> : null}
      {loadError ? (
        <ErrorState message={loadError} onRetry={() => void users.refetch()} />
      ) : null}
      {forbidden ? <p role="alert" className="text-sm text-mt-warning">Se requiere el rol de operador</p> : null}
      {users.isPending ? <LoadingState label="Cargando usuarios" /> : null}
      {tab === "users" ? (
        <section className="flex flex-col gap-4" aria-label="Cuentas de usuario">
          <h2 className="text-sm font-semibold">Crear usuario</h2>
          <form className="flex flex-wrap items-end gap-2" noValidate onSubmit={(event) => { event.preventDefault(); submitUser(); }}>
            <div>
              <label htmlFor="new-username" className="text-xs font-semibold text-mt-muted">Usuario</label>
              <Input id="new-username" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </div>
            <div>
              <label htmlFor="new-password" className="text-xs font-semibold text-mt-muted">Contraseña</label>
              <Input id="new-password" type="password" required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
            </div>
            <div>
              <label htmlFor="new-role" className="text-xs font-semibold text-mt-muted">Rol</label>
              <select id="new-role" value={role} onChange={(event) => setRole(event.target.value === "operator" ? "operator" : "viewer")} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm">
                <option value="operator">Operador</option>
                <option value="viewer">Visor</option>
              </select>
            </div>
            <Button type="submit" disabled={busy}>Crear</Button>
          </form>
          {users.isSuccess && accountRows.length === 0 ? (
            <EmptyState title="Sin usuarios">
              Crea una cuenta o envía una invitación para dar acceso.
            </EmptyState>
          ) : null}
          {accountRows.length > 0 ? (
            <table className="w-full text-sm">
              <caption className="sr-only">Cuentas de usuario</caption>
              <thead>
                <tr className="text-left text-xs text-mt-muted">
                  <th className="py-1 font-medium">Usuario</th>
                  <th className="py-1 font-medium">Rol</th>
                  <th className="py-1 text-right font-medium">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {accountRows.map((user) => (
                  <tr key={user.id} className="border-t border-mt-border">
                    <td className="py-1.5 text-sm text-mt-fg">{user.username}</td>
                    <td className="py-1.5 text-xs text-mt-muted">{user.role === "operator" ? "operador" : "visor"}</td>
                    <td className="py-1.5 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="secondary"
                          className="px-2 py-1 text-xs"
                          onClick={() => changeRole.mutate({ id: user.id, next: user.role === "operator" ? "viewer" : "operator" })}
                        >
                          Convertir en {user.role === "operator" ? "visor" : "operador"}
                        </Button>
                        <Button
                          variant="danger"
                          className="px-2 py-1 text-xs"
                          onClick={() => {
                            if (window.confirm("¿Eliminar este usuario?")) removeUser.mutate(user.id);
                          }}
                        >
                          Eliminar
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>
      ) : (
        <section className="flex flex-col gap-4" aria-label="Invitaciones">
          {freshCode ? (
            <div role="status" className="rounded-md border border-mt-border-strong bg-mt-surface p-3">
              <p className="text-sm text-mt-fg">Código de invitación — se muestra una vez. No permanece en la página cuando lo descartas.</p>
              <p className="mt-tech mt-2">{freshCode}</p>
              <div className="mt-2 flex gap-2">
                <Button variant="secondary" onClick={() => void copyCode()}>
                  {copied ? "Copiado" : "Copiar"}
                </Button>
                <Button variant="secondary" onClick={() => setFreshCode("")}>Descartar</Button>
              </div>
            </div>
          ) : null}
          <form className="flex flex-wrap items-end gap-2" noValidate onSubmit={(event) => { event.preventDefault(); submitInvite(); }}>
            <div>
              <label htmlFor="invite-role" className="text-xs font-semibold text-mt-muted">Rol</label>
              <select id="invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value === "operator" ? "operator" : "viewer")} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm">
                <option value="viewer">Visor</option>
                <option value="operator">Operador</option>
              </select>
            </div>
            <div>
              <label htmlFor="invite-ttl" className="text-xs font-semibold text-mt-muted">Caduca en (horas)</label>
              <Input id="invite-ttl" type="number" min={1} max={720} value={inviteHours} onChange={(event) => setInviteHours(Number(event.target.value))} />
            </div>
            <Button type="submit" disabled={busy}>Crear invitación</Button>
          </form>
          {inviteRows.length > 0 ? (
            <table className="w-full text-sm">
              <caption className="sr-only">Invitaciones</caption>
              <thead>
                <tr className="text-left text-xs text-mt-muted">
                  <th className="py-1 font-medium">Rol</th>
                  <th className="py-1 font-medium">Estado</th>
                  <th className="py-1 text-right font-medium">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {inviteRows.map((invite) => (
                  <tr key={invite.id} className="border-t border-mt-border">
                    <td className="py-1.5 text-sm text-mt-fg">{invite.role === "operator" ? "operador" : "visor"}</td>
                    <td className="py-1.5 text-sm text-mt-fg">{invite.status}</td>
                    <td className="py-1.5 text-right">
                      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => revoke.mutate(invite.id)}>
                        Revocar
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>
      )}
    </div>
  );
}
