"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AssetIssues } from "@/components/run/asset-issues";
import { findingsKey } from "@/components/run/findings-panel";
import { LiveScanGraph } from "@/components/run/graph/live-scan-graph";
import { LiveActivity } from "@/components/run/live-activity";
import { isLive, runKey } from "@/components/run/run-model";
import { CorrelationPanel } from "@/components/run/workspace/correlation-panel";
import { useWorkspace } from "@/components/run/workspace/workspace-context";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";
import {
  applyProgress,
  initialStages,
  parseProgressEvent,
  STAGE_LABELS,
  STAGES,
  type StageState,
} from "@/lib/sse/progress";

function stageLabel(stages: StageState[]): string | null {
  const index = stages.findIndex((state) => state === "active");
  if (index < 0) return null;
  const key = STAGES[index];
  return key ? STAGE_LABELS[key] : null;
}

export function RunProgress({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const { run, deleted, isPending, error } = useWorkspace();
  const [stages, setStages] = useState<StageState[]>(initialStages);
  const [message, setMessage] = useState("");
  const [currentAsset, setCurrentAsset] = useState("");
  const [step, setStep] = useState<{ current: number; total: number }>({
    current: 0,
    total: STAGES.length,
  });
  const [contractError, setContractError] = useState(false);
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
        void queryClient.invalidateQueries({ queryKey: queryKeys.graph(runId) });
      }
    };
    source.onerror = () => {
      if (closedByUs) return;
      closeStream();
    };
    return () => closeStream();
  }, [queryClient, runId]);

  if (deleted) return null;

  if (error && !run) {
    const missing = error instanceof ApiError && error.status === 404;
    const loadError = missing
      ? "Escaneo no encontrado"
      : error instanceof ApiError
        ? error.status === 200
          ? "No se pudo cargar este escaneo."
          : `No se pudo cargar este escaneo (HTTP ${error.status}).`
        : "Error de red: la API no está accesible.";
    return (
      <div role="alert" className="flex flex-col gap-2 rounded-md border border-mt-danger-border bg-mt-danger-bg p-4">
        <p className="text-base font-semibold text-mt-fg">{loadError}</p>
        {missing ? (
          <p className="text-sm text-mt-fg">
            Este id de escaneo no existe en la base local. Puede pertenecer a otra instalación de
            MetaTracer o la base puede haberse restablecido.
          </p>
        ) : null}
        <Link href="/" className="self-start text-sm font-semibold text-mt-accent-hover">
          Iniciar un nuevo escaneo
        </Link>
      </div>
    );
  }

  if (isPending || !run) {
    return (
      <p className="flex items-center gap-2 text-sm text-mt-muted" aria-live="polite">
        <span className="mt-spin" aria-hidden="true" />
        Cargando escaneo…
      </p>
    );
  }

  const live = isLive(run.status);
  const finished = run.status === "completed";

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {run.status === "failed" ? (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-mt-danger-border bg-mt-danger-bg p-3">
          <p className="text-sm font-semibold text-mt-fg">Escaneo fallido</p>
          <p className="mt-tech whitespace-pre-wrap">{run.error_message || "error desconocido"}</p>
        </div>
      ) : null}

      {run.status === "aborted" ? (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-mt-warning-border bg-mt-warning-bg p-3">
          <p className="text-sm font-semibold text-mt-fg">Escaneo abortado</p>
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

      <LiveScanGraph runId={run.run_id} />

      {finished ? <CorrelationPanel runId={run.run_id} /> : null}

      {finished ? (
        <p className="text-sm text-mt-muted">
          Los hallazgos están en la pestaña Hallazgos.{" "}
          <Link href={`/runs/${encodeURIComponent(run.run_id)}/findings`} className="underline">
            Ver hallazgos
          </Link>
        </p>
      ) : null}

      <AssetIssues issues={run.asset_issues} />
    </div>
  );
}
