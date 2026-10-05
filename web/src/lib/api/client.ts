import { apiFetch } from "@/lib/api/browser";
import { ApiError, readDetail } from "@/lib/api/errors";

export type Guard<T> = (value: unknown) => value is T;

/** Object whose `key` is an array. Element fields are rendered as text only. */
export function hasArray<K extends string>(key: K) {
  return (value: unknown): value is Record<K, unknown[]> =>
    Boolean(value) &&
    typeof value === "object" &&
    Array.isArray((value as Record<string, unknown>)[key]);
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/** GET a typed JSON body. Non-2xx and shape mismatches throw ApiError; network errors propagate. */
export async function getJson<T>(path: string, guard: (value: unknown) => boolean): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) throw new ApiError(response.status, await readDetail(response));
  const payload: unknown = await response.json();
  if (!guard(payload)) throw new ApiError(response.status, "unexpected response");
  return payload as T;
}

/** Mutation with a JSON body. Returns the parsed body (or null for 204). */
export async function sendJson<T = unknown>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T | null> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await apiFetch(path, init);
  if (!response.ok) throw new ApiError(response.status, await readDetail(response));
  if (response.status === 204) return null;
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Operator role required.";
    return error.detail && error.detail !== "unexpected response"
      ? `${fallback} (${error.detail})`
      : `${fallback} (HTTP ${error.status}).`;
  }
  return "Network error: the API is unreachable.";
}
