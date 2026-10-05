"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch, parseSession, type SessionState } from "@/lib/api/browser";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";

export const SESSION_KEY = queryKeys.session;

export type Actor = "unknown" | "operator" | "viewer";

type LoadedSession = Exclude<SessionState, { status: "loading" }>;

/** 401 is a normal "signed out" answer; any other non-2xx is an error. */
async function fetchSession(): Promise<LoadedSession> {
  const response = await apiFetch("/api/auth/me");
  if (response.status === 401) return { status: "signed-out" };
  if (!response.ok) throw new ApiError(response.status, "session check failed");
  return parseSession(await response.json());
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
