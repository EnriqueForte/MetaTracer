"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/states";
import { apiFetch } from "@/lib/api/browser";
import { errorMessage, getJson, hasArray } from "@/lib/api/client";
import { readDetail } from "@/lib/api/errors";
import type { SearchResponse } from "@/lib/api/types";
import { useActor } from "@/lib/session";

/** Same ceiling as the API body cap. */
export const MAX_KB_BYTES = 5 * 1024 * 1024;

export async function importKnowledgeFile(file: File): Promise<number> {
  if (file.size > MAX_KB_BYTES) throw new Error("File too large: the limit is 5 MiB.");
  const text = await file.text();
  try {
    JSON.parse(text);
  } catch {
    throw new Error("The file is not valid JSON.");
  }
  let response: Response;
  try {
    response = await apiFetch("/api/knowledge/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: text,
    });
  } catch {
    throw new Error("Network error: the API is unreachable.");
  }
  if (response.status === 413) throw new Error("File too large: the server rejected the upload.");
  if (response.status === 403) throw new Error("Operator role required.");
  if (!response.ok) throw new Error(`Import failed: ${(await readDetail(response)) || `HTTP ${response.status}`}`);
  const payload: unknown = await response.json().catch(() => null);
  const imported = payload && typeof payload === "object" ? (payload as { imported?: unknown }).imported : 0;
  return typeof imported === "number" ? imported : 0;
}

async function exportKnowledge(): Promise<void> {
  const response = await apiFetch("/api/knowledge/export", { method: "POST" });
  if (!response.ok) throw new Error(response.status === 403 ? "Operator role required." : `Export failed (HTTP ${response.status}).`);
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = "kb-export.json";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export function KnowledgeView() {
  const actor = useActor();
  const [message, setMessage] = useState("");
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");

  const exporter = useMutation({ mutationFn: exportKnowledge });
  const importer = useMutation({
    mutationFn: importKnowledgeFile,
    onSuccess: (count) => setMessage(`Imported ${count} precedent(s). Already known rows were skipped.`),
  });
  const search = useQuery({
    queryKey: ["knowledge", "search", submitted],
    queryFn: () =>
      getJson<SearchResponse>(`/api/knowledge/search?q=${encodeURIComponent(submitted)}&limit=10`, hasArray("hits")),
    enabled: actor === "operator" && submitted.length > 0,
  });

  if (actor === "viewer") {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="mt-title">Knowledge</h1>
        <p role="alert" className="text-sm text-mt-warning">Operator role required</p>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div>
        <h1 className="mt-title">Knowledge</h1>
        <p className="text-sm text-mt-fg">
          Historical precedents the agent may cite as background. The portable file carries finding type,
          sanitized snippet, severity and title only — never run ids, raw metadata or file bytes.
        </p>
      </div>
      <section className="flex flex-col gap-3 rounded-md border border-mt-border bg-mt-surface p-4" aria-label="Export and import">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" disabled={exporter.isPending} onClick={() => exporter.mutate()}>
            {exporter.isPending ? "Exporting…" : "Export precedents"}
          </Button>
          {exporter.isError ? (
            <p role="alert" className="text-sm text-mt-danger">
              {exporter.error instanceof Error ? exporter.error.message : "Export failed."}
            </p>
          ) : null}
        </div>
        <label htmlFor="kb-import-file" className="text-xs font-semibold text-mt-muted">
          Import a portable knowledge file (JSON, up to 5 MiB)
        </label>
        <input
          id="kb-import-file"
          type="file"
          accept="application/json,.json"
          disabled={importer.isPending}
          onChange={(event) => {
            const file = event.target.files?.[0];
            setMessage("");
            importer.reset();
            if (file) importer.mutate(file);
            event.target.value = "";
          }}
        />
        {message ? <p role="status" className="text-xs text-mt-muted">{message}</p> : null}
        {importer.isError ? (
          <p role="alert" className="text-sm text-mt-danger">
            {importer.error instanceof Error ? importer.error.message : "Import failed."}
          </p>
        ) : null}
      </section>
      <section className="flex flex-col gap-3" aria-label="Search precedents">
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); setSubmitted(q.trim()); }}>
          <div className="flex min-w-[16rem] flex-1 flex-col gap-1">
            <label htmlFor="kb-search" className="text-xs font-semibold text-mt-muted">Find similar precedents</label>
            <Input id="kb-search" className="mt-tech" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Evidence snippet or field source" />
          </div>
          <Button type="submit" variant="secondary" disabled={!q.trim()}>Search</Button>
        </form>
        {search.isError ? <p role="alert" className="text-sm text-mt-danger">{errorMessage(search.error, "Search failed")}</p> : null}
        {search.isSuccess && search.data.hits.length === 0 ? <EmptyState title="No precedents match" /> : null}
        {search.isSuccess && search.data.hits.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {search.data.hits.map((hit) => (
              <li key={hit.finding_id} className="mt-card flex flex-col gap-1 p-3">
                <p className="text-sm text-mt-fg">{hit.title || hit.finding_type}</p>
                <p className="mt-tech">{hit.evidence_snippet}</p>
                <p className="mt-meta">
                  {hit.finding_type} · {hit.severity ?? "unclassified"} · score {hit.score}
                </p>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
