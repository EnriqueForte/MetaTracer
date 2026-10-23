import type { NotificationResponse } from "@/lib/api/types";

export function csrfTokenFromCookie(): string {
  if (typeof document === "undefined") return "";
  // The double-submit token is delivered in-page by the server: every page
  // shell emits <meta name="csrf-token" content="..."> (see base.html and the
  // standalone auth templates). JS echoes it back in the X-CSRF-Token header.
  //
  // Reading the raw cookie from JS is NOT a browser API (document.cookie only
  // exists as a jsdom shim), so the meta tag is the only portable channel.
  const meta = document.querySelector('meta[name="csrf-token"]');
  const content = meta ? meta.getAttribute("content") ?? "" : "";
  return content;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method === "POST" || method === "PUT" || method === "PATCH" || method === "DELETE") {
    headers.set("x-csrf-token", csrfTokenFromCookie());
  }
  return fetch(path, { ...init, headers, credentials: "same-origin" });
}

export type SessionState =
  | { status: "loading" }
  | { status: "auth-off" }
  | { status: "signed-in"; username: string; role: "operator" | "viewer" }
  | { status: "signed-out" };

export function parseSession(value: unknown): Exclude<SessionState, { status: "loading" }> {
  if (!value || typeof value !== "object") return { status: "signed-out" };
  const row = value as Record<string, unknown>;
  if (row.authenticated === false) return { status: "auth-off" };
  if (
    row.authenticated === true &&
    typeof row.username === "string" &&
    (row.role === "operator" || row.role === "viewer")
  ) {
    return { status: "signed-in", username: row.username, role: row.role };
  }
  return { status: "signed-out" };
}

/** A terminal-run notification; `kind` is narrowed to the terminal statuses. */
export type NotificationItem = Omit<NotificationResponse, "kind"> & {
  kind: "completed" | "failed" | "aborted";
};

export function parseNotifications(value: unknown): NotificationItem[] | null {
  if (!value || typeof value !== "object") return null;
  const rows = (value as { notifications?: unknown }).notifications;
  if (!Array.isArray(rows)) return null;
  const items: NotificationItem[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const entry = row as Record<string, unknown>;
    if (typeof entry.id !== "number") return null;
    if (entry.kind !== "completed" && entry.kind !== "failed" && entry.kind !== "aborted") {
      return null;
    }
    if (typeof entry.target !== "string") return null;
    if (typeof entry.total_assets !== "number" || typeof entry.total_findings !== "number") {
      return null;
    }
    if (
      entry.error_message !== null &&
      entry.error_message !== undefined &&
      typeof entry.error_message !== "string"
    ) {
      return null;
    }
    items.push({
      id: entry.id,
      kind: entry.kind,
      run_id: typeof entry.run_id === "string" ? entry.run_id : "",
      target: entry.target,
      total_assets: entry.total_assets,
      total_findings: entry.total_findings,
      error_message: typeof entry.error_message === "string" ? entry.error_message : null,
      created_at: typeof entry.created_at === "string" ? entry.created_at : "",
    });
  }
  return items;
}

export function truncate(text: string, limit: number): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  return collapsed.length <= limit ? collapsed : `${collapsed.slice(0, limit - 3)}...`;
}
