"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AssetIssues } from "@/components/run/asset-issues";
import { ExportLinks } from "@/components/run/export-links";
import { findingsKey, FindingsPanel } from "@/components/run/findings-panel";
import { AbortRunButton, DeleteRunDialog } from "@/components/run/run-actions";
import { fetchRun, isLive, RUN_STATUS_LABEL, runKey, TERMINAL } from "@/components/run/run-model";
import { CorrelationPanel } from "@/components/run/workspace/correlation-panel";
import { RunSectionNav } from "@/components/run/workspace/run-header";
import { LiveActivity } from "@/components/run/live-activity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";
import {
  applyProgress,
  initialStages,
  parseProgressEvent,
  STAGE_LABELS,
  STAGES,
  type StageState,
} from "@/lib/sse/progress";
import { formatWhen } from "@/lib/time";

function stageLabel(stages: StageState[]): string | null {
  const index = stages.findIndex((state) => state === "active");
  if (index < 0) return null;
  const key = STAGES[index];
  return key ? STAGE_LABELS[key] : null;
}

export function RunProgress({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const actor = useActor();
  const runQuery = useQuery({
    queryKey: runKey(runId),
    queryFn: () => fetchRun(runId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.has(status) ? false : 2000;
    },
  });
  const run = runQuery.data ?? null;
  const [stages, setStages] = useState<StageState[]>(initialStages);
  const [message, setMessage] = useState("");
  const [currentAsset, setCurrentAsset] = useState("");
  const [step, setStep] = useState<{ current: number; total: number }>({
    current: 0,
    total: STAGES.length,
  });
  const [contractError, setContractError] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let closedByUs = false;
    function closeStream() {
      closedByUs = true;
      sourceRef.current?.close();
      sourceRef.current = null;
    }
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
      setStep({ current: tick.current_step, total: tick.total_steps });
      setStages((current) => applyProgress(current, tick));
      if (tick.stage === "completed" || tick.stage === "failed" || tick.stage === "aborted") {
        closeStream();
        void queryClient.invalidateQueries({ queryKey: runKey(runId) });
        void queryClient.invalidateQueries({ queryKey: findingsKey(runId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.notifications });
      }
    };
    source.onerror = () => {
      if (closedByUs) return;
      closeStream();
    };
    return () => closeStream();
  }, [queryClient, runId]);

  if (deleted) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-mt-fg">This run was deleted.</p>
        <Link href="/runs" className="self-start text-sm font-semibold text-mt-accent-hover">
          Back to history
        </Link>
      </div>
    );
  }

  if (runQuery.isError && !run) {
    const missing = runQuery.error instanceof ApiError && runQuery.error.status === 404;
    const loadError = missing
      ? "Run not found"
      : runQuery.error instanceof ApiError
        ? runQuery.error.status === 200
          ? "Could not load this run."
          : `Could not load this run (HTTP ${runQuery.error.status}).`
        : "Network error: the API is unreachable.";
    return (
      <div role="alert" className="flex flex-col gap-2 rounded-md border border-mt-danger-border bg-mt-danger-bg p-4">
        <p className="text-base font-semibold text-mt-fg">{loadError}</p>
        {missing ? (
          <p className="text-sm text-mt-fg">
            This run id does not exist in the local database. It may belong to another MetaTracer
            installation or the database may have been reset.
          </p>
        ) : null}
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

  const live = isLive(run.status);
  const finished = run.status === "completed";
  const canMutate = actor === "operator";

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
          <Badge variant={run.status}>{RUN_STATUS_LABEL[run.status]}</Badge>
          {live && canMutate ? <AbortRunButton runId={run.run_id} /> : null}
          {!live && canMutate ? (
            <Button variant="danger" onClick={() => setConfirmDelete(true)}>
              Delete run
            </Button>
          ) : null}
        </div>
      </div>
      <RunSectionNav runId={run.run_id} active="" />
      {finished ? (
        <>
          <ExportLinks runId={run.run_id} />
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" className="px-2 py-1 text-xs" asChild>
              <Link href={`/runs/compare?b=${encodeURIComponent(run.run_id)}`}>Compare</Link>
            </Button>
            <Button variant="ghost" className="px-2 py-1 text-xs" asChild>
              <Link href="/runs">History</Link>
            </Button>
            <Button variant="secondary" className="px-2 py-1 text-xs" asChild>
              <Link href="/">New scan</Link>
            </Button>
          </div>
        </>
      ) : null}
      <DeleteRunDialog
        runId={run.run_id}
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        onDeleted={() => setDeleted(true)}
      />

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
        <LiveActivity
          startedAt={run.started_at}
          totalAssets={run.total_assets}
          totalFindings={run.total_findings}
          issueCount={run.asset_issues.length}
          stageLabel={stageLabel(stages)}
          message={message}
          currentAsset={currentAsset}
          contractError={contractError}
          currentStep={step.current}
          totalSteps={step.total}
        />
      ) : null}

      {finished ? <CorrelationPanel runId={run.run_id} /> : null}

      {finished ? <FindingsPanel runId={run.run_id} totalAssets={run.total_assets} /> : null}

      <AssetIssues issues={run.asset_issues} />
    </div>
  );
}
