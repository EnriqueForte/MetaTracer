"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { runKey, type RunSnapshot } from "@/components/run/run-model";
import { Button } from "@/components/ui/button";
import { errorMessage, getJson, sendJson } from "@/lib/api/client";

type InvestigationRow = {
  id: string;
  name: string;
  status: string;
  run_count: number;
};

type InvestigationList = {
  total: number;
  investigations: InvestigationRow[];
};

/**
 * Group this run with others. A group suggests triage; it does not apply it
 * and it does not hide the run from the rest of the install.
 */
export function InvestigationMembership({
  run,
  canMutate,
}: {
  run: RunSnapshot;
  canMutate: boolean;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [picked, setPicked] = useState("");
  const [formError, setFormError] = useState("");
  const list = useQuery({
    queryKey: ["investigations"],
    queryFn: () => getJson<InvestigationList>("/api/investigations", isInvestigationList),
    enabled: canMutate && !run.investigation_id,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: runKey(run.run_id) });
    await queryClient.invalidateQueries({ queryKey: ["investigations"] });
  };

  const start = useMutation({
    mutationFn: async (label: string) => {
      const created = await sendJson<InvestigationRow>("/api/investigations", "POST", {
        name: label,
      });
      if (!created?.id) throw new Error("The investigation was not created.");
      await sendJson(`/api/investigations/${encodeURIComponent(created.id)}/runs`, "POST", {
        run_id: run.run_id,
      });
    },
    onSuccess: () => {
      setFormError("");
      setName("");
      void refresh();
    },
    onError: (error) => setFormError(errorMessage(error, "Could not update the investigation.")),
  });

  const join = useMutation({
    mutationFn: (investigationId: string) =>
      sendJson(`/api/investigations/${encodeURIComponent(investigationId)}/runs`, "POST", {
        run_id: run.run_id,
      }),
    onSuccess: () => {
      setFormError("");
      void refresh();
    },
    onError: (error) => setFormError(errorMessage(error, "Could not update the investigation.")),
  });

  const leave = useMutation({
    mutationFn: () =>
      sendJson(
        `/api/investigations/${encodeURIComponent(run.investigation_id ?? "")}/runs/${encodeURIComponent(run.run_id)}`,
        "DELETE",
      ),
    onSuccess: () => {
      setFormError("");
      void refresh();
    },
    onError: (error) => setFormError(errorMessage(error, "Could not update the investigation.")),
  });

    if (run.investigation_id) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-mt-muted">
        <p>
          Investigation{" "}
          <span className="text-mt-fg">{run.investigation_name ?? run.investigation_id}</span>.
          Triage from other runs in this group is suggested, not applied.
        </p>
        {canMutate ? (
          <Button variant="secondary" disabled={leave.isPending} onClick={() => leave.mutate()}>
            Remove from investigation
          </Button>
        ) : null}
        {formError ? <span className="text-mt-danger">{formError}</span> : null}
      </div>
    );
  }

  if (!canMutate) return null;

  const openGroups = (list.data?.investigations ?? []).filter((row) => row.status === "open");

  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const label = name.trim();
        if (!label) {
          setFormError("Name the investigation first.");
          return;
        }
        start.mutate(label);
      }}
    >
      <label htmlFor="investigation-name" className="text-xs font-semibold text-mt-muted">
        Investigation
      </label>
      <input
        id="investigation-name"
        value={name}
        maxLength={80}
        onChange={(event) => setName(event.target.value)}
        placeholder="Name a new group"
        className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
      />
      <Button type="submit" variant="secondary" disabled={start.isPending}>
        Start investigation
      </Button>
      {openGroups.length > 0 ? (
        <>
          <select
            aria-label="Existing investigation"
            value={picked}
            onChange={(event) => setPicked(event.target.value)}
            className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
          >
            <option value="">Add to an existing group</option>
            {openGroups.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="secondary"
            disabled={!picked || join.isPending}
            onClick={() => join.mutate(picked)}
          >
            Add this run
          </Button>
        </>
      ) : null}
      {formError ? <span className="text-xs text-mt-danger">{formError}</span> : null}
    </form>
  );
}

function isInvestigationList(value: unknown): value is InvestigationList {
  if (!value || typeof value !== "object") return false;
  const row = value as { investigations?: unknown };
  return Array.isArray(row.investigations);
}
