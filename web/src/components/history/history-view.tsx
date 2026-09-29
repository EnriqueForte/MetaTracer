"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/browser";

const STATUSES = ["all", "completed", "failed", "running", "pending", "aborted"] as const;
type StatusFilter = (typeof STATUSES)[number];
type RunStatus = Exclude<StatusFilter, "all">;

const STATUS_LABEL: Record<StatusFilter, string> = {
  all: "All",
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  aborted: "Aborted",
};

type HistoryRun = {
  run_id: string;
  status: RunStatus;
  target: string;
  scope: string[];
  total_assets: number;
  total_findings: number;
  started_at: string;
};

function formatWhen(value: string): string {
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", "").replace("Z", "");
}

function parsePage(value: unknown): { total: number; runs: HistoryRun[]; has_more: boolean; next_cursor: string | null } | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  if (typeof row.total !== "number" || !Array.isArray(row.runs)) return null;
  const runs: HistoryRun[] = [];
  for (const item of row.runs) {
    if (!item || typeof item !== "object") return null;
    const run = item as Record<string, unknown>;
    if (typeof run.run_id !== "string" || typeof run.target !== "string" || typeof run.started_at !== "string") {
      return null;
    }
    if (
      run.status !== "pending" &&
      run.status !== "running" &&
      run.status !== "completed" &&
      run.status !== "failed" &&
      run.status !== "aborted"
    ) {
      return null;
    }
    if (typeof run.total_assets !== "number" || typeof run.total_findings !== "number") return null;
    if (!Array.isArray(run.scope) || !run.scope.every((domain) => typeof domain === "string")) return null;
    runs.push({
      run_id: run.run_id,
      status: run.status,
      target: run.target,
      scope: run.scope,
      total_assets: run.total_assets,
      total_findings: run.total_findings,
      started_at: run.started_at,
    });
  }
  return {
    total: row.total,
    runs,
    has_more: row.has_more === true,
    next_cursor: typeof row.next_cursor === "string" ? row.next_cursor : null,
  };
}

export function HistoryView() {
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [totalRuns, setTotalRuns] = useState(0);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([]);
  const [currentCursor, setCurrentCursor] = useState<string | null>(null);

  const fetchPage = useCallback(async (status: StatusFilter, cursor: string | null) => {
    const params = new URLSearchParams();
    params.set("limit", "50");
    if (status !== "all") params.set("status", status);
    if (cursor) params.set("cursor", cursor);
    const response = await apiFetch(`/api/runs?${params.toString()}`);
    if (!response.ok) throw new Error("load");
    const parsed = parsePage(await response.json());
    if (!parsed) throw new Error("shape");
    return parsed;
  }, []);

  const load = useCallback(async () => {
    setError("");
    setCursorStack([]);
    setCurrentCursor(null);
    try {
      const page = await fetchPage(statusFilter, null);
      setRuns(page.runs);
      setTotalRuns(page.total);
      setNextCursor(page.next_cursor);
      setHasMore(page.has_more);
      setLoaded(true);
    } catch {
      setError("Could not load the local history.");
      setLoaded(true);
    }
  }, [fetchPage, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadNext() {
    if (!hasMore || loadingMore || !nextCursor) return;
    setLoadingMore(true);
    setError("");
    try {
      const page = await fetchPage(statusFilter, nextCursor);
      setCursorStack((stack) => [...stack, currentCursor]);
      setCurrentCursor(nextCursor);
      setRuns(page.runs);
      setNextCursor(page.next_cursor);
      setHasMore(page.has_more);
    } catch {
      setError("Network error: the API is unreachable.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function loadPrevious() {
    if (cursorStack.length === 0 || loadingMore) return;
    setLoadingMore(true);
    setError("");
    const previous = cursorStack[cursorStack.length - 1] ?? null;
    try {
      const page = await fetchPage(statusFilter, previous);
      setCursorStack((stack) => stack.slice(0, -1));
      setCurrentCursor(previous);
      setRuns(page.runs);
      setNextCursor(page.next_cursor);
      setHasMore(page.has_more);
    } catch {
      setError("Network error: the API is unreachable.");
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mt-title">Local history</h1>
          <p className="text-sm text-mt-fg">
            Runs stored in this installation. Reopen a scan to review findings or re-export the report. This is not a multi-user dashboard.
          </p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/">New scan</Link>
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {STATUSES.map((status) => (
          <Button
            key={status}
            variant="secondary"
            className="px-2 py-1 text-xs"
            aria-pressed={statusFilter === status}
            aria-label={`Filter by status ${status}`}
            onClick={() => setStatusFilter(status)}
          >
            {STATUS_LABEL[status]}
          </Button>
        ))}
      </div>
      <p className="text-xs text-mt-muted" aria-live="polite">
        {loaded && !error ? `${totalRuns} ${totalRuns === 1 ? "run" : "runs"}` : ""}
      </p>
      {!loaded && !error ? <p className="text-sm text-mt-muted">Loading history…</p> : null}
      {error ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-mt-danger-border bg-mt-danger-bg p-3 text-sm">
          <p>{error}</p>
          <Button variant="secondary" onClick={() => void load()}>Retry</Button>
        </div>
      ) : null}
      {loaded && !error && runs.length === 0 ? (
        <p className="text-sm text-mt-muted">No runs yet. Start a scan to build a local history.</p>
      ) : null}
      {runs.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">Local scan history</caption>
          <thead>
            <tr className="text-left text-xs text-mt-muted">
              <th className="py-1 font-medium">Status</th>
              <th className="py-1 font-medium">Target</th>
              <th className="py-1 text-right font-medium">Assets</th>
              <th className="py-1 text-right font-medium">Findings</th>
              <th className="py-1 font-medium">Started (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id} className="border-t border-mt-border">
                <td className="py-1.5">
                  <Badge variant={run.status}>{STATUS_LABEL[run.status]}</Badge>
                </td>
                <td className="py-1.5">
                  <Link href={`/runs/${encodeURIComponent(run.run_id)}`} className="mt-tech underline">
                    {run.target}
                  </Link>
                  {run.scope.length > 0 ? <p className="mt-tech">{run.scope.join(", ")}</p> : null}
                </td>
                <td className="py-1.5 text-right tabular-nums">{run.total_assets}</td>
                <td className="py-1.5 text-right tabular-nums">{run.total_findings}</td>
                <td className="mt-tech py-1.5">{formatWhen(run.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {loaded && runs.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="secondary" disabled={cursorStack.length === 0 || loadingMore} onClick={() => void loadPrevious()}>
            Newer
          </Button>
          {loadingMore ? <span className="text-xs text-mt-muted">Loading more…</span> : null}
          <Button variant="secondary" disabled={!hasMore || loadingMore} onClick={() => void loadNext()}>
            Older
          </Button>
        </div>
      ) : null}
    </div>
  );
}
