"use client";

import { useQuery } from "@tanstack/react-query";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { StatusChip } from "@/components/ui/status-chip";
import { errorMessage } from "@/lib/api/client";
import { SKIP_REASON_LABEL, fetchCoverage, formatBytes } from "@/lib/api/workspace";
import { queryKeys } from "@/lib/query/keys";

import { CorrelationPanel } from "./correlation-panel";
import { useWorkspace } from "./workspace-context";

const MIME_FILL = [
  "bg-mt-chart-1",
  "bg-mt-chart-2",
  "bg-mt-chart-3",
  "bg-mt-chart-4",
  "bg-mt-chart-5",
];

/** Human label for a limit identifier; the wire value stays lowercase snake_case. */
const LIMIT_LABEL: Record<string, string> = {
  max_depth: "Límite de profundidad de rastreo",
  max_pages: "Límite de páginas",
  max_assets: "Límite de activos",
  max_total_bytes: "Límite de bytes",
  max_seconds: "Límite de tiempo",
};

function Figure({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex flex-col gap-0.5 border border-mt-border bg-mt-bg p-3">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-mt-muted">{label}</dt>
      <dd className="m-0 text-xl font-semibold tabular-nums text-mt-fg">{value}</dd>
      {detail ? <dd className="m-0 text-xs text-mt-muted">{detail}</dd> : null}
    </div>
  );
}

/**
 * Coverage: what the run actually collected.
 *
 * The section exists to make one limitation explicit instead of implying
 * completeness: the crawl budget is not persisted yet (Fase 2), so the number
 * of discovered-but-not-attempted resources is *unknown*, not zero. Saying
 * "0 omitted" would be a lie; the panel says "not recorded".
 */
