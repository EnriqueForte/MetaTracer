"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/browser";
import { sendJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Severity } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

import { SEVERITY_ASCENDING, SEVERITY_LABEL, type Finding } from "./model";

type FeedbackRow = { vote: "up" | "down"; severity_after: Severity };

const feedbackSchema = z.object({
  vote: z.enum(["up", "down"]),
  severity_after: z.enum(SEVERITY_ASCENDING),
  reason: z.string().trim().max(500, "El motivo no puede superar los 500 caracteres.").nullable(),
});

const feedbackKey = queryKeys.feedback;

async function fetchFeedback(findingId: string): Promise<FeedbackRow | null> {
  const response = await apiFetch(`/api/feedback/${encodeURIComponent(findingId)}`);
  if (response.status !== 200) return null;
  const row: unknown = await response.json();
  const parsed = z
    .object({ vote: z.enum(["up", "down"]), severity_after: z.enum(SEVERITY_ASCENDING) })
    .safeParse(row);
  return parsed.success ? parsed.data : null;
}

export function FeedbackForm({ finding }: { finding: Finding }) {
  const queryClient = useQueryClient();
  const key = feedbackKey(finding.id);
  const current = useQuery({ queryKey: key, queryFn: () => fetchFeedback(finding.id) });
  const [severity, setSeverity] = useState<Severity>(finding.severity ?? "info");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState("");

  const save = useMutation({
    mutationFn: (body: z.infer<typeof feedbackSchema>) =>
      sendJson<FeedbackRow>(`/api/feedback/${encodeURIComponent(finding.id)}`, "PUT", body),
    onSuccess: (row) => {
      if (row) queryClient.setQueryData(key, { vote: row.vote, severity_after: row.severity_after });
    },
  });
  const remove = useMutation({
    mutationFn: () => sendJson(`/api/feedback/${encodeURIComponent(finding.id)}`, "DELETE"),
    onSuccess: () => queryClient.setQueryData(key, null),
  });

  function submit() {
    setFormError("");
    if (severity === finding.severity) {
      setFormError("Elige una severidad distinta para guardar la corrección.");
      return;
    }
    const before = finding.severity ? SEVERITY_ASCENDING.indexOf(finding.severity) : -1;
    const parsed = feedbackSchema.safeParse({
      vote: SEVERITY_ASCENDING.indexOf(severity) > before ? "up" : "down",
      severity_after: severity,
      reason: reason.trim() || null,
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "La corrección no es válida.");
      return;
    }
    save.mutate(parsed.data);
  }

  const busy = save.isPending || remove.isPending;
  const mutationError = save.error ?? remove.error;
  const errorText =
    formError ||
    (mutationError
      ? mutationError instanceof ApiError && mutationError.detail
        ? mutationError.detail
        : save.error
          ? "No se pudo guardar la corrección"
          : "No se pudo quitar la corrección"
      : "");
  const stored = current.data ?? null;

  return (
    <div className="flex flex-col gap-2 border-t border-mt-border pt-4">
      <h3 className="text-sm font-semibold text-mt-fg">Corrección</h3>
      <p className="text-xs text-mt-muted">
        Corrige la severidad si el modelo se equivocó. Tu corrección se guarda en local y orienta
        escaneos futuros con hallazgos similares.
      </p>
      {stored ? (
        <p className="text-xs text-mt-muted">
          Corrección actual: {stored.vote} → {SEVERITY_LABEL[stored.severity_after]}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="feedback-severity" className="text-xs font-semibold text-mt-muted">
          Severidad corregida
        </label>
        <select
          id="feedback-severity"
          value={severity}
          onChange={(event) => {
            const next = SEVERITY_ASCENDING.find((item) => item === event.target.value);
            if (next) setSeverity(next);
          }}
          className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
        >
          {SEVERITY_ASCENDING.map((item) => (
            <option key={item} value={item}>
              {SEVERITY_LABEL[item]}
            </option>
          ))}
        </select>
        <Button variant="secondary" disabled={busy} onClick={submit}>
          {stored ? "Actualizar corrección" : "Guardar corrección"}
        </Button>
        {stored ? (
          <Button variant="danger" disabled={busy} onClick={() => remove.mutate()}>
            Quitar
          </Button>
        ) : null}
        {busy ? <span className="text-xs text-mt-muted">Guardando…</span> : null}
        {errorText ? (
          <span role="alert" className="text-xs text-mt-danger">
            {errorText}
          </span>
        ) : null}
      </div>
      <label htmlFor="feedback-reason" className="text-xs font-semibold text-mt-muted">
        Motivo (opcional)
      </label>
      <input
        id="feedback-reason"
        type="text"
        value={reason}
        maxLength={500}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Opcional: motivo (se guarda en local, nunca se envía al modelo)"
        className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint"
      />
    </div>
  );
}
