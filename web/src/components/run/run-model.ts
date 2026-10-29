import { apiFetch } from "@/lib/api/browser";
import { ApiError, readDetail } from "@/lib/api/errors";
import type { RunStatus, RunStatusResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

export type RunSnapshot = RunStatusResponse;

export const runKey = queryKeys.run;

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  aborted: "Aborted",
};

export const TERMINAL: ReadonlySet<RunStatus> = new Set(["completed", "failed", "aborted"]);

export function isLive(status: RunStatus): boolean {
  return status === "pending" || status === "running";
}

function isRunSnapshot(value: unknown): value is RunSnapshot {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.run_id === "string" &&
    typeof row.status === "string" &&
    typeof row.target === "string" &&
    Array.isArray(row.scope) &&
    typeof row.total_assets === "number" &&
    typeof row.total_findings === "number"
  );
}

export async function fetchRun(runId: string): Promise<RunSnapshot> {
  const response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) throw new ApiError(response.status, await readDetail(response));
  const payload: unknown = await response.json();
  if (!isRunSnapshot(payload)) throw new ApiError(200, "unexpected response");
  return { ...payload, asset_issues: Array.isArray(payload.asset_issues) ? payload.asset_issues : [] };
}

export function asRunSnapshot(value: unknown): RunSnapshot | null {
  return isRunSnapshot(value)
    ? { ...value, asset_issues: Array.isArray(value.asset_issues) ? value.asset_issues : [] }
    : null;
}

export const EXPORTS = [
  ["md", "Download Markdown"],
  ["json", "Download JSON"],
  ["html", "Download HTML"],
  ["csv", "Download CSV"],
  ["bounty", "Download Bounty TXT"],
] as const;

export const REDACTIONS = [
  ["contacts", "Contacts"],
  ["coordinates", "Coordinates"],
  ["all", "Contacts and coordinates"],
  ["none", "None"],
] as const;

export type Redaction = (typeof REDACTIONS)[number][0];

export function exportHref(
  runId: string,
  format: (typeof EXPORTS)[number][0],
  redact: Redaction = "contacts",
): string {
  const query = new URLSearchParams({ format, redact });
  return `/api/runs/${encodeURIComponent(runId)}/export?${query.toString()}`;
}
