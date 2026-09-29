"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FindingsPanel } from "@/components/run/findings-panel";
import { apiFetch } from "@/lib/api/browser";
import { safeUrl } from "@/lib/security/safe-url";
import {
  STAGE_LABELS,
  STAGES,
  applyProgress,
  initialStages,
  parseProgressEvent,
  type StageState,
} from "@/lib/sse/progress";

type RunStatus = "pending" | "running" | "completed" | "failed" | "aborted";

type AssetIssue = {
  asset_id: string;
  source_url: string;
  status: "failed" | "skipped";
  skip_reason: string | null;
  error_message: string | null;
};

type RunSnapshot = {
  run_id: string;
  status: RunStatus;
  target: string;
  scope: string[];
  reasoning_depth: string;
  total_assets: number;
  total_findings: number;
  error_message: string | null;
  completed_at: string | null;
  asset_issues: AssetIssue[];
};

const EXPORTS = [
  ["md", "Download Markdown"],
  ["json", "Download JSON"],
  ["html", "Download HTML"],
  ["csv", "Download CSV"],
  ["bounty", "Download Bounty TXT"],
] as const;

function exportHref(runId: string, format: (typeof EXPORTS)[number][0]): string {
  return `/api/runs/${encodeURIComponent(runId)}/export?format=${format}`;
}

const STATUS_LABEL: Record<RunStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  aborted: "Aborted",
};

function isRunStatus(value: unknown): value is RunStatus {
  return (
    value === "pending" ||
    value === "running" ||
    value === "completed" ||
    value === "failed" ||
    value === "aborted"
  );
}

function parseRun(value: unknown): RunSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  if (!isRunStatus(row.status) || typeof row.target !== "string" || typeof row.run_id !== "string") {
    return null;
  }
  if (typeof row.total_assets !== "number" || typeof row.total_findings !== "number") return null;
  if (!Array.isArray(row.scope) || !row.scope.every((item) => typeof item === "string")) return null;
  const issues: AssetIssue[] = [];
  if (Array.isArray(row.asset_issues)) {
    for (const item of row.asset_issues) {
      if (!item || typeof item !== "object") continue;
      const issue = item as Record<string, unknown>;
      if (typeof issue.asset_id !== "string" || typeof issue.source_url !== "string") continue;
      if (issue.status !== "failed" && issue.status !== "skipped") continue;
      issues.push({
        asset_id: issue.asset_id,
        source_url: issue.source_url,
        status: issue.status,
        skip_reason: typeof issue.skip_reason === "string" ? issue.skip_reason : null,
        error_message: typeof issue.error_message === "string" ? issue.error_message : null,
      });
    }
  }
  return {
    run_id: row.run_id,
    status: row.status,
    target: row.target,
    scope: row.scope,
    reasoning_depth: typeof row.reasoning_depth === "string" ? row.reasoning_depth : "",
    total_assets: row.total_assets,
    total_findings: row.total_findings,
    error_message: typeof row.error_message === "string" ? row.error_message : null,
    completed_at: typeof row.completed_at === "string" ? row.completed_at : null,
    asset_issues: issues,
  };
}

function formatWhen(value: string): string {
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", "").replace("Z", "");
}

