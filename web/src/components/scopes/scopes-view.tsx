"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { apiFetch } from "@/lib/api/browser";
import { errorMessage, getJson, hasArray, sendJson } from "@/lib/api/client";
import { readDetail } from "@/lib/api/errors";
import type { ScopeListResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";

/** Same ceiling as the API body cap (METATRACER_MAX_REQUEST_BODY_BYTES default). */
export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;

function domainList(value: string): string[] {
  return value.split(/[\n,]+/).map((entry) => entry.trim()).filter(Boolean);
}

const scopeSchema = z.object({
  name: z.string().trim().min(1, "Name and at least one domain are required.").max(64, "Names are at most 64 characters."),
  description: z.string().trim().max(1000, "Descriptions are at most 1000 characters.").nullable(),
  domains: z.array(z.string()).min(1, "Name and at least one domain are required."),
});

/** Client-side checks before the upload, then the server's own message. */
export async function importScopesFile(file: File): Promise<{ imported: number; skipped: number }> {
  if (file.size > MAX_IMPORT_BYTES) {
    throw new Error("File too large: the limit is 5 MiB.");
  }
  const text = await file.text();
  try {
    JSON.parse(text);
  } catch {
    throw new Error("The file is not valid JSON.");
  }
  let response: Response;
  try {
    response = await apiFetch("/api/scopes/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: text,
    });
  } catch {
    throw new Error("Network error: the API is unreachable.");
  }
  if (response.status === 413) throw new Error("File too large: the server rejected the upload.");
  if (response.status === 403) throw new Error("Operator role required.");
  if (!response.ok) {
    const detail = await readDetail(response);
    throw new Error(`Import failed: ${detail || `HTTP ${response.status}`}`);
  }
  const payload: unknown = await response.json().catch(() => null);
  const row = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  return {
    imported: typeof row.imported === "number" ? row.imported : 0,
    skipped: typeof row.skipped === "number" ? row.skipped : 0,
  };
}

