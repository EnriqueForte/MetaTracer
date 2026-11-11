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

  if (list.isPending) return <LoadingState label="Cargando investigaciones" />;
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
      <div>
        <h1 className="mt-title">Investigaciones</h1>
        <p className="mt-2 max-w-2xl text-sm text-mt-muted">
          Grupos de escaneos en esta instalación. Un valor compartido no es una identidad compartida.
          El triaje de otro escaneo se sugiere en el hallazgo, nunca se aplica solo.
        </p>
      </div>

      {canMutate ? (
        <form
          className="mt-card flex flex-wrap items-end gap-2 p-4"
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
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs font-semibold text-mt-muted">
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
          {formError ? (
            <p className="w-full text-sm text-mt-danger" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="Aún no hay investigaciones">
          {canMutate
            ? "Nombra un grupo y luego adjunta escaneos desde un espacio de trabajo."
            : "Cuando un operador agrupe escaneos, aparecerán aquí."}
        </EmptyState>
      ) : (
        <div className="mt-card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-mt-border text-xs text-mt-muted">
                <th className="px-3 py-1 font-semibold">Nombre</th>
                <th className="px-3 py-1 font-semibold">Estado</th>
                <th className="px-3 py-1 font-semibold">Escaneos</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-mt-border last:border-0">
                  <td className="px-3 py-2">
                    <Link
                      href={`/investigations/${encodeURIComponent(row.id)}`}
                      className="text-mt-fg underline-offset-2 hover:underline"
                    >
                      {row.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={row.status === "open" ? "running" : "aborted"}>
                      {row.status === "open" ? "Abierta" : "Cerrada"}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 mt-tech">{row.run_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