export function RunProgress({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [loadError, setLoadError] = useState("");
  const [stages, setStages] = useState<StageState[]>(initialStages);
  const [message, setMessage] = useState("Connecting to the live stream…");
  const [currentAsset, setCurrentAsset] = useState("");
  const [currentStep, setCurrentStep] = useState<number | null>(null);
  const [totalSteps, setTotalSteps] = useState<number | null>(null);
  const [contractError, setContractError] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    let stopped = false;

    let closedByUs = false;

    function stopPolling() {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }

    async function refresh(): Promise<RunSnapshot | "missing" | "error"> {
      try {
        const response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}`);
        if (stopped) return "error";
        if (response.status === 404) {
          setLoadError("Run not found");
          setRun(null);
          return "missing";
        }
        if (!response.ok) {
          setLoadError(`Could not load this run (HTTP ${response.status}).`);
          return "error";
        }
        const parsed = parseRun(await response.json());
        if (!parsed) {
          setLoadError("Could not load this run.");
          return "error";
        }
        setRun(parsed);
        setLoadError("");
        return parsed;
      } catch {
        if (!stopped) setLoadError("Network error: the API is unreachable.");
        return "error";
      }
    }

    function startPolling() {
      if (pollRef.current !== null) return;
      pollRef.current = window.setInterval(() => {
        void refresh().then((snapshot) => {
          if (snapshot === "missing") {
            stopPolling();
            return;
          }
          if (
            snapshot !== "error" &&
            (snapshot.status === "completed" ||
              snapshot.status === "failed" ||
              snapshot.status === "aborted")
          ) {
            stopPolling();
          }
        });
      }, 2000);
    }

    function closeStream() {
      closedByUs = true;
      sourceRef.current?.close();
      sourceRef.current = null;
    }

    void refresh();
    const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream`);
    sourceRef.current = source;
    source.onmessage = (event) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        setContractError(true);
        return;
      }
      const tick = parseProgressEvent(payload);
      if (!tick) {
        setContractError(true);
        return;
      }
      setMessage(tick.message);
      setCurrentAsset(tick.current_asset ?? "");
      setCurrentStep(tick.current_step);
      setTotalSteps(tick.total_steps);
      setStages((current) => applyProgress(current, tick));
      if (tick.stage === "completed" || tick.stage === "failed") {
        closeStream();
        void refresh();
      }
    };
    source.onerror = () => {
      if (closedByUs) return;
      closeStream();
      startPolling();
    };

    return () => {
      stopped = true;
      closeStream();
      stopPolling();
    };
  }, [runId]);

  if (loadError && !run) {
    return (
      <div role="alert" className="flex flex-col gap-2 rounded-md border border-mt-danger-border bg-mt-danger-bg p-4">
        <p className="text-base font-semibold text-mt-fg">{loadError}</p>
        <p className="text-sm text-mt-fg">
          This run id does not exist in the local database. It may belong to another MetaTracer
          installation or the database may have been reset.
        </p>
        <Link href="/" className="self-start text-sm font-semibold text-mt-accent-hover">
          Start a new scan
        </Link>
      </div>
    );
  }

  if (!run) {
    return (
      <p className="flex items-center gap-2 text-sm text-mt-muted" aria-live="polite">
        <span className="mt-spin" aria-hidden="true" />
        Loading run…
      </p>
    );
  }

  const live = run.status === "pending" || run.status === "running";

  const finished = run.status === "completed";

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-mt-border pb-3">
        <div className="min-w-0">
          <h1 className="mt-title">
            Scan of <span className="mt-tech">{run.target}</span>
          </h1>
          <p className="mt-tech">{run.run_id}</p>
          {run.completed_at ? (
            <p className="text-xs text-mt-muted">Completed at {formatWhen(run.completed_at)}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={run.status}>{STATUS_LABEL[run.status]}</Badge>
          {finished ? (
            <>
              {EXPORTS.map(([format, label]) => (
                <Button key={format} variant="secondary" className="px-2 py-1 text-xs" asChild>
                  <a href={exportHref(run.run_id, format)} download>
                    {label}
                  </a>
                </Button>
              ))}
              <Button variant="ghost" className="px-2 py-1 text-xs" asChild>
                <Link href="/runs">History</Link>
              </Button>
              <Button variant="secondary" className="px-2 py-1 text-xs" asChild>
                <Link href="/">New scan</Link>
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {finished ? (
        <p className="text-xs text-mt-muted">The report file is regenerated on the server.</p>
      ) : null}

      {run.status === "failed" ? (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-mt-danger-border bg-mt-danger-bg p-3">
          <p className="text-sm font-semibold text-mt-fg">Scan failed</p>
          <p className="mt-tech whitespace-pre-wrap">{run.error_message || "unknown error"}</p>
        </div>
      ) : null}

      {run.status === "aborted" ? (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-mt-warning-border bg-mt-warning-bg p-3">
          <p className="text-sm font-semibold text-mt-fg">Scan aborted</p>
          {run.error_message ? <p className="mt-tech whitespace-pre-wrap">{run.error_message}</p> : null}
        </div>
      ) : null}

      {live ? (
        <div className="flex flex-col gap-2">
          <ol className="mt-stages" aria-label="Progress">
            {STAGES.map((key, index) => {
              const state = stages[index];
              return (
                <li
                  key={key}
                  className="mt-stage"
                  data-state={state}
                  data-stage={key}
                  aria-current={state === "active" ? "step" : undefined}
                >
                  <span className="mt-stage-line" aria-hidden="true" />
                  <span className="mt-stage-node">
                    <span className="mt-stage-dot" aria-hidden="true" />
                    <span>
                      {state === "active" ? <span className="mt-spin" aria-hidden="true" /> : null}
                      {STAGE_LABELS[key]}
                      {key === "ai_analysis" && state === "active" ? (
                        <span className="mt-meta block font-normal">Classifying extracted evidence</span>
                      ) : null}
                    </span>
                  </span>
                  {state === "failed" ? (
                    <span aria-hidden="true" className="text-mt-danger">
                      Failed
                    </span>
                  ) : null}
                  <span className="sr-only">{state}</span>
                </li>
              );
            })}
          </ol>
          <p className="mt-tech whitespace-pre-wrap">{message}</p>
          {currentAsset ? <p className="mt-tech break-all">{currentAsset}</p> : null}
          {totalSteps !== null && currentStep !== null ? (
            <p className="text-xs text-mt-muted">
              Step {currentStep} / {totalSteps}
            </p>
          ) : null}
          {contractError ? (
            <p className="text-xs text-mt-muted">A progress event could not be read.</p>
          ) : null}
        </div>
      ) : null}

      {finished ? <FindingsPanel runId={run.run_id} totalAssets={run.total_assets} /> : null}

      {run.asset_issues.length > 0 ? (
        <details className="rounded-md border border-mt-warning-border bg-mt-warning-bg p-3">
          <summary className="cursor-pointer text-sm text-mt-fg">
            Asset issues ({run.asset_issues.length}) — failed or skipped documents that did not abort
            the run
          </summary>
          <ul className="mt-3 flex flex-col gap-2">
            {run.asset_issues.map((issue) => {
              const href = safeUrl(issue.source_url);
              return (
                <li key={issue.asset_id} className="mt-tech">
                  <Badge variant={issue.status === "failed" ? "failed" : "pending"}>
                    {issue.skip_reason || issue.status}
                  </Badge>{" "}
                  {href ? (
                    <a href={href} className="underline">
                      {issue.source_url}
                    </a>
                  ) : (
                    issue.source_url
                  )}
                  {issue.error_message ? ` — ${issue.error_message}` : ""}
                </li>
              );
            })}
          </ul>
        </details>
      ) : null}

    </div>
  );
}
