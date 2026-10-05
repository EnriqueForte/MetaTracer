"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { TRIAGE_LABEL } from "@/components/run/findings/model";
import { triageVariant } from "@/components/run/findings/triage-form";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { truncate } from "@/lib/api/browser";
import { errorMessage, getJson, hasArray, isObject } from "@/lib/api/client";
import type { ComparedFindingResponse, RunComparisonResponse, RunListResponse } from "@/lib/api/types";
import { severityKey } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { formatWhen } from "@/lib/time";

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
  unclassified: "Unclassified",
};

const TYPE_LABEL: Record<string, string> = {
  gps: "GPS / Coordinates",
  email: "Email",
  internal_path: "Internal Path",
  software_version: "Software Version",
  debug_comment: "Debug Comment",
};

function readParams(): { a: string; b: string } {
  if (typeof window === "undefined") return { a: "", b: "" };
  const params = new URLSearchParams(window.location.search);
  return { a: params.get("a") ?? "", b: params.get("b") ?? "" };
}

function writeParams(a: string, b: string) {
  const params = new URLSearchParams(window.location.search);
  if (a) params.set("a", a);
  else params.delete("a");
  if (b) params.set("b", b);
  else params.delete("b");
  const search = params.toString();
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
}

function Section({
  title,
  items,
  empty,
}: {
  title: string;
  items: ComparedFindingResponse[];
  empty: string;
}) {
  return (
    <section className="mt-card flex min-w-0 flex-col gap-2 p-4" aria-label={title}>
      <h2 className="mt-section-title">
        {title} <span className="mt-meta inline">({items.length})</span>
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-mt-muted">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={`${item.run_id}-${item.finding_id}`} className="flex min-w-0 flex-col gap-1 border-t border-mt-border pt-2 first:border-t-0 first:pt-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={severityKey(item.severity)}>{SEVERITY_LABEL[severityKey(item.severity)]}</Badge>
                <span className="text-xs text-mt-muted">{TYPE_LABEL[item.finding_type] ?? item.finding_type}</span>
                {item.triage_status && item.triage_status !== "open" ? (
                  <Badge variant={triageVariant(item.triage_status)}>{TRIAGE_LABEL[item.triage_status]}</Badge>
                ) : null}
                <Link
                  href={`/runs/${encodeURIComponent(item.run_id)}?q=${encodeURIComponent(item.evidence_snippet.slice(0, 80))}`}
                  className="mt-tech underline"
                >
                  {truncate(item.evidence_snippet, 100)}
                </Link>
              </div>
              <p className="mt-tech text-mt-muted">{truncate(item.asset_url, 100)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function CompareView() {
  const [{ a, b }, setPair] = useState({ a: "", b: "" });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPair(readParams());
    setReady(true);
  }, []);

  const runs = useQuery({
    queryKey: [...queryKeys.runs, "completed-50"],
    queryFn: () => getJson<RunListResponse>("/api/runs?limit=50&status=completed", hasArray("runs")),
  });
  const comparison = useQuery({
    queryKey: queryKeys.compare(a, b),
    queryFn: () =>
      getJson<RunComparisonResponse>(
        `/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
        (value) => isObject(value) && Array.isArray(value.new),
      ),
    enabled: ready && Boolean(a && b) && a !== b,
  });

  function choose(side: "a" | "b", value: string) {
    const next = { a, b, [side]: value };
    setPair(next);
    writeParams(next.a, next.b);
  }

  const options = runs.data?.runs ?? [];
  const select = (side: "a" | "b", label: string, value: string) => (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={`compare-${side}`} className="text-xs font-semibold text-mt-muted">
        {label}
      </label>
      <select
        id={`compare-${side}`}
        value={value}
        onChange={(event) => choose(side, event.target.value)}
        className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
      >
        <option value="">Choose a completed run</option>
        {value && !options.some((run) => run.run_id === value) ? <option value={value}>{value}</option> : null}
        {options.map((run) => (
          <option key={run.run_id} value={run.run_id}>
            {run.target} — {formatWhen(run.started_at)} ({run.total_findings})
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div>
        <h1 className="mt-title">Compare runs</h1>
        <p className="text-sm text-mt-muted">
          Findings are matched by asset URL, type and evidence. The baseline is the earlier run; the
          other run is the one you are reviewing.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {select("a", "Baseline run", a)}
        {select("b", "Run to review", b)}
      </div>
      {!a || !b ? <EmptyState title="Choose two runs">Pick a baseline and a run to review.</EmptyState> : null}
      {a && b && a === b ? <EmptyState title="Same run twice">Choose two different runs.</EmptyState> : null}
      {comparison.isPending && comparison.fetchStatus === "fetching" ? <LoadingState label="Comparing runs" /> : null}
      {comparison.isError ? (
        <ErrorState message={errorMessage(comparison.error, "Could not compare these runs")} onRetry={() => void comparison.refetch()} />
      ) : null}
      {comparison.data ? (
        <div className="flex flex-col gap-3">
          <p className="mt-meta">
            {comparison.data.a.target} ({formatWhen(comparison.data.a.started_at)}) →{" "}
            {comparison.data.b.target} ({formatWhen(comparison.data.b.started_at)})
          </p>
          <Section title="New" items={comparison.data.new} empty="Nothing new in the reviewed run." />
          <Section title="Resolved" items={comparison.data.resolved} empty="Nothing from the baseline went away." />
          <Section title="Persistent" items={comparison.data.persistent} empty="No finding appears in both runs." />
        </div>
      ) : null}
    </div>
  );
}
