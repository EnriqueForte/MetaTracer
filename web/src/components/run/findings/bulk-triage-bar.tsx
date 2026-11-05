"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { errorMessage, sendJson } from "@/lib/api/client";
import type { BulkTriageResponse, FindingsResponse, TriageStatus } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

import { TRIAGE_LABEL, TRIAGE_STATUSES } from "./model";

export const BULK_TRIAGE_LIMIT = 200;

type Props = {
  runId: string;
  selectedIds: string[];
  onClear: () => void;
};

export function BulkTriageBar({ runId, selectedIds, onClear }: Props) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<TriageStatus>("false_positive");
  const [confirm, setConfirm] = useState(false);
  const capped = selectedIds.slice(0, BULK_TRIAGE_LIMIT);

  const save = useMutation({
    mutationFn: () =>
      sendJson<BulkTriageResponse>(`/api/runs/${encodeURIComponent(runId)}/findings/triage`, "POST", {
        finding_ids: capped,
        status,
        note: null,
      }),
    onSuccess: (body) => {
      if (!body) return;
      queryClient.setQueryData<FindingsResponse>(queryKeys.findings(runId), (data) => {
        if (!data) return data;
        const byId = new Map(body.findings.map((row) => [row.finding_id, row]));
        return {
          ...data,
          findings: data.findings.map((item) => {
            const row = byId.get(item.id);
            return row
              ? {
                  ...item,
                  triage_status: row.triage_status,
                  triage_note: row.triage_note,
                  triaged_by: row.triaged_by,
                  triaged_at: row.triaged_at,
                }
              : item;
          }),
        };
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
      onClear();
      setConfirm(false);
    },
  });

  if (selectedIds.length === 0) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-md border border-mt-border bg-mt-panel px-3 py-2"
      role="region"
      aria-label="Bulk triage"
    >
      <p className="text-sm text-mt-fg">
        {capped.length} selected
        {selectedIds.length > BULK_TRIAGE_LIMIT ? ` (first ${BULK_TRIAGE_LIMIT})` : ""}
      </p>
      <label htmlFor="bulk-triage-status" className="text-xs font-semibold text-mt-muted">
        Status
      </label>
      <select
        id="bulk-triage-status"
        value={status}
        onChange={(event) => {
          const next = TRIAGE_STATUSES.find((item) => item === event.target.value);
          if (next) setStatus(next);
        }}
        className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
      >
        {TRIAGE_STATUSES.map((item) => (
          <option key={item} value={item}>
            {TRIAGE_LABEL[item]}
          </option>
        ))}
      </select>
      <Button variant="secondary" onClick={() => setConfirm(true)} disabled={save.isPending}>
        Apply to selected
      </Button>
      <Button variant="ghost" onClick={onClear}>
        Clear selection
      </Button>
      {save.isError ? (
        <p role="alert" className="text-xs text-mt-danger">
          {errorMessage(save.error, "Bulk triage could not be saved")}
        </p>
      ) : null}
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle>Apply triage to {capped.length} findings?</DialogTitle>
          <DialogDescription>
            Status becomes {TRIAGE_LABEL[status]}. Severity and evidence are not changed.
          </DialogDescription>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              Confirm
            </Button>
            <Button variant="secondary" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
