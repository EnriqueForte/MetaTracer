"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage, getJson, hasArray, sendJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { InvitationListResponse, UserListResponse, UserResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

type Account = UserResponse;

const userSchema = z.object({
  username: z.string().trim().min(1, "Enter a username.").max(64, "Usernames are at most 64 characters."),
  password: z.string().min(8, "Passwords need at least 8 characters."),
  role: z.enum(["operator", "viewer"]),
});

const inviteSchema = z.object({
  role: z.enum(["operator", "viewer"]),
  hours: z.number().int("Use whole hours.").min(1, "At least 1 hour.").max(720, "At most 720 hours (30 days)."),
});

export function UsersView() {
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
    onError: (error) => setActionError(errorMessage(error, "Could not create the user")),
  });
  const changeRole = useMutation({
    mutationFn: ({ id, next }: { id: string; next: Account["role"] }) =>
      sendJson(`/api/users/${encodeURIComponent(id)}`, "PATCH", { role: next }),
    onSuccess: refresh,
    onError: (error) => setActionError(errorMessage(error, "Could not change the role")),
  });
  const removeUser = useMutation({
    mutationFn: (id: string) => sendJson(`/api/users/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: refresh,
    onError: (error) => setActionError(errorMessage(error, "Could not delete the user")),
  });
  const createInvite = useMutation({
    mutationFn: (body: { role: string; ttl_seconds: number }) =>
      sendJson<{ code?: unknown }>("/api/invitations", "POST", body),
    onSuccess: (payload) => {
      if (payload && typeof payload.code === "string") setFreshCode(payload.code);
      setCopied(false);
      refresh();
    },
    onError: (error) => setActionError(errorMessage(error, "Could not create the invitation")),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => sendJson(`/api/invitations/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: refresh,
    onError: (error) => setActionError(errorMessage(error, "Could not revoke the invitation")),
  });

  function submitUser() {
    setFormError("");
    setActionError("");
    const parsed = userSchema.safeParse({ username, password, role });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check the form.");
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
      setFormError(parsed.error.issues[0]?.message ?? "Check the form.");
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
    users.isError && !forbidden ? errorMessage(users.error, "Could not load users") : "";
  const error = formError || actionError || loadError;
  const busy = createUser.isPending || createInvite.isPending;
  const accountRows = users.data?.users ?? [];
  const inviteRows = invites.data?.invitations ?? [];

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="mt-title">Users & invitations</h1>
        <div role="tablist" aria-label="Admin sections" className="flex gap-2">
          <Button variant={tab === "users" ? "primary" : "secondary"} role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>Users</Button>
          <Button variant={tab === "invitations" ? "primary" : "secondary"} role="tab" aria-selected={tab === "invitations"} onClick={() => setTab("invitations")}>Invitations</Button>
        </div>
      </div>
      {error ? <p role="alert" className="text-sm text-mt-danger">{error}</p> : null}
      {forbidden ? <p role="alert" className="text-sm text-mt-warning">Operator role required</p> : null}
      {tab === "users" ? (
        <section className="flex flex-col gap-4" aria-label="User accounts">
          <h2 className="text-sm font-semibold">Create user</h2>
          <form className="flex flex-wrap items-end gap-2" noValidate onSubmit={(event) => { event.preventDefault(); submitUser(); }}>
            <div>
              <label htmlFor="new-username" className="text-xs font-semibold text-mt-muted">Username</label>
              <Input id="new-username" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </div>
            <div>
              <label htmlFor="new-password" className="text-xs font-semibold text-mt-muted">Password</label>
              <Input id="new-password" type="password" required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
            </div>
            <div>
              <label htmlFor="new-role" className="text-xs font-semibold text-mt-muted">Role</label>
              <select id="new-role" value={role} onChange={(event) => setRole(event.target.value === "operator" ? "operator" : "viewer")} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm">
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <Button type="submit" disabled={busy}>Create</Button>
          </form>
          {accountRows.length > 0 ? (
            <table className="w-full text-sm">
              <caption className="sr-only">User accounts</caption>
              <thead>
                <tr className="text-left text-xs text-mt-muted">
                  <th className="py-1 font-medium">Username</th>
                  <th className="py-1 font-medium">Role</th>
                  <th className="py-1 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {accountRows.map((user) => (
                  <tr key={user.id} className="border-t border-mt-border">
                    <td className="py-1.5 text-sm text-mt-fg">{user.username}</td>
                    <td className="py-1.5 text-xs text-mt-muted">{user.role}</td>
                    <td className="py-1.5 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="secondary"
                          className="px-2 py-1 text-xs"
                          onClick={() => changeRole.mutate({ id: user.id, next: user.role === "operator" ? "viewer" : "operator" })}
                        >
                          Make {user.role === "operator" ? "viewer" : "operator"}
                        </Button>
                        <Button
                          variant="danger"
                          className="px-2 py-1 text-xs"
                          onClick={() => {
                            if (window.confirm("Delete this user?")) removeUser.mutate(user.id);
                          }}
                        >
                          Delete
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
        <section className="flex flex-col gap-4" aria-label="Invitations">
          {freshCode ? (
            <div role="status" className="rounded-md border border-mt-border-strong bg-mt-surface p-3">
              <p className="text-sm text-mt-fg">Invitation code — shown once. It is not stored in the page after you dismiss it.</p>
              <p className="mt-tech mt-2">{freshCode}</p>
              <div className="mt-2 flex gap-2">
                <Button variant="secondary" onClick={() => void copyCode()}>
                  {copied ? "Copied" : "Copy"}
                </Button>
                <Button variant="secondary" onClick={() => setFreshCode("")}>Dismiss</Button>
              </div>
            </div>
          ) : null}
          <form className="flex flex-wrap items-end gap-2" noValidate onSubmit={(event) => { event.preventDefault(); submitInvite(); }}>
            <div>
              <label htmlFor="invite-role" className="text-xs font-semibold text-mt-muted">Role</label>
              <select id="invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value === "operator" ? "operator" : "viewer")} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm">
                <option value="viewer">Viewer</option>
                <option value="operator">Operator</option>
              </select>
            </div>
            <div>
              <label htmlFor="invite-ttl" className="text-xs font-semibold text-mt-muted">Expires in (hours)</label>
              <Input id="invite-ttl" type="number" min={1} max={720} value={inviteHours} onChange={(event) => setInviteHours(Number(event.target.value))} />
            </div>
            <Button type="submit" disabled={busy}>Create invitation</Button>
          </form>
          {inviteRows.length > 0 ? (
            <table className="w-full text-sm">
              <caption className="sr-only">Invitations</caption>
              <thead>
                <tr className="text-left text-xs text-mt-muted">
                  <th className="py-1 font-medium">Role</th>
                  <th className="py-1 font-medium">Status</th>
                  <th className="py-1 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {inviteRows.map((invite) => (
                  <tr key={invite.id} className="border-t border-mt-border">
                    <td className="py-1.5 text-sm text-mt-fg">{invite.role}</td>
                    <td className="py-1.5 text-sm text-mt-fg">{invite.status}</td>
                    <td className="py-1.5 text-right">
                      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => revoke.mutate(invite.id)}>
                        Revoke
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
