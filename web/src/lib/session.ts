"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch, parseSession, type SessionState } from "@/lib/api/browser";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";

export const SESSION_KEY = queryKeys.session;

export type Actor = "unknown" | "operator" | "viewer";

type LoadedSession = Exclude<SessionState, { status: "loading" }>;

/** Persist the double-submit token where csrfTokenFromCookie() reads it. */
export function persistCsrfToken(token: string | null): void {
  if (typeof document === "undefined" || !token) return;
  let meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
  if (!meta) {
    meta = document.createElement("meta") as HTMLMetaElement;
    meta.name = "csrf-token";
    document.head.appendChild(meta);
  }
  meta.content = token;
}

/** 401 is a normal "signed out" answer; any other non-2xx is an error. */
async function fetchSession(): Promise<LoadedSession> {
  const response = await apiFetch("/api/auth/me");
  if (response.status === 401) {
    // /me hands the pre-session token in the response header (MIN-01 parity);
    // without a session there is no body to carry it.
    persistCsrfToken(response.headers.get("x-csrf-token"));
    return { status: "signed-out" };
  }
  if (!response.ok) throw new ApiError(response.status, "session check failed");
  const body = await response.json();
  // A signed-in /me exposes the token in the JSON; keep the meta in sync so
  // mutations send the same value the server expects from the cookie.
  if (body && typeof body === "object" && typeof (body as { csrf_token?: unknown }).csrf_token === "string") {
    persistCsrfToken((body as { csrf_token: string }).csrf_token);
  }
  return parseSession(body);
}

export function useSessionQuery() {
  return useQuery({ queryKey: SESSION_KEY, queryFn: fetchSession, staleTime: 60_000 });
}

export function useSession(): SessionState {
  const query = useSessionQuery();
  if (query.isPending) return { status: "loading" };
  if (query.isError) return { status: "signed-out" };
  return query.data;
}

/** Operator (or auth off) may mutate. Viewers and unknown sessions may not. */
export function actorOf(session: SessionState): Actor {
  if (session.status === "auth-off") return "operator";
  if (session.status === "signed-in") return session.role;
  return "unknown";
}

export function useActor(): Actor {
  return actorOf(useSession());
}
