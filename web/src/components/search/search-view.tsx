"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { errorMessage, getJson, isObject } from "@/lib/api/client";
import { queryKeys } from "@/lib/query/keys";
import { FINDING_TYPE_LABEL, SEVERITY_LABEL, TRIAGE_LABEL } from "@/lib/ui-copy";

export type FindingSearchHit = {
  kind: "finding";
  id: string;
  run_id: string;
  asset_id: string;
  asset_url: string;
  finding_type: string;
  type_label: string;
  title: string | null;
  field_source: string;
  evidence_snippet: string;
  severity: string | null;
  triage_status: string;
  created_at: string;
};

export type MetadataSearchHit = {
  kind: "metadata";
  id: number;
  run_id: string;
  asset_id: string;
  asset_url: string;
  namespace: string;
  key: string;
  value: string;
};

export type GlobalSearchResponse = {
  query: string;
  kind: string;
  mode: string;
  findings: { total: number; items: FindingSearchHit[]; has_more: boolean; next_cursor: string | null };
  metadata: { total: number; items: MetadataSearchHit[]; has_more: boolean; next_cursor: string | null };
};

export function isGlobalSearch(value: unknown): value is GlobalSearchResponse {
  if (!isObject(value)) return false;
  const findings = value.findings;
  const metadata = value.metadata;
  return (
    isObject(findings) &&
    Array.isArray(findings.items) &&
    isObject(metadata) &&
    Array.isArray(metadata.items)
  );
}

export function searchUrl(params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const encoded = query.toString();
  return encoded ? `/api/search?${encoded}` : "/api/search";
}

const NAMESPACES = ["exif", "xmp", "pdfinfo", "iptc", "http", "html", "js", "ooxml", "odf"] as const;
const TYPES = Object.keys(FINDING_TYPE_LABEL);

type Filters = {
  q: string;
  kind: string;
  mode: string;
  type: string;
  namespace: string;
  severity: string;
  triage: string;
};

function readFilters(): Filters {
  if (typeof window === "undefined") {
    return { q: "", kind: "all", mode: "lexical", type: "", namespace: "", severity: "", triage: "" };
  }
  const params = new URLSearchParams(window.location.search);
  const kind = params.get("kind");
  return {
    q: params.get("q") ?? "",
    kind: kind === "findings" || kind === "metadata" ? kind : "all",
    mode: params.get("mode") === "similar" ? "similar" : "lexical",
    type: params.get("type") ?? "",
    namespace: params.get("namespace") ?? "",
    severity: params.get("severity") ?? "",
    triage: params.get("triage") ?? "",
  };
}

function writeFilters(filters: Filters) {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.kind !== "all") params.set("kind", filters.kind);
  if (filters.mode !== "lexical") params.set("mode", filters.mode);
  if (filters.type) params.set("type", filters.type);
  if (filters.namespace) params.set("namespace", filters.namespace);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.triage) params.set("triage", filters.triage);
  const search = params.toString();
  window.history.replaceState(window.history.state, "", search ? `?${search}` : window.location.pathname);
}

