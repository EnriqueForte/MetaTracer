"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AbortRunButton, DeleteRunDialog } from "@/components/run/run-actions";
import { isLive, RUN_STATUS_LABEL } from "@/components/run/run-model";
import { ExportLinks } from "@/components/run/export-links";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useActor } from "@/lib/session";
import { formatWhen } from "@/lib/time";

import { InvestigationMembership } from "./investigation-membership";
import { useWorkspace } from "./workspace-context";

export const RUN_TABS = [
  { segment: "", label: "Resumen", hint: "Progreso y hallazgos de este escaneo" },
  { segment: "assets", label: "Activos", hint: "Ficheros que este escaneo llegó a descargar" },
  { segment: "metadata", label: "Metadatos", hint: "Valores originales, con lectura normalizada cuando existe" },
  { segment: "findings", label: "Hallazgos", hint: "Evidencia, severidad y triaje" },
  { segment: "coverage", label: "Cobertura", hint: "Lo que el rastreo no descargó" },
] as const;

export function RunSectionNav({ runId, active }: { runId: string; active: string }) {
  return (
    <nav aria-label="Secciones del escaneo" className="mt-tabs">
      {RUN_TABS.map((tab) => {
        const href = tab.segment ? `/runs/${runId}/${tab.segment}` : `/runs/${runId}`;
        const isActive = active === tab.segment;
        return (
          <Link
            key={tab.segment || "overview"}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className="mt-tab"
          >
            <span className="text-sm font-semibold text-mt-fg">{tab.label}</span>
            <span className="text-xs text-mt-muted">{tab.hint}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function currentTab(pathname: string, runId: string): string {
  const base = `/runs/${runId}`;
  const rest = pathname.slice(base.length).replace(/^\//, "");
  return rest.split("/")[0] ?? "";
}

/**
 * Run header: status, counters, actions and the workspace tab strip.
 *
 * The run itself comes from the shared workspace context (one `fetchRun`
 * query), so switching tabs never refetches it.
 */
export function RunHeader() {
  const { runId, run, setDeleted } = useWorkspace();
  const actor = useActor();
  const pathname = usePathname();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const active = currentTab(pathname, runId);
  const canMutate = actor === "operator";

  if (!run) return <p className="text-sm text-mt-muted">Cargando escaneo…</p>;

  const live = isLive(run.status);
  const finished = run.status === "completed";

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="mt-page-head">
        <div className="min-w-0">
          <h1 className="mt-title">
            Escaneo de <span className="mt-tech">{run.target}</span>
          </h1>
          <p className="mt-tech text-xs text-mt-muted">{run.run_id}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-mt-muted">
            <Badge variant={run.status}>{RUN_STATUS_LABEL[run.status]}</Badge>
            <span>{run.total_assets} activo(s)</span>
            <span aria-hidden="true">·</span>
            <span>{run.total_findings} hallazgo(s)</span>
            {run.completed_at ? (
              <>
                <span aria-hidden="true">·</span>
                <span>Completado {formatWhen(run.completed_at)}</span>
              </>
            ) : null}
          </div>
          <InvestigationMembership run={run} canMutate={canMutate} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {live && canMutate ? <AbortRunButton runId={run.run_id} /> : null}
          {!live && canMutate ? (
            <Button variant="danger" onClick={() => setConfirmDelete(true)}>
              Eliminar escaneo
            </Button>
          ) : null}
        </div>
      </div>

      <RunSectionNav runId={runId} active={active} />
      {finished ? <ExportLinks runId={run.run_id} /> : null}

      <DeleteRunDialog
        runId={run.run_id}
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        onDeleted={() => setDeleted(true)}
      />
    </div>
  );
}
