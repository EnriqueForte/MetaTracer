"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { sendJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";

import { asRunSnapshot, runKey } from "./run-model";

function failure(error: unknown, action: "abort" | "delete"): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Se requiere el rol de operador.";
    if (error.status === 409) return action === "abort" ? "Este escaneo ya terminó." : "Este escaneo sigue en curso.";
    return action === "abort"
      ? `No se pudo abortar este escaneo (HTTP ${error.status}).`
      : `No se pudo eliminar este escaneo (HTTP ${error.status}).`;
  }
  return "Error de red: la API no está accesible.";
}

export function AbortRunButton({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const abort = useMutation({
    mutationFn: () => sendJson(`/api/runs/${encodeURIComponent(runId)}/abort`, "POST"),
    onSuccess: (payload) => {
      const snapshot = asRunSnapshot(payload);
      if (snapshot) queryClient.setQueryData(runKey(runId), snapshot);
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications });
      setOpen(false);
    },
  });
  return (
    <>
      <Button variant="danger" onClick={() => { abort.reset(); setOpen(true); }}>
        Abortar escaneo
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>¿Abortar este escaneo?</DialogTitle>
          <DialogDescription>
            El escaneo se detiene y queda marcado como abortado. No se escriben informes parciales.
          </DialogDescription>
          {abort.isError ? (
            <p role="alert" className="mt-3 text-sm text-mt-danger">
              {failure(abort.error, "abort")}
            </p>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)} disabled={abort.isPending}>
              Seguir escaneando
            </Button>
            <Button variant="danger" onClick={() => abort.mutate()} disabled={abort.isPending}>
              Abortar este escaneo
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function DeleteRunDialog({
  runId,
  open,
  onOpenChange,
  onDeleted,
}: {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => sendJson(`/api/runs/${encodeURIComponent(runId)}`, "DELETE"),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: runKey(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
      onOpenChange(false);
      onDeleted();
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) remove.reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogTitle>¿Eliminar este escaneo?</DialogTitle>
        <DialogDescription>
          Se eliminan los hallazgos, activos e informes exportados de este escaneo. No se puede deshacer.
        </DialogDescription>
        {remove.isError ? (
          <p role="alert" className="mt-3 text-sm text-mt-danger">
            {failure(remove.error, "delete")}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={remove.isPending}>
            Conservar escaneo
          </Button>
          <Button variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
            Eliminar este escaneo
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