export function CoverageView() {
  const { runId } = useWorkspace();
  const query = useQuery({
    queryKey: [...queryKeys.run(runId), "coverage"],
    queryFn: () => fetchCoverage(runId),
  });

  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error, "No se pudo cargar el resumen de cobertura")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (query.isPending || !query.data) {
    return <LoadingState label="Cargando cobertura" />;
  }

  const coverage = query.data;
  const skipReasons = Object.entries(coverage.by_skip_reason).sort((a, b) => b[1] - a[1]);
  const namespaces = Object.entries(coverage.by_namespace).sort((a, b) => b[1] - a[1]);
  const mimeRows = Object.entries(coverage.by_content_type ?? {}).sort((a, b) => b[1] - a[1]);
  const mimeMax = Math.max(1, ...mimeRows.map(([, count]) => count));

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h2 className="mt-section-title">Cobertura de este escaneo</h2>
        <p className="mt-meta">
          Lo que el pipeline guardó. No es una medida de exposición: la ausencia de hallazgos no es
          ausencia de metadatos.
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        <Figure label="Activos registrados" value={String(coverage.total_assets)} />
        <Figure label="Extraídos" value={String(coverage.ok)} detail="Metadatos leídos" />
        <Figure label="Omitidos" value={String(coverage.skipped)} detail="Ver motivos abajo" />
        <Figure label="Fallidos" value={String(coverage.failed)} detail="Parser o transporte" />
        <Figure label="Bytes" value={formatBytes(coverage.bytes_downloaded)} detail="Cuerpos descargados" />
      </dl>

      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Figure
          label="Campos de metadatos"
          value={String(coverage.metadata_fields)}
          detail="Guardados como texto estructurado, nunca como bytes"
        />
        <Figure label="Hallazgos" value={String(coverage.findings)} detail="Subconjunto de campos que coincidió con un detector" />
      </dl>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="mt-card flex flex-col gap-2 p-4" aria-labelledby="coverage-skip-title">
          <h3 id="coverage-skip-title" className="mt-section-title">
            Por qué se omitieron activos
          </h3>
          {skipReasons.length === 0 ? (
            <p className="text-sm text-mt-muted">Ningún activo se omitió en este escaneo.</p>
          ) : (
            <dl className="flex flex-col gap-1 text-sm">
              {skipReasons.map(([reason, count]) => (
                <div key={reason} className="flex items-center justify-between gap-2">
                  <dt>
                    <StatusChip tone="skipped" label={SKIP_REASON_LABEL[reason] ?? reason} />
                  </dt>
                  <dd className="m-0 tabular-nums text-mt-fg">{count}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section className="mt-card flex flex-col gap-2 p-4" aria-labelledby="coverage-namespace-title">
          <h3 id="coverage-namespace-title" className="mt-section-title">
            Campos por espacio de nombres
          </h3>
          {namespaces.length === 0 ? (
            <p className="text-sm text-mt-muted">No se guardó ningún campo de metadatos.</p>
          ) : (
            <dl className="flex flex-col gap-1 text-sm">
              {namespaces.map(([namespace, count]) => (
                <div key={namespace} className="flex items-center justify-between gap-2">
                  <dt className="mt-tech">{namespace}</dt>
                  <dd className="m-0 tabular-nums text-mt-fg">{count}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      </div>

      <section className="mt-card flex flex-col gap-3 p-4" aria-labelledby="coverage-mime-title">
        <h3 id="coverage-mime-title" className="mt-section-title">
          Activos por tipo MIME
        </h3>
        {mimeRows.length === 0 ? (
          <EmptyState title="Sin tipos MIME">
            Este escaneo no registró ningún activo.
          </EmptyState>
        ) : (
          <div className="flex flex-col gap-3">
            {mimeRows.map(([mime, count], index) => (
              <div
                key={mime}
                className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_2.5rem] items-center gap-2"
              >
                <span className="mt-tech truncate text-xs text-mt-muted" title={mime}>
                  {mime}
                </span>
                <div className="mt-chart-track" role="img" aria-label={`${mime}: ${count}`}>
                  <span
                    className={`mt-chart-fill ${MIME_FILL[index % MIME_FILL.length]}`}
                    style={{ width: `${Math.min(100, (count / mimeMax) * 100)}%` }}
                  />
                </div>
                <span className="text-right text-xs tabular-nums text-mt-fg">{count}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <CorrelationPanel runId={runId} />

      <section
        className="rounded-md border border-mt-warning-border bg-mt-warning-bg p-3"
        aria-labelledby="coverage-limits-title"
      >
        <h3 id="coverage-limits-title" className="text-sm font-semibold text-mt-fg">
          Límites
        </h3>
        {coverage.counters_recorded ? (
          <>
            {coverage.limits_hit.length > 0 ? (
              <ul className="mt-1 flex list-disc flex-col gap-0.5 ps-5 text-sm text-mt-fg">
                {coverage.limits_hit.map((limit) => (
                  <li key={limit}>{LIMIT_LABEL[limit] ?? limit}: se alcanzó; el rastreo se detuvo ahí.</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-mt-fg">
                En este escaneo no se alcanzó ningún presupuesto configurado.
              </p>
            )}
            {Object.keys(coverage.budget).length > 0 ? (
              <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mt-muted">
                <div className="flex gap-1">
                  <dt>Profundidad de rastreo</dt>
                  <dd className="m-0 text-mt-fg">{coverage.budget.depth}</dd>
                </div>
                <div className="flex gap-1">
                  <dt>Páginas</dt>
                  <dd className="m-0 text-mt-fg">
                    {coverage.pages_crawled}/{coverage.budget.max_pages}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>Activos</dt>
                  <dd className="m-0 text-mt-fg">
                    {coverage.assets_queued}/{coverage.budget.max_assets}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>Presupuesto de bytes</dt>
                  <dd className="m-0 text-mt-fg">{formatBytes(coverage.budget.max_total_bytes)}</dd>
                </div>
                <div className="flex gap-1">
                  <dt>Tiempo</dt>
                  <dd className="m-0 text-mt-fg">{coverage.budget.max_seconds}s</dd>
                </div>
                <div className="flex gap-1">
                  <dt>Concurrencia</dt>
                  <dd className="m-0 text-mt-fg">{coverage.budget.max_concurrency}</dd>
                </div>
              </dl>
            ) : null}
            {coverage.robots_checked ? (
              <p className="mt-2 text-sm text-mt-fg">
                Se consultó robots.txt. Se omitieron {coverage.robots_omitted ?? 0} URL(s) por
                Disallow. Es cortesía: no autoriza ningún host, y una URL omitida no se pidió.
              </p>
            ) : null}
            {(coverage.sitemaps_ignored ?? 0) > 0 ? (
              <p className="mt-1 text-sm text-mt-fg">
                Se ignoraron {coverage.sitemaps_ignored} URL(s) de sitemap porque están fuera del
                alcance confirmado. Un sitemap nunca amplía lo que este escaneo puede pedir.
              </p>
            ) : null}
            {coverage.sitemaps_truncated ? (
              <p className="mt-1 text-sm text-mt-fg">
                La lectura del sitemap se detuvo en su tope. Las ubicaciones más allá no se pidieron.
              </p>
            ) : null}
          </>
        ) : (
          <>
            <p className="mt-1 text-sm text-mt-fg">
              Los contadores de descubrimiento <strong>no están registrados</strong> para este escaneo.
            </p>
            <p className="mt-1 text-sm text-mt-muted">
              Este escaneo es anterior al presupuesto de rastreo, así que el número de recursos
              descubiertos pero no intentados es desconocido, no cero. Trata los totales de arriba
              como lo procesado, no como todo lo que existe en el objetivo.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