export function SearchView() {
  const [filters, setFilters] = useState<Filters>(readFilters);
  const [draft, setDraft] = useState(filters.q);

  const apply = useCallback((next: Filters) => {
    writeFilters(next);
    setFilters(next);
  }, []);

  const apiParams = {
    q: filters.q.trim() || undefined,
    kind: filters.kind,
    mode: filters.mode === "similar" ? "similar" : undefined,
    finding_type: filters.type || undefined,
    namespace: filters.namespace || undefined,
    severity: filters.severity || undefined,
    triage_status: filters.triage || undefined,
    limit: "50",
  };

  const search = useQuery({
    queryKey: queryKeys.globalSearch(apiParams),
    queryFn: () => getJson<GlobalSearchResponse>(searchUrl(apiParams), isGlobalSearch),
    enabled: filters.q.trim().length > 0,
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    apply({ ...filters, q: draft.trim() });
  }

  function patch(partial: Partial<Filters>) {
    const next = { ...filters, ...partial, q: draft.trim() || filters.q };
    apply(next);
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="mt-page-head">
        <div>
          <h1 className="mt-page-title">Buscar</h1>
          <p className="mt-meta">Hallazgos y metadatos ya guardados. No inicia un escaneo.</p>
        </div>
      </div>
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <div className="mt-command">
          <label className="mt-command-field text-sm text-mt-muted">
            Consulta
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              name="q"
              aria-label="Consulta de búsqueda"
              placeholder="Email, GPS, clave EXIF…"
            />
          </label>
          <Button type="submit" className="mt-command-start">
            Buscar
          </Button>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          <FilterSelect
            label="Origen"
            value={filters.kind}
            onChange={(kind) => patch({ kind })}
            options={[
              ["all", "Hallazgos y metadatos"],
              ["findings", "Solo hallazgos"],
              ["metadata", "Solo metadatos"],
            ]}
          />
          <FilterSelect
            label="Modo"
            value={filters.mode}
            onChange={(mode) => patch({ mode })}
            options={[
              ["lexical", "Léxico"],
              ["similar", "Similar (índice local)"],
            ]}
          />
          <FilterSelect
            label="Tipo"
            value={filters.type}
            onChange={(type) => patch({ type })}
            options={[["", "Cualquier tipo"], ...TYPES.map((type) => [type, FINDING_TYPE_LABEL[type] ?? type])]}
          />
          <FilterSelect
            label="Espacio de nombres"
            value={filters.namespace}
            onChange={(namespace) => patch({ namespace })}
            options={[["", "Cualquiera"], ...NAMESPACES.map((item) => [item, item])]}
          />
          <FilterSelect
            label="Severidad"
            value={filters.severity}
            onChange={(severity) => patch({ severity })}
            options={[
              ["", "Cualquiera"],
              ["unclassified", SEVERITY_LABEL.unclassified],
              ["critical", SEVERITY_LABEL.critical],
              ["high", SEVERITY_LABEL.high],
              ["medium", SEVERITY_LABEL.medium],
              ["low", SEVERITY_LABEL.low],
              ["info", SEVERITY_LABEL.info],
            ]}
          />
          <FilterSelect
            label="Triaje"
            value={filters.triage}
            onChange={(triage) => patch({ triage })}
            options={[
              ["", "Cualquiera"],
              ["open", TRIAGE_LABEL.open],
              ["confirmed", TRIAGE_LABEL.confirmed],
              ["fixed", TRIAGE_LABEL.fixed],
              ["false_positive", TRIAGE_LABEL.false_positive],
            ]}
          />
        </div>
      </form>
      {filters.q.trim().length === 0 ? (
        <EmptyState title="Escribe una consulta">No inicia un escaneo.</EmptyState>
      ) : search.isLoading ? (
        <LoadingState label="Buscando" variant="list" />
      ) : search.isError ? (
        <ErrorState message={errorMessage(search.error, "No se pudo completar la búsqueda")} onRetry={() => void search.refetch()} />
      ) : search.data && search.data.findings.total === 0 && search.data.metadata.total === 0 ? (
        <EmptyState title="Sin coincidencias">Ningún hallazgo ni campo de metadatos coincide con esta consulta.</EmptyState>
      ) : search.data ? (
        <Results data={search.data} />
      ) : null}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<readonly [string, string]>;
}) {
  return (
    <label className="flex flex-col gap-1 text-mt-muted">
      {label}
      <select
        className="rounded-sm border border-mt-border-strong bg-mt-bg px-2 py-1 text-mt-fg"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map(([id, text]) => (
          <option key={id || "any"} value={id}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

function Results({ data }: { data: GlobalSearchResponse }) {
  return (
    <div className="flex flex-col gap-8">
      {data.findings.items.length > 0 ? (
        <section aria-label="Hallazgos">
          <h2 className="mt-section-title mb-3">Hallazgos ({data.findings.total})</h2>
          <ul className="flex flex-col gap-2">
            {data.findings.items.map((hit) => (
              <li key={hit.id} className="mt-card px-3 py-2">
                <Link className="text-sm text-mt-fg underline" href={`/runs/${encodeURIComponent(hit.run_id)}/findings`}>
                  {hit.title || hit.type_label}
                </Link>
                <p className="mt-tech mt-1 text-xs text-mt-muted">
                  {FINDING_TYPE_LABEL[hit.finding_type] ?? hit.type_label}
                  {hit.severity ? ` · ${SEVERITY_LABEL[hit.severity as keyof typeof SEVERITY_LABEL] ?? hit.severity}` : ""}
                  {` · ${TRIAGE_LABEL[hit.triage_status as keyof typeof TRIAGE_LABEL] ?? hit.triage_status}`}
                </p>
                <p className="mt-evidence mt-1 break-all text-sm">{hit.evidence_snippet}</p>
                <p className="mt-tech mt-1 break-all text-xs text-mt-faint">{hit.asset_url}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {data.metadata.items.length > 0 ? (
        <section aria-label="Metadatos">
          <h2 className="mt-section-title mb-3">Metadatos ({data.metadata.total})</h2>
          <ul className="flex flex-col gap-2">
            {data.metadata.items.map((hit) => (
              <li key={`${hit.run_id}-${hit.id}`} className="mt-card px-3 py-2">
                <Link className="text-sm text-mt-fg underline" href={`/runs/${encodeURIComponent(hit.run_id)}/metadata`}>
                  {hit.namespace}:{hit.key}
                </Link>
                <p className="mt-tech mt-1 break-all text-sm text-mt-fg">{hit.value}</p>
                <p className="mt-tech mt-1 break-all text-xs text-mt-faint">{hit.asset_url}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
