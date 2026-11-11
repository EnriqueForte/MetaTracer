"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { TRIAGE_LABEL } from "@/components/run/findings/model";
import { triageVariant } from "@/components/run/findings/triage-form";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { truncate } from "@/lib/api/browser";
import { errorMessage, getJson, hasArray, isObject } from "@/lib/api/client";
import type { ComparedFindingResponse, RunComparisonResponse, RunListResponse } from "@/lib/api/types";
import { severityKey } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import { formatWhen } from "@/lib/time";
import { FINDING_TYPE_LABEL, SEVERITY_LABEL } from "@/lib/ui-copy";

function readParams(): { a: string; b: string } {
  if (typeof window === "undefined") return { a: "", b: "" };
  const params = new URLSearchParams(window.location.search);
  return { a: params.get("a") ?? "", b: params.get("b") ?? "" };
}

function writeParams(a: string, b: string) {
  const params = new URLSearchParams(window.location.search);
  if (a) params.set("a", a);
  else params.delete("a");
  if (b) params.set("b", b);
  else params.delete("b");
  const search = params.toString();
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
}

const LIMIT_LABEL: Record<string, string> = {
  max_depth: "profundidad de rastreo",
  max_pages: "tope de páginas",
  max_assets: "tope de activos",
  max_total_bytes: "presupuesto de bytes",
  max_seconds: "presupuesto de tiempo",
};

function Section({
  title,
  items,
  empty,
  showSeverityChange = false,
}: {
  title: string;
  items: ComparedFindingResponse[];
  empty: string;
  showSeverityChange?: boolean;
}) {
  return (
    <section className="mt-card flex min-w-0 flex-col gap-2 p-4" aria-label={title}>
      <h2 className="mt-section-title">
        {title} <span className="mt-meta inline">({items.length})</span>
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-mt-muted">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={`${item.run_id}-${item.finding_id}`} className="flex min-w-0 flex-col gap-1 border-t border-mt-border pt-2 first:border-t-0 first:pt-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={severityKey(item.severity)}>{SEVERITY_LABEL[severityKey(item.severity)]}</Badge>
                <span className="text-xs text-mt-muted">{FINDING_TYPE_LABEL[item.finding_type] ?? item.finding_type}</span>
                {item.triage_status && item.triage_status !== "open" ? (
                  <Badge variant={triageVariant(item.triage_status)}>{TRIAGE_LABEL[item.triage_status]}</Badge>
                ) : null}
                <Link
                  href={`/runs/${encodeURIComponent(item.run_id)}?q=${encodeURIComponent(item.evidence_snippet.slice(0, 80))}`}
                  className="mt-tech underline"
                >
                  {truncate(item.evidence_snippet, 100)}
                </Link>
              </div>
              <p className="mt-tech text-mt-muted">{truncate(item.asset_url, 100)}</p>
              {showSeverityChange ? (
                <p className="text-xs text-mt-muted">
                  La severidad cambió de {SEVERITY_LABEL[severityKey(item.previous_severity)]} a{" "}
                  {SEVERITY_LABEL[severityKey(item.severity)]}. La evidencia no cambia.
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function CompareView() {
  const [{ a, b }, setPair] = useState({ a: "", b: "" });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPair(readParams());
    setReady(true);
  }, []);

  const runs = useQuery({
    queryKey: [...queryKeys.runs, "completed-50"],
    queryFn: () => getJson<RunListResponse>("/api/runs?limit=50&status=completed", hasArray("runs")),
  });
  const comparison = useQuery({
    queryKey: queryKeys.compare(a, b),
    queryFn: () =>
      getJson<RunComparisonResponse>(
        `/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
        (value) => isObject(value) && Array.isArray(value.new),
      ),
    enabled: ready && Boolean(a && b) && a !== b,
  });

  function choose(side: "a" | "b", value: string) {
    const next = { a, b, [side]: value };
    setPair(next);
    writeParams(next.a, next.b);
  }

  const options = runs.data?.runs ?? [];
  const select = (side: "a" | "b", label: string, value: string) => (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={`compare-${side}`} className="text-xs font-semibold text-mt-muted">
        {label}
      </label>
      <select
        id={`compare-${side}`}
        value={value}
        onChange={(event) => choose(side, event.target.value)}
        className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
      >
        <option value="">Elige un escaneo completado</option>
        {value && !options.some((run) => run.run_id === value) ? <option value={value}>{value}</option> : null}
        {options.map((run) => (
          <option key={run.run_id} value={run.run_id}>
            {run.target} — {formatWhen(run.started_at)} ({run.total_findings})
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div>
        <h1 className="mt-title">Comparar escaneos</h1>
        <p className="text-sm text-mt-muted">
          Los hallazgos se emparejan por URL de activo, tipo y evidencia. La línea base es el
          escaneo anterior; el otro es el que estás revisando.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {select("a", "Escaneo de línea base", a)}
        {select("b", "Escaneo a revisar", b)}
      </div>
      {!a || !b ? <EmptyState title="Elige dos escaneos">Escoge una línea base y un escaneo a revisar.</EmptyState> : null}
      {a && b && a === b ? <EmptyState title="El mismo escaneo dos veces">Elige dos escaneos distintos.</EmptyState> : null}
      {comparison.isPending && comparison.fetchStatus === "fetching" ? <LoadingState label="Comparando escaneos" /> : null}
      {comparison.isError ? (
        <ErrorState message={errorMessage(comparison.error, "No se pudieron comparar estos escaneos")} onRetry={() => void comparison.refetch()} />
      ) : null}
      {comparison.data ? (
        <div className="flex flex-col gap-3">
          <p className="mt-meta">
            {comparison.data.a.target} ({formatWhen(comparison.data.a.started_at)}) →{" "}
            {comparison.data.b.target} ({formatWhen(comparison.data.b.started_at)})
          </p>
          {!comparison.data.coverage_recorded_b ? (
            <p className="text-sm text-mt-fg">
              Los contadores de descubrimiento no se registraron en el escaneo revisado. Un hallazgo
              listado como resuelto estuvo ausente de ese escaneo, lo que no prueba que haya desaparecido.
            </p>
          ) : (comparison.data.limits_hit_b ?? []).length > 0 ? (
            <p className="text-sm text-mt-fg">
              El escaneo revisado se detuvo porque se alcanzó un límite de rastreo (
              {(comparison.data.limits_hit_b ?? [])
                .map((limit) => LIMIT_LABEL[limit] ?? limit)
                .join(", ")}
              ). Un hallazgo resuelto puede no haberse pedido.
            </p>
          ) : null}
          <Section title="Nuevos" items={comparison.data.new} empty="Nada nuevo en el escaneo revisado." />
          <Section
            title="Reaparecidos"
            items={comparison.data.reappeared ?? []}
            empty="Nada de un escaneo anterior de esta investigación volvió a aparecer."
          />
          <Section
            title="Severidad cambiada"
            items={comparison.data.severity_changed ?? []}
            empty="Ningún hallazgo compartido cambió de severidad."
            showSeverityChange
          />
          <Section title="Resueltos" items={comparison.data.resolved} empty="Nada de la línea base desapareció." />
          <Section title="Persistentes" items={comparison.data.persistent} empty="Ningún hallazgo aparece en ambos escaneos con la misma severidad." />
        </div>
      ) : null}
    </div>
  );
}