export function ScopesView() {
  const queryClient = useQueryClient();
  const actor = useActor();
  const canMutate = actor === "operator";
  const [formError, setFormError] = useState("");
  const [actionError, setActionError] = useState("");
  const [importMessage, setImportMessage] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [domainsText, setDomainsText] = useState("");

  const scopes = useQuery({
    queryKey: queryKeys.scopes,
    queryFn: () => getJson<ScopeListResponse>("/api/scopes", hasArray("scopes")),
  });
  const rows = scopes.data?.scopes ?? [];
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.scopes });

  function resetForm() {
    setEditing(null);
    setName("");
    setDescription("");
    setDomainsText("");
    setFormError("");
  }

  const save = useMutation({
    mutationFn: (body: z.infer<typeof scopeSchema>) =>
      editing
        ? sendJson(`/api/scopes/${encodeURIComponent(editing)}`, "PUT", body)
        : sendJson("/api/scopes", "POST", body),
    onSuccess: () => {
      resetForm();
      void refresh();
    },
    onError: (error) => setFormError(errorMessage(error, "Could not save the scope")),
  });
  const remove = useMutation({
    mutationFn: (id: string) => sendJson(`/api/scopes/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: (_data, id) => {
      if (editing === id) resetForm();
      void refresh();
    },
    onError: (error) => setActionError(errorMessage(error, "Could not delete the scope")),
  });
  const importer = useMutation({
    mutationFn: importScopesFile,
    onSuccess: (result) => {
      setImportMessage(`Imported ${result.imported} scope(s), ${result.skipped} skipped (already exist).`);
      void refresh();
    },
  });

  function submit() {
    setFormError("");
    const parsed = scopeSchema.safeParse({
      name,
      description: description.trim() || null,
      domains: domainList(domainsText),
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check the form.");
      return;
    }
    save.mutate(parsed.data);
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mt-title">Scopes</h1>
          <p className="text-sm text-mt-fg">
            Reusable sets of authorized domains. A scan copies the domains of a scope onto the run, so editing or deleting a scope never changes past runs.
          </p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/">New scan</Link>
        </Button>
      </div>
      {canMutate ? (
        <section className="flex flex-col gap-3 rounded-md border border-mt-border bg-mt-surface p-4">
          <h2 className="text-sm font-semibold">Import scopes from a file</h2>
          <p className="text-sm text-mt-fg">
            Upload a portable scopes JSON (up to 5 MiB). Existing names are skipped — nothing is overwritten.
          </p>
          <label htmlFor="scope-import-file" className="text-xs font-semibold text-mt-muted">Portable scopes JSON file</label>
          <input
            id="scope-import-file"
            type="file"
            accept="application/json,.json"
            disabled={importer.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              setImportMessage("");
              importer.reset();
              if (file) importer.mutate(file);
              event.target.value = "";
            }}
          />
          {importMessage ? <p role="status" className="text-xs text-mt-muted">{importMessage}</p> : null}
          {importer.isError ? (
            <p role="alert" className="text-sm text-mt-danger">
              {importer.error instanceof Error ? importer.error.message : "Import failed."}
            </p>
          ) : null}
        </section>
      ) : null}
      {canMutate ? (
        <section className="flex flex-col gap-4 rounded-md border border-mt-border bg-mt-surface p-4">
          <h2 className="text-sm font-semibold">{editing ? "Edit scope" : "New scope"}</h2>
          <label htmlFor="scope-name" className="text-xs font-semibold text-mt-muted">Name</label>
          <input id="scope-name" value={name} maxLength={64} onChange={(event) => setName(event.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" placeholder="e.g. acme-2026-engagement" />
          <label htmlFor="scope-desc" className="text-xs font-semibold text-mt-muted">Description (optional)</label>
          <textarea id="scope-desc" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" />
          <label htmlFor="scope-domains" className="text-xs font-semibold text-mt-muted">Domains</label>
          <textarea id="scope-domains" rows={3} value={domainsText} onChange={(event) => setDomainsText(event.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" placeholder="One per line or comma-separated" />
          <p className="text-xs text-mt-muted">Stored host-normalized. Wildcards like *.example.com are allowed; one-label bases such as *.com are rejected.</p>
          {formError ? <p role="alert" className="text-sm text-mt-danger">{formError}</p> : null}
          <div className="flex gap-2">
            <Button disabled={save.isPending} onClick={submit}>{editing ? "Save changes" : "Create scope"}</Button>
            {editing ? <Button variant="secondary" onClick={resetForm}>Cancel</Button> : null}
          </div>
        </section>
      ) : null}
      {actionError ? <p role="alert" className="text-sm text-mt-danger">{actionError}</p> : null}
      {scopes.isError ? (
        <ErrorState message={errorMessage(scopes.error, "Could not load scopes")} onRetry={() => void scopes.refetch()} />
      ) : null}
      {scopes.isPending ? <p className="text-sm text-mt-muted">Loading scopes…</p> : null}
      {scopes.isSuccess && rows.length === 0 ? (
        <EmptyState title="No scopes yet">
          {canMutate ? "Create one to reuse the same authorized domains across scans." : "An operator can create scopes."}
        </EmptyState>
      ) : null}
      {rows.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">Saved scopes</caption>
          <thead>
            <tr className="text-left text-xs text-mt-muted">
              <th className="py-1 font-medium">Name</th>
              <th className="py-1 font-medium">Domains</th>
              {canMutate ? <th className="py-1 text-right font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((scope) => (
              <tr key={scope.id} className="border-t border-mt-border">
                <td className="py-1.5">
                  <p className="text-sm text-mt-fg">{scope.name}</p>
                  {scope.description ? <p className="text-xs text-mt-muted">{scope.description}</p> : null}
                </td>
                <td className="py-1.5">
                  <p className="mt-tech">{scope.domains.join(", ")}</p>
                  <p className="text-xs text-mt-muted">{scope.total_domains} domain(s)</p>
                </td>
                {canMutate ? (
                  <td className="py-1.5 text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="secondary"
                        className="px-2 py-1 text-xs"
                        onClick={() => {
                          setEditing(scope.id);
                          setName(scope.name);
                          setDescription(scope.description ?? "");
                          setDomainsText(scope.domains.join("\n"));
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="danger"
                        className="px-2 py-1 text-xs"
                        onClick={() => {
                          setActionError("");
                          if (window.confirm("Delete this scope? Past runs keep their copied domains.")) {
                            remove.mutate(scope.id);
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
