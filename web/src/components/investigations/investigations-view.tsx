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
  name: z.string().trim().min(1, "Name the investigation first.").max(80, "Names are at most 80 characters."),
  description: z.string().trim().max(2000, "Descriptions are at most 2000 characters.").optional(),
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
    onError: (error) => setFormError(errorMessage(error, "Could not create the investigation.")),
  });

  if (list.isPending) return <LoadingState label="Loading investigations" />;
  if (list.isError) {
    return (
      <ErrorState
        message={errorMessage(list.error, "Could not load investigations.")}
        onRetry={() => void list.refetch()}
      />
    );
  }

  const rows = list.data?.investigations ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="mt-title">Investigations</h1>
        <p className="mt-2 max-w-2xl text-sm text-mt-muted">
          Groups of runs in this install. A shared value is not a shared identity. Triage from
          another run is suggested on the finding, never applied by itself.
        </p>
      </div>

      {canMutate ? (
        <form
          className="mt-card flex flex-wrap items-end gap-2 p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const parsed = createSchema.safeParse({ name });
            if (!parsed.success) {
              setFormError(parsed.error.issues[0]?.message ?? "Name the investigation first.");
              return;
            }
            create.mutate(parsed.data);
          }}
        >
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs font-semibold text-mt-muted">
            New investigation
            <Input
              value={name}
              maxLength={80}
              onChange={(event) => setName(event.target.value)}
              placeholder="Engagement name"
            />
          </label>
          <Button type="submit" disabled={create.isPending}>
            Create
          </Button>
          {formError ? (
            <p className="w-full text-sm text-mt-danger" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="No investigations yet">
          {canMutate
            ? "Name a group, then attach runs from a scan."
            : "When an operator groups runs, they appear here."}
        </EmptyState>
      ) : (
        <div className="mt-card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-mt-border text-xs text-mt-muted">
                <th className="px-3 py-1 font-semibold">Name</th>
                <th className="px-3 py-1 font-semibold">Status</th>
                <th className="px-3 py-1 font-semibold">Runs</th>
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
                      {row.status === "open" ? "Open" : "Closed"}
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
