"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DeleteRunDialog } from "@/components/run/run-actions";
import { RUN_STATUS_LABEL } from "@/components/run/run-model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { getJson, hasArray } from "@/lib/api/client";
import type { RunListItem, RunListResponse, RunStatus } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";
import { formatWhen } from "@/lib/time";

const STATUSES = ["all", "completed", "failed", "running", "pending", "aborted"] as const;
type StatusFilter = (typeof STATUSES)[number];

const FILTER_LABEL: Record<StatusFilter, string> = { all: "All", ...RUN_STATUS_LABEL };

function isStatusFilter(value: string | null): value is StatusFilter {
  return value !== null && (STATUSES as readonly string[]).includes(value);
}

function statusFromSearch(): StatusFilter {
  const raw = new URLSearchParams(window.location.search).get("status");
  return isStatusFilter(raw) ? raw : "all";
}

function writeStatus(status: StatusFilter) {
  const params = new URLSearchParams(window.location.search);
  if (status === "all") params.delete("status");
  else params.set("status", status);
  const search = params.toString();
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`,
  );
}

function fetchPage(status: StatusFilter, cursor: string | null): Promise<RunListResponse> {
  const params = new URLSearchParams();
  params.set("limit", "50");
  if (status !== "all") params.set("status", status);
  if (cursor) params.set("cursor", cursor);
  return getJson<RunListResponse>(`/api/runs?${params.toString()}`, hasArray("runs"));
}

function isActive(status: RunStatus): boolean {
  return status === "pending" || status === "running";
}

export function HistoryView() {
  const actor = useActor();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(statusFromSearch);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<RunListItem | null>(null);
  const [compare, setCompare] = useState<string[]>([]);

  const page = useQuery({
    queryKey: [...queryKeys.runs, statusFilter, cursor],
    queryFn: () => fetchPage(statusFilter, cursor),
    placeholderData: keepPreviousData,
  });
  const runs = page.data?.runs ?? [];
  const totalRuns = page.data?.total ?? 0;
  const hasMore = page.data?.has_more === true;
  const nextCursor = page.data?.next_cursor ?? null;
  const loaded = page.isSuccess || page.isError;
  const error = page.isError ? "Could not load the local history." : "";

  function changeStatus(next: StatusFilter) {
    setStatusFilter(next);
    writeStatus(next);
    setCursor(null);
    setCursorStack([]);
  }

  function toggleCompare(runId: string) {
    setCompare((current) =>
      current.includes(runId)
        ? current.filter((id) => id !== runId)
        : [...current, runId].slice(-2),
    );
  }

  const compareHref =
    compare.length === 2
      ? `/runs/compare?a=${encodeURIComponent(compare[0])}&b=${encodeURIComponent(compare[1])}`
      : "";

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mt-title">Local history</h1>
          <p className="text-sm text-mt-fg">
            Runs stored in this installation. Reopen a scan to review findings or re-export the report. This is not a multi-user dashboard.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {compareHref ? (
            <Button variant="secondary" asChild>
              <Link href={compareHref}>Compare selected</Link>
            </Button>
          ) : (
            <Button variant="secondary" disabled>
              Compare selected
            </Button>
          )}
          <Button variant="secondary" asChild>
            <Link href="/">New scan</Link>
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Status filter">
        {STATUSES.map((status) => (
          <Button
            key={status}
            variant="toggle"
            aria-pressed={statusFilter === status}
            aria-label={`Filter by status ${status}`}
            onClick={() => changeStatus(status)}
          >
            {FILTER_LABEL[status]}
          </Button>
        ))}
      </div>
      <p className="text-xs text-mt-muted" aria-live="polite">
        {loaded && !error ? `${totalRuns} ${totalRuns === 1 ? "run" : "runs"}` : ""}
        {compare.length > 0 ? ` · ${compare.length} of 2 selected to compare` : ""}
      </p>
      {!loaded ? <p className="text-sm text-mt-muted">Loading history…</p> : null}
      {error ? <ErrorState message={error} onRetry={() => void page.refetch()} /> : null}
      {loaded && !error && runs.length === 0 ? (
        <EmptyState title="No runs yet">Start a scan to build a local history.</EmptyState>
      ) : null}
      {runs.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">Local scan history</caption>
          <thead>
            <tr className="text-left text-xs text-mt-muted">
              <th className="py-1 font-medium">
                <span className="sr-only">Compare</span>
              </th>
              <th className="py-1 font-medium">Status</th>
              <th className="py-1 font-medium">Target</th>
              <th className="py-1 text-right font-medium">Assets</th>
              <th className="py-1 text-right font-medium">Findings</th>
              <th className="py-1 font-medium">Started (UTC)</th>
              {actor === "operator" ? <th className="py-1 font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id} className="border-t border-mt-border">
                <td className="py-1.5 pr-2">
                  {run.status === "completed" ? (
                    <input
                      type="checkbox"
                      aria-label={`Select ${run.target} to compare`}
                      checked={compare.includes(run.run_id)}
                      onChange={() => toggleCompare(run.run_id)}
                    />
                  ) : null}
                </td>
                <td className="py-1.5">
                  <Badge variant={run.status}>{RUN_STATUS_LABEL[run.status]}</Badge>
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
                {actor === "operator" ? (
                  <td className="py-1.5">
                    {isActive(run.status) ? null : (
                      <Button
                        variant="danger"
                        className="px-2 py-1 text-xs"
                        onClick={() => setPendingDelete(run)}
                      >
                        Delete run
                      </Button>
                    )}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {pendingDelete ? (
        <DeleteRunDialog
          runId={pendingDelete.run_id}
          open
          onOpenChange={(open) => {
            if (!open) setPendingDelete(null);
          }}
          onDeleted={() => {
            setCompare((current) => current.filter((id) => id !== pendingDelete.run_id));
            setPendingDelete(null);
          }}
        />
      ) : null}
      {loaded && runs.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            variant="secondary"
            disabled={cursorStack.length === 0 || page.isFetching}
            onClick={() => {
              setCursor(cursorStack[cursorStack.length - 1] ?? null);
              setCursorStack((stack) => stack.slice(0, -1));
            }}
          >
            Newer
          </Button>
          {page.isFetching && page.isPlaceholderData ? (
            <span className="text-xs text-mt-muted">Loading more…</span>
          ) : null}
          <Button
            variant="secondary"
            disabled={!hasMore || !nextCursor || page.isFetching}
            onClick={() => {
              setCursorStack((stack) => [...stack, cursor]);
              setCursor(nextCursor);
            }}
          >
            Older
          </Button>
        </div>
      ) : null}
    </div>
  );
}
