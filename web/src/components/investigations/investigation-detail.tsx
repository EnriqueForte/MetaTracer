"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { RUN_STATUS_LABEL } from "@/components/run/run-model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { errorMessage, getJson, isObject, sendJson } from "@/lib/api/client";
import type { InvestigationResponse, RunStatus } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";
import { formatWhen } from "@/lib/time";

function isInvestigation(value: unknown): value is InvestigationResponse {
  return isObject(value) && typeof value.id === "string" && typeof value.name === "string";
}

export function InvestigationDetail({ investigationId }: { investigationId: string }) {
  const queryClient = useQueryClient();
  const actor = useActor();
  const canMutate = actor === "operator";

  const query = useQuery({
    queryKey: queryKeys.investigation(investigationId),
    queryFn: () =>
      getJson<InvestigationResponse>(
        `/api/investigations/${encodeURIComponent(investigationId)}`,
        isInvestigation,
      ),
  });

  const close = useMutation({
    mutationFn: (row: InvestigationResponse) =>
      sendJson(`/api/investigations/${encodeURIComponent(row.id)}`, "PUT", {
        name: row.name,
        description: row.description,
        status: "closed",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.investigation(investigationId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.investigations });
    },
  });

  if (query.isPending) return <LoadingState label="Cargando investigación" variant="list" />;
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error, "No se pudo cargar la investigación.")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const row = query.data;
  if (!row) return null;
  const runs = row.runs ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="mt-page-head">
        <div>
          <p className="mt-meta">
            <Link href="/investigations" className="underline-offset-2 hover:underline">
              Investigaciones
            </Link>
          </p>
          <h1 className="mt-page-title">{row.name}</h1>
          {row.description ? <p className="max-w-2xl text-sm text-mt-muted">{row.description}</p> : null}
          <p className="text-sm text-mt-muted">
            Los valores compartidos aparecen en cada escaneo. El triaje sugerido nunca se aplica
            solo y no cambia la severidad ni la evidencia.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={row.status === "open" ? "running" : "completed"}>
            {row.status === "open" ? "Abierta" : "Cerrada"}
          </Badge>
          {canMutate && row.status === "open" ? (
            <Button
              variant="secondary"
              disabled={close.isPending}
              onClick={() => close.mutate(row)}
            >
              Cerrar investigación
            </Button>
          ) : null}
        </div>
      </div>
      {close.isError ? (
        <p className="text-sm text-mt-danger" role="alert">
          {errorMessage(close.error, "No se pudo cerrar la investigación.")}
        </p>
      ) : null}

      {runs.length === 0 ? (
        <EmptyState title="No hay escaneos en este grupo">Adjunta un escaneo desde un espacio de trabajo.</EmptyState>
      ) : (
        <div className="mt-card overflow-x-auto">
          <table className="mt-table">
            <thead>
              <tr>
                <th>Escaneo</th>
                <th>Objetivo</th>
                <th>Estado</th>
                <th>Inicio</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="mt-row">
                  <td className="px-3 py-2">
                    <Link
                      href={`/runs/${encodeURIComponent(run.run_id)}`}
                      className="mt-tech text-mt-fg underline-offset-2 hover:underline"
                    >
                      {run.run_ref ?? run.run_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{run.target}</td>
                  <td className="px-3 py-2">
                    {RUN_STATUS_LABEL[run.status as RunStatus] ?? run.status}
                  </td>
                  <td className="px-3 py-2 mt-tech">{formatWhen(run.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
