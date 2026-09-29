"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api/browser";

type Account = { id: string; username: string; role: "operator" | "viewer" };
type Invitation = { id: string; role: string; status: string; expires_at: string };

function parseUsers(value: unknown): Account[] | null {
  if (!value || typeof value !== "object") return null;
  const rows = (value as { users?: unknown }).users;
  if (!Array.isArray(rows)) return null;
  const users: Account[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const item = row as Record<string, unknown>;
    if (typeof item.id !== "string" || typeof item.username !== "string") return null;
    if (item.role !== "operator" && item.role !== "viewer") return null;
    users.push({ id: item.id, username: item.username, role: item.role });
  }
  return users;
}

function parseInvites(value: unknown): Invitation[] | null {
  if (!value || typeof value !== "object") return null;
  const rows = (value as { invitations?: unknown }).invitations;
  if (!Array.isArray(rows)) return null;
  const invites: Invitation[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const item = row as Record<string, unknown>;
    if (typeof item.id !== "string" || typeof item.role !== "string" || typeof item.status !== "string") return null;
    invites.push({
      id: item.id,
      role: item.role,
      status: item.status,
      expires_at: typeof item.expires_at === "string" ? item.expires_at : "",
    });
  }
  return invites;
}

export function UsersView() {
  const [tab, setTab] = useState<"users" | "invitations">("users");
  const [users, setUsers] = useState<Account[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"operator" | "viewer">("viewer");
  const [inviteRole, setInviteRole] = useState<"operator" | "viewer">("viewer");
  const [inviteHours, setInviteHours] = useState(24);
  const [freshCode, setFreshCode] = useState("");
  const [busy, setBusy] = useState(false);

  const loadAll = useCallback(async () => {
    setError("");
    setForbidden(false);
    const usersResponse = await apiFetch("/api/users");
    if (usersResponse.status === 403) {
      setForbidden(true);
      return;
    }
    if (!usersResponse.ok) {
      setError("Could not load users.");
      return;
    }
    const parsedUsers = parseUsers(await usersResponse.json());
    if (!parsedUsers) {
      setError("Could not load users.");
      return;
    }
    setUsers(parsedUsers);
    const invitesResponse = await apiFetch("/api/invitations");
    if (!invitesResponse.ok) return;
    const parsedInvites = parseInvites(await invitesResponse.json());
    if (parsedInvites) setInvites(parsedInvites);
  }, []);

  useEffect(() => {
    void loadAll().catch(() => setError("Network error: the API is unreachable."));
  }, [loadAll]);

  async function createUser() {
    setBusy(true);
    setError("");
    try {
      const response = await apiFetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, role }),
      });
      if (!response.ok) {
        setError(`Could not create the user (HTTP ${response.status}).`);
        return;
      }
      setUsername("");
      setPassword("");
      await loadAll();
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(id: string, next: "operator" | "viewer") {
    const response = await apiFetch(`/api/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: next }),
    });
    if (!response.ok) {
      setError(`Could not change the role (HTTP ${response.status}).`);
      return;
    }
    await loadAll();
  }

  async function removeUser(id: string) {
    if (!window.confirm("Delete this user?")) return;
    const response = await apiFetch(`/api/users/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (response.status !== 204) {
      setError(`Could not delete the user (HTTP ${response.status}).`);
      return;
    }
    await loadAll();
  }

  async function createInvite() {
    setBusy(true);
    setFreshCode("");
    setError("");
    try {
      const response = await apiFetch("/api/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: inviteRole, ttl_seconds: Math.round(inviteHours * 3600) }),
      });
      if (!response.ok) {
        setError(`Could not create the invitation (HTTP ${response.status}).`);
        return;
      }
      const payload: unknown = await response.json();
      const code = payload && typeof payload === "object" ? (payload as { code?: unknown }).code : null;
      if (typeof code === "string") setFreshCode(code);
      await loadAll();
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    const response = await apiFetch(`/api/invitations/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (response.status !== 204) {
      setError(`Could not revoke the invitation (HTTP ${response.status}).`);
      return;
    }
    await loadAll();
  }

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
          <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void createUser(); }}>
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
          {users.length > 0 ? (
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
                {users.map((user) => (
                  <tr key={user.id} className="border-t border-mt-border">
                    <td className="py-1.5 text-sm text-mt-fg">{user.username}</td>
                    <td className="py-1.5 text-xs text-mt-muted">{user.role}</td>
                    <td className="py-1.5 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="secondary"
                          className="px-2 py-1 text-xs"
                          onClick={() => void changeRole(user.id, user.role === "operator" ? "viewer" : "operator")}
                        >
                          Make {user.role === "operator" ? "viewer" : "operator"}
                        </Button>
                        <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => void removeUser(user.id)}>
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
              <Button variant="secondary" className="mt-2" onClick={() => setFreshCode("")}>Dismiss</Button>
            </div>
          ) : null}
          <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void createInvite(); }}>
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
          {invites.length > 0 ? (
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
                {invites.map((invite) => (
                  <tr key={invite.id} className="border-t border-mt-border">
                    <td className="py-1.5 text-sm text-mt-fg">{invite.role}</td>
                    <td className="py-1.5 text-sm text-mt-fg">{invite.status}</td>
                    <td className="py-1.5 text-right">
                      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => void revoke(invite.id)}>
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
