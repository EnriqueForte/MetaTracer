"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/browser";

type ScopeRow = {
  id: string;
  name: string;
  description: string | null;
  domains: string[];
  total_domains: number;
};

function parseScopes(value: unknown): ScopeRow[] | null {
  if (!value || typeof value !== "object") return null;
  const rows = (value as { scopes?: unknown }).scopes;
  if (!Array.isArray(rows)) return null;
  const scopes: ScopeRow[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const item = row as Record<string, unknown>;
    if (typeof item.id !== "string" || typeof item.name !== "string") return null;
    if (!Array.isArray(item.domains) || !item.domains.every((domain) => typeof domain === "string")) return null;
    scopes.push({
      id: item.id,
      name: item.name,
      description: typeof item.description === "string" ? item.description : null,
      domains: item.domains,
      total_domains: typeof item.total_domains === "number" ? item.total_domains : item.domains.length,
    });
  }
  return scopes;
}

function domainList(value: string): string[] {
  return value.split(/[\n,]+/).map((entry) => entry.trim()).filter(Boolean);
}

export function ScopesView() {
  const [scopes, setScopes] = useState<ScopeRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [importMessage, setImportMessage] = useState("");
  const [importError, setImportError] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [domainsText, setDomainsText] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await apiFetch("/api/scopes");
      if (!response.ok) {
        setError("Could not load scopes.");
        setLoaded(true);
        return;
      }
      const parsed = parseScopes(await response.json());
      if (!parsed) {
        setError("Could not load scopes.");
        setLoaded(true);
        return;
      }
      setScopes(parsed);
      setLoaded(true);
    } catch {
      setError("Network error: the API is unreachable.");
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function resetForm() {
    setEditing(null);
    setName("");
    setDescription("");
    setDomainsText("");
    setFormError("");
  }

  async function save() {
    const domains = domainList(domainsText);
    if (!name.trim() || domains.length === 0) {
      setFormError("Name and at least one domain are required.");
      return;
    }
    setFormError("");
    const body = { name: name.trim(), description: description.trim() || null, domains };
    const response = await apiFetch(editing ? `/api/scopes/${encodeURIComponent(editing)}` : "/api/scopes", {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      setFormError(`Could not save the scope (HTTP ${response.status}).`);
      return;
    }
    resetForm();
    await load();
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this scope? Past runs keep their copied domains.")) return;
    const response = await apiFetch(`/api/scopes/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (response.status !== 204) {
      setError(`Could not delete the scope (HTTP ${response.status}).`);
      return;
    }
    if (editing === id) resetForm();
    await load();
  }

  async function importFile(file: File | undefined) {
    if (!file) return;
    setImportBusy(true);
    setImportError("");
    setImportMessage("");
    try {
      const text = await file.text();
      const response = await apiFetch("/api/scopes/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text,
      });
      if (!response.ok) {
        setImportError(`Import failed (HTTP ${response.status}).`);
        return;
      }
      const payload: unknown = await response.json();
      const imported = payload && typeof payload === "object" ? (payload as { imported?: unknown }).imported : null;
      const skipped = payload && typeof payload === "object" ? (payload as { skipped?: unknown }).skipped : null;
      setImportMessage(`Imported ${typeof imported === "number" ? imported : 0}, skipped ${typeof skipped === "number" ? skipped : 0}.`);
      await load();
    } catch {
      setImportError("Import failed.");
    } finally {
      setImportBusy(false);
    }
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
      <section className="flex flex-col gap-3 rounded-md border border-mt-border bg-mt-surface p-4">
        <h2 className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Import scopes from a file</h2>
        <p className="text-sm text-mt-fg">
          Upload a portable scopes JSON. Existing names are skipped — nothing is overwritten.
        </p>
        <label htmlFor="scope-import-file" className="text-xs font-semibold text-mt-muted">Portable scopes JSON file</label>
        <input id="scope-import-file" type="file" accept="application/json,.json" disabled={importBusy} onChange={(event) => void importFile(event.target.files?.[0])} />
        {importMessage ? <p role="status" className="text-xs text-mt-muted">{importMessage}</p> : null}
        {importError ? <p role="alert" className="text-sm text-mt-danger">{importError}</p> : null}
      </section>
      <section className="flex flex-col gap-4 rounded-md border border-mt-border bg-mt-surface p-4">
        <h2 className="text-xs font-semibold tracking-wide text-mt-muted uppercase">{editing ? "Edit scope" : "New scope"}</h2>
        <label htmlFor="scope-name" className="text-xs font-semibold text-mt-muted">Name</label>
        <input id="scope-name" value={name} maxLength={64} onChange={(event) => setName(event.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" placeholder="e.g. acme-2026-engagement" />
        <label htmlFor="scope-desc" className="text-xs font-semibold text-mt-muted">Description (optional)</label>
        <textarea id="scope-desc" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" />
        <label htmlFor="scope-domains" className="text-xs font-semibold text-mt-muted">Domains</label>
        <textarea id="scope-domains" rows={3} value={domainsText} onChange={(event) => setDomainsText(event.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" placeholder="One per line or comma-separated" />
        <p className="text-xs text-mt-muted">Stored host-normalized. Wildcards like *.example.com are allowed.</p>
        {formError ? <p role="alert" className="text-sm text-mt-danger">{formError}</p> : null}
        <div className="flex gap-2">
          <Button onClick={() => void save()}>{editing ? "Save changes" : "Create scope"}</Button>
          {editing ? <Button variant="secondary" onClick={resetForm}>Cancel</Button> : null}
        </div>
      </section>
      {error ? <p role="alert" className="text-sm text-mt-danger">{error}</p> : null}
      {!loaded ? <p className="text-sm text-mt-muted">Loading scopes…</p> : null}
      {loaded && scopes.length === 0 ? <p className="text-sm text-mt-muted">No scopes yet.</p> : null}
      {scopes.map((scope) => (
        <div key={scope.id} className="flex flex-wrap items-start justify-between gap-3 border-t border-mt-border py-3">
          <div>
            <p className="text-sm font-semibold text-mt-fg">{scope.name}</p>
            {scope.description ? <p className="text-xs text-mt-muted">{scope.description}</p> : null}
            <p className="mt-tech">{scope.domains.join(", ")}</p>
            <p className="text-xs text-mt-muted">{scope.total_domains} domain(s)</p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setEditing(scope.id);
                setName(scope.name);
                setDescription(scope.description ?? "");
                setDomainsText(scope.domains.join("\n"));
              }}
            >
              Edit
            </Button>
            <Button variant="danger" onClick={() => void remove(scope.id)}>Delete</Button>
          </div>
        </div>
      ))}
    </div>
  );
}
