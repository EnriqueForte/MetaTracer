"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { errorMessage, getJson, hasArray, sendJson } from "@/lib/api/client";
import type { InvestigationListResponse, InvestigationResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";

const createSchema = z.object({
  name: z.string().trim().min(1, "Pon primero un nombre a la investigación.").max(80, "Los nombres tienen como máximo 80 caracteres."),
  description: z.string().trim().max(2000, "Las descripciones tienen como máximo 2000 caracteres.").optional(),
});

export function InvestigationsView() {
  const queryClient = useQueryClient();
  const actor = useActor();
  const canMutate = actor === "operator";
  const [name, setName] = useState("");
  const [formError, setFormError] = useState("");

  const list = useQuery({
    queryKey: queryKeys.investigations,
    queryFn: () =>
      getJson<InvestigationListResponse>("/api/investigations", hasArray("investigations")),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      sendJson<InvestigationResponse>("/api/investigations", "POST", body),
    onSuccess: () => {
      setName("");
      setFormError("");
      void queryClient.invalidateQueries({ queryKey: queryKeys.investigations });
    },
    onError: (error) => setFormError(errorMessage(error, "No se pudo crear la investigación.")),
  });

  if (list.isPending) return <LoadingState label="Cargando investigaciones" variant="list" />;
  if (list.isError) {
    return (
      <ErrorState
        message={errorMessage(list.error, "No se pudieron cargar las investigaciones.")}
        onRetry={() => void list.refetch()}
      />
    );
  }

  const rows = list.data?.investigations ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="mt-page-head">
        <div>
          <h1 className="mt-page-title">Investigaciones</h1>
          <p className="mt-meta">
            Grupos de escaneos en esta instalación. Un valor compartido no es una identidad compartida.
            El triaje de otro escaneo se sugiere en el hallazgo, nunca se aplica solo.
          </p>
        </div>
        {canMutate ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const parsed = createSchema.safeParse({ name });
              if (!parsed.success) {
                setFormError(parsed.error.issues[0]?.message ?? "Pon primero un nombre a la investigación.");
                return;
              }
              create.mutate(parsed.data);
            }}
          >
            <label className="flex min-w-48 flex-col gap-1 text-xs font-semibold text-mt-muted">
              Nueva investigación
              <Input
                value={name}
                maxLength={80}
                onChange={(event) => setName(event.target.value)}
                placeholder="Nombre del encargo"
              />
            </label>
            <Button type="submit" disabled={create.isPending}>
              Crear
            </Button>
          </form>
        ) : null}
      </div>
      {formError ? (
        <p className="text-sm text-mt-danger" role="alert">
          {formError}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="Aún no hay investigaciones">
          {canMutate
            ? "Nombra un grupo y luego adjunta escaneos desde un espacio de trabajo."
            : "Cuando un operador agrupe escaneos, aparecerán aquí."}
        </EmptyState>
      ) : (
        <div className="mt-card overflow-x-auto">
          <table className="mt-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Estado</th>
                <th>Escaneos</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="mt-row">
                  <td>
                    <Link
                      href={`/investigations/${encodeURIComponent(row.id)}`}
                      className="text-mt-fg underline-offset-2 hover:underline"
                    >
                      {row.name}
                    </Link>
                  </td>
                  <td>
                    <Badge variant={row.status === "open" ? "running" : "completed"}>
                      {row.status === "open" ? "Abierta" : "Cerrada"}
                    </Badge>
                  </td>
                  <td className="mt-tech">{row.run_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
