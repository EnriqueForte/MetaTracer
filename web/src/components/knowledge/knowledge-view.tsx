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
  if (file.size > MAX_KB_BYTES) throw new Error("El fichero es demasiado grande: el límite es 5 MiB.");
  const text = await file.text();
  try {
    JSON.parse(text);
  } catch {
    throw new Error("El fichero no es JSON válido.");
  }
  let response: Response;
  try {
    response = await apiFetch("/api/knowledge/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: text,
    });
  } catch {
    throw new Error("Error de red: la API no está accesible.");
  }
  if (response.status === 413) throw new Error("El fichero es demasiado grande: el servidor rechazó la subida.");
  if (response.status === 403) throw new Error("Se requiere el rol de operador.");
  if (!response.ok) throw new Error(`La importación falló: ${(await readDetail(response)) || `HTTP ${response.status}`}`);
  const payload: unknown = await response.json().catch(() => null);
  const imported = payload && typeof payload === "object" ? (payload as { imported?: unknown }).imported : 0;
  return typeof imported === "number" ? imported : 0;
}

async function exportKnowledge(): Promise<void> {
  const response = await apiFetch("/api/knowledge/export", { method: "POST" });
  if (!response.ok) throw new Error(response.status === 403 ? "Se requiere el rol de operador." : `La exportación falló (HTTP ${response.status}).`);
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
    onSuccess: (count) => setMessage(`Importados ${count} precedente(s). Las filas ya conocidas se omitieron.`),
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
        <h1 className="mt-title">Conocimiento</h1>
        <p role="alert" className="text-sm text-mt-warning">Se requiere el rol de operador</p>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div>
        <h1 className="mt-title">Conocimiento</h1>
        <p className="text-sm text-mt-fg">
          Precedentes históricos que el agente puede citar como contexto. El fichero portable lleva tipo de
          hallazgo, fragmento saneado, severidad y título — nunca ids de escaneo, metadatos crudos ni bytes.
        </p>
      </div>
      <section className="flex flex-col gap-3 rounded-md border border-mt-border bg-mt-surface p-4" aria-label="Exportar e importar">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" disabled={exporter.isPending} onClick={() => exporter.mutate()}>
            {exporter.isPending ? "Exportando…" : "Exportar precedentes"}
          </Button>
          {exporter.isError ? (
            <p role="alert" className="text-sm text-mt-danger">
              {exporter.error instanceof Error ? exporter.error.message : "La exportación falló."}
            </p>
          ) : null}
        </div>
        <label htmlFor="kb-import-file" className="text-xs font-semibold text-mt-muted">
          Importar un fichero portable de conocimiento (JSON, hasta 5 MiB)
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
            {importer.error instanceof Error ? importer.error.message : "La importación falló."}
          </p>
        ) : null}
      </section>
      <section className="flex flex-col gap-3" aria-label="Buscar precedentes">
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); setSubmitted(q.trim()); }}>
          <div className="flex min-w-[16rem] flex-1 flex-col gap-1">
            <label htmlFor="kb-search" className="text-xs font-semibold text-mt-muted">Buscar precedentes similares</label>
            <Input id="kb-search" className="mt-tech" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Fragmento de evidencia o campo de origen" />
          </div>
          <Button type="submit" variant="secondary" disabled={!q.trim()}>Buscar</Button>
        </form>
        {search.isError ? <p role="alert" className="text-sm text-mt-danger">{errorMessage(search.error, "La búsqueda falló")}</p> : null}
        {search.isSuccess && search.data.hits.length === 0 ? <EmptyState title="Ningún precedente coincide" /> : null}
        {search.isSuccess && search.data.hits.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {search.data.hits.map((hit) => (
              <li key={hit.finding_id} className="mt-card flex flex-col gap-1 p-3">
                <p className="text-sm text-mt-fg">{hit.title || hit.finding_type}</p>
                <p className="mt-tech">{hit.evidence_snippet}</p>
                <p className="mt-meta">
                  {hit.finding_type} · {hit.severity ?? "sin clasificar"} · puntuación {hit.score}
                </p>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
