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
  name: z.string().trim().min(1, "El nombre y al menos un dominio son obligatorios.").max(64, "Los nombres tienen como máximo 64 caracteres."),
  description: z.string().trim().max(1000, "Las descripciones tienen como máximo 1000 caracteres.").nullable(),
  domains: z.array(z.string()).min(1, "El nombre y al menos un dominio son obligatorios."),
});

/** Client-side checks before the upload, then the server's own message. */
export async function importScopesFile(file: File): Promise<{ imported: number; skipped: number }> {
  if (file.size > MAX_IMPORT_BYTES) {
    throw new Error("El fichero es demasiado grande: el límite es 5 MiB.");
  }
  const text = await file.text();
  try {
    JSON.parse(text);
  } catch {
    throw new Error("El fichero no es JSON válido.");
  }
  let response: Response;
  try {
    response = await apiFetch("/api/scopes/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: text,
    });
  } catch {
    throw new Error("Error de red: la API no está accesible.");
  }
  if (response.status === 413) throw new Error("El fichero es demasiado grande: el servidor rechazó la subida.");
  if (response.status === 403) throw new Error("Se requiere el rol de operador.");
  if (!response.ok) {
    const detail = await readDetail(response);
    throw new Error(`La importación falló: ${detail || `HTTP ${response.status}`}`);
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
    onError: (error) => setFormError(errorMessage(error, "No se pudo guardar el alcance")),
  });
  const remove = useMutation({
    mutationFn: (id: string) => sendJson(`/api/scopes/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: (_data, id) => {
      if (editing === id) resetForm();
      void refresh();
    },
    onError: (error) => setActionError(errorMessage(error, "No se pudo eliminar el alcance")),
  });
  const importer = useMutation({
    mutationFn: importScopesFile,
    onSuccess: (result) => {
      setImportMessage(`Importados ${result.imported} alcance(s), ${result.skipped} omitidos (ya existían).`);
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
      setFormError(parsed.error.issues[0]?.message ?? "Revisa el formulario.");
      return;
    }
    save.mutate(parsed.data);
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mt-title">Alcances</h1>
          <p className="text-sm text-mt-fg">
            Conjuntos reutilizables de dominios autorizados. Un escaneo copia los dominios de un alcance al run, así que editar o borrar un alcance nunca cambia escaneos pasados.
          </p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/">Nuevo escaneo</Link>
        </Button>
      </div>
      {canMutate ? (
        <section className="flex flex-col gap-3 rounded-md border border-mt-border bg-mt-surface p-4">
          <h2 className="text-sm font-semibold">Importar alcances desde un fichero</h2>
          <p className="text-sm text-mt-fg">
            Sube un JSON portable de alcances (hasta 5 MiB). Los nombres existentes se omiten — no se sobrescribe nada.
          </p>
          <label htmlFor="scope-import-file" className="text-xs font-semibold text-mt-muted">Fichero JSON portable de alcances</label>
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
              {importer.error instanceof Error ? importer.error.message : "La importación falló."}
            </p>
          ) : null}
        </section>
      ) : null}
      {canMutate ? (
        <section className="flex flex-col gap-4 rounded-md border border-mt-border bg-mt-surface p-4">
          <h2 className="text-sm font-semibold">{editing ? "Editar alcance" : "Nuevo alcance"}</h2>
          <label htmlFor="scope-name" className="text-xs font-semibold text-mt-muted">Nombre</label>
          <input id="scope-name" value={name} maxLength={64} onChange={(event) => setName(event.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" placeholder="e.g. acme-2026-engagement" />
          <label htmlFor="scope-desc" className="text-xs font-semibold text-mt-muted">Descripción (opcional)</label>
          <textarea id="scope-desc" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" />
          <label htmlFor="scope-domains" className="text-xs font-semibold text-mt-muted">Dominios</label>
          <textarea id="scope-domains" rows={3} value={domainsText} onChange={(event) => setDomainsText(event.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" placeholder="Uno por línea o separados por comas" />
          <p className="text-xs text-mt-muted">Se guardan con el host normalizado. Se permiten comodines como *.example.com; bases de una sola etiqueta como *.com se rechazan.</p>
          {formError ? <p role="alert" className="text-sm text-mt-danger">{formError}</p> : null}
          <div className="flex gap-2">
            <Button disabled={save.isPending} onClick={submit}>{editing ? "Guardar cambios" : "Crear alcance"}</Button>
            {editing ? <Button variant="secondary" onClick={resetForm}>Cancelar</Button> : null}
          </div>
        </section>
      ) : null}
      {actionError ? <p role="alert" className="text-sm text-mt-danger">{actionError}</p> : null}
      {scopes.isError ? (
        <ErrorState message={errorMessage(scopes.error, "No se pudieron cargar los alcances")} onRetry={() => void scopes.refetch()} />
      ) : null}
      {scopes.isPending ? <p className="text-sm text-mt-muted">Cargando alcances…</p> : null}
      {scopes.isSuccess && rows.length === 0 ? (
        <EmptyState title="Aún no hay alcances">
          {canMutate ? "Crea uno para reutilizar los mismos dominios autorizados en varios escaneos." : "Un operador puede crear alcances."}
        </EmptyState>
      ) : null}
      {rows.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">Alcances guardados</caption>
          <thead>
            <tr className="text-left text-xs text-mt-muted">
              <th className="py-1 font-medium">Nombre</th>
              <th className="py-1 font-medium">Dominios</th>
              {canMutate ? <th className="py-1 text-right font-medium">Acciones</th> : null}
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
                  <p className="text-xs text-mt-muted">{scope.total_domains} dominio(s)</p>
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
                        Editar
                      </Button>
                      <Button
                        variant="danger"
                        className="px-2 py-1 text-xs"
                        onClick={() => {
                          setActionError("");
                          if (window.confirm("¿Eliminar este alcance? Los escaneos pasados conservan los dominios copiados.")) {
                            remove.mutate(scope.id);
                          }
                        }}
                      >
                        Eliminar
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
