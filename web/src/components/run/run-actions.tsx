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
    if (error.status === 403) return "Operator role required.";
    if (error.status === 409) return action === "abort" ? "This scan already finished." : "This scan is still running.";
    return action === "abort"
      ? `Could not abort this scan (HTTP ${error.status}).`
      : `Could not delete this run (HTTP ${error.status}).`;
  }
  return "Network error: the API is unreachable.";
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
        Abort scan
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>Abort this scan?</DialogTitle>
          <DialogDescription>
            The run stops and is marked aborted. Partial reports are not written.
          </DialogDescription>
          {abort.isError ? (
            <p role="alert" className="mt-3 text-sm text-mt-danger">
              {failure(abort.error, "abort")}
            </p>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)} disabled={abort.isPending}>
              Keep scanning
            </Button>
            <Button variant="danger" onClick={() => abort.mutate()} disabled={abort.isPending}>
              Abort this scan
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
        <DialogTitle>Delete this run?</DialogTitle>
        <DialogDescription>
          Findings, assets and exported reports for this run are removed. This cannot be undone.
        </DialogDescription>
        {remove.isError ? (
          <p role="alert" className="mt-3 text-sm text-mt-danger">
            {failure(remove.error, "delete")}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={remove.isPending}>
            Keep run
          </Button>
          <Button variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
            Delete this run
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
