"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorMessage, sendJson } from "@/lib/api/client";
import type { FindingsResponse, TriageResponse, TriageStatus } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { formatWhen } from "@/lib/time";

import { TRIAGE_LABEL, TRIAGE_STATUSES, triageOf, type Finding } from "./model";

const triageSchema = z.object({
  status: z.enum(TRIAGE_STATUSES),
  note: z.string().trim().max(500, "Keep the note under 500 characters.").nullable(),
});

export function triageVariant(status: TriageStatus): "confidence" | "completed" | "aborted" | "pending" {
  if (status === "confirmed") return "aborted";
  if (status === "fixed") return "completed";
  if (status === "false_positive") return "pending";
  return "confidence";
}

/** Read-only for viewers; operators get the selector. Severity is never sent. */
export function TriageForm({ runId, finding, canMutate }: { runId: string; finding: Finding; canMutate: boolean }) {
  const queryClient = useQueryClient();
  const current = triageOf(finding);
  const [status, setStatus] = useState<TriageStatus>(current);
  const [note, setNote] = useState(finding.triage_note ?? "");
  const [formError, setFormError] = useState("");

  const save = useMutation({
    mutationFn: (body: z.infer<typeof triageSchema>) =>
      sendJson<TriageResponse>(
        `/api/runs/${encodeURIComponent(runId)}/findings/${encodeURIComponent(finding.id)}/triage`,
        "PUT",
        body,
      ),
    onSuccess: (row) => {
      if (!row) return;
      queryClient.setQueryData<FindingsResponse>(queryKeys.findings(runId), (data) =>
        data
          ? {
              ...data,
              findings: data.findings.map((item) =>
                item.id === row.finding_id
                  ? {
                      ...item,
                      triage_status: row.triage_status,
                      triage_note: row.triage_note,
                      triaged_by: row.triaged_by,
                      triaged_at: row.triaged_at,
                    }
                  : item,
              ),
            }
          : data,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
    },
  });

  function submit() {
    setFormError("");
    const parsed = triageSchema.safeParse({ status, note: note.trim() || null });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check the triage form.");
      return;
    }
    save.mutate(parsed.data);
  }

  return (
    <section className="flex flex-col gap-2 rounded-md border border-mt-border p-3" aria-label="Triage">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-mt-fg">Triage</h3>
        <Badge variant={triageVariant(current)}>{TRIAGE_LABEL[current]}</Badge>
        {finding.triaged_at ? (
          <span className="mt-meta">
            by {finding.triaged_by ?? "unknown"} · {formatWhen(finding.triaged_at)} UTC
          </span>
        ) : null}
      </div>
      {finding.triage_note ? <p className="text-sm text-mt-fg">{finding.triage_note}</p> : null}
      <p className="text-xs text-mt-muted">
        Triage never changes severity or evidence. False positives are left out of exports and
        dashboard counts by default.
      </p>
      {canMutate ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="triage-status" className="text-xs font-semibold text-mt-muted">
              Status
            </label>
            <select
              id="triage-status"
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
            <Button variant="secondary" disabled={save.isPending} onClick={submit}>
              Save triage
            </Button>
            {save.isSuccess ? <span role="status" className="text-xs text-mt-muted">Saved.</span> : null}
          </div>
          <label htmlFor="triage-note" className="text-xs font-semibold text-mt-muted">
            Note (optional)
          </label>
          <input
            id="triage-note"
            type="text"
            maxLength={500}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why — e.g. vendor address, already rotated"
            className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint"
          />
          {formError || save.isError ? (
            <p role="alert" className="text-xs text-mt-danger">
              {formError || errorMessage(save.error, "Triage could not be saved")}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
