"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { isLive } from "@/components/run/run-model";
import { useWorkspace } from "@/components/run/workspace/workspace-context";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { errorMessage } from "@/lib/api/client";
import {
  correlationKindsIn,
  fetchRunGraph,
  filterCorrelationLayer,
  type GraphNode,
} from "@/lib/api/graph";
import { queryKeys } from "@/lib/query/keys";
import { safeUrl } from "@/lib/security/safe-url";

const MetricsChart = dynamic(
  () => import("@/components/run/graph/metrics-chart").then((mod) => mod.MetricsChart),
  { ssr: false },
);
const NetworkGraph = dynamic(
  () => import("@/components/run/graph/network-graph").then((mod) => mod.NetworkGraph),
  { ssr: false },
);

const KIND_LABEL: Record<string, string> = {
  page: "Página",
  asset: "Activo",
  local_root: "Raíz local",
  value: "Valor compartido",
};

const CORRELATION_LABEL: Record<string, string> = {
  email: "Correo",
  author_string: "Cadena de autor",
  gps_point: "Punto GPS",
  internal_endpoint: "Endpoint interno",
  software_version: "Versión de software",
  document_id: "Id de documento",
  device_serial: "Serie de dispositivo",
};

const LEGEND_LABEL: Record<string, string> = {
  page: "Página",
  asset: "Documento",
  local_root: "Raíz local",
  value: "Valor",
};

function GraphLegend({ keys }: { keys: string[] }) {
  return (
    <ul className="mt-graph-legend" aria-label="Leyenda del grafo">
      {keys.map((kind) => (
        <li key={kind} className="mt-graph-key">
          <span className="mt-graph-key-node" data-kind={kind} aria-hidden="true" />
          {LEGEND_LABEL[kind] ?? kind}
        </li>
      ))}
    </ul>
  );
}

export function LiveScanGraph({ runId }: { runId: string }) {
  const { run } = useWorkspace();
  const live = run ? isLive(run.status) : true;
  const query = useQuery({
    queryKey: queryKeys.graph(runId),
    queryFn: () => fetchRunGraph(runId),
    refetchInterval: live ? 2000 : false,
  });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [kindFilter, setKindFilter] = useState<string | "all">("all");
  const onSelect = useCallback((node: GraphNode | null) => setSelected(node), []);
  const correlations = query.data?.correlations;
  const correlationKinds = useMemo(
    () => (correlations ? correlationKindsIn(correlations) : []),
    [correlations],
  );
  const activeKind = correlationKinds.includes(kindFilter) ? kindFilter : "all";
  const correlationLayer = useMemo(
    () => (correlations ? filterCorrelationLayer(correlations, activeKind) : null),
    [correlations, activeKind],
  );

  if (query.isPending) {
    return <LoadingState label="Cargando grafo del escaneo" />;
  }
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error, "No se pudo cargar el grafo del escaneo")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const graph = query.data;
  const href = selected?.url ? safeUrl(selected.url) : null;
  const assetHref =
    selected?.asset_id && graph
      ? `/runs/${encodeURIComponent(graph.run_id)}/assets`
      : null;

  return (
    <section className="mt-card flex flex-col gap-4 p-4" aria-label="Grafos del escaneo">
      <div>
        <p className="mt-kicker">Conexiones observadas</p>
        <h2 className="mt-section-title">De dónde salen los documentos y qué valores se repiten</h2>
      </div>

      <div className="mt-graph-grid">
        <div className="flex min-w-0 flex-col gap-2">
          <h3 className="text-sm font-semibold text-mt-fg">Descubrimiento</h3>
          <p className="text-xs text-mt-muted">
            Rueda para zoom, arrastra el fondo, clic en un nodo para el detalle.
          </p>
          {graph.crawl.nodes.length === 0 ? (
            <EmptyState title="Aún no hay conexiones">
              El crawler aún no ha persistido un enlace página → documento.
            </EmptyState>
          ) : (
            <>
              <GraphLegend keys={["page", "asset"]} />
              <NetworkGraph
                layer={graph.crawl}
                layout="breadthfirst"
                label="Grafo de descubrimiento"
                onSelect={onSelect}
              />
            </>
          )}
          {graph.crawl.truncated ? (
            <p className="text-xs text-mt-muted">Se muestran los primeros 400 nodos / 800 aristas.</p>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <h3 className="text-sm font-semibold text-mt-fg">Valores compartidos</h3>
          <p className="text-xs text-mt-muted">
            El filtro acota por tipo. El cursor aísla un vecindario. Un valor repetido no prueba
            identidad.
          </p>
          {correlationKinds.length > 1 ? (
            <div className="flex flex-wrap gap-1" role="group" aria-label="Tipo de valor compartido">
              <Button
                variant="toggle"
                aria-pressed={activeKind === "all"}
                onClick={() => setKindFilter("all")}
              >
                Todos
              </Button>
              {correlationKinds.map((kind) => (
                <Button
                  key={kind}
                  variant="toggle"
                  aria-pressed={activeKind === kind}
                  onClick={() => setKindFilter(kind)}
                >
                  {CORRELATION_LABEL[kind] ?? kind}
                </Button>
              ))}
            </div>
          ) : null}
          {!correlationLayer || correlationLayer.nodes.length === 0 ? (
            <EmptyState title="Ningún valor compartido todavía">
              Un valor repetido no prueba identidad: es el mismo texto en más de un activo.
            </EmptyState>
          ) : (
            <>
              <GraphLegend keys={["value", "asset"]} />
              <NetworkGraph
                layer={correlationLayer}
                layout="cose"
                label="Grafo de correlación"
                onSelect={onSelect}
              />
            </>
          )}
          {graph.correlations.notice ? (
            <p className="text-xs text-mt-muted">{graph.correlations.notice}</p>
          ) : null}
          {graph.correlations.truncated ? (
            <p className="text-xs text-mt-muted">Se muestran los primeros 400 nodos / 800 aristas.</p>
          ) : null}
        </div>
      </div>

      {selected ? (
        <div className="flex flex-col gap-1 border border-mt-border bg-mt-bg p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-mt-muted">
            {KIND_LABEL[selected.kind] ?? selected.kind}
            {selected.correlation_kind
              ? ` · ${CORRELATION_LABEL[selected.correlation_kind] ?? selected.correlation_kind}`
              : ""}
          </p>
          <p className="mt-tech break-all">{selected.url ?? selected.label}</p>
          {href ? (
            <a href={href} className="text-sm font-semibold text-mt-accent-hover" rel="noreferrer">
              Abrir URL
            </a>
          ) : null}
          {assetHref ? (
            <Link href={assetHref} className="text-sm font-semibold text-mt-accent-hover">
              Ver activos de este escaneo
            </Link>
          ) : null}
        </div>
      ) : null}

      <div>
        <h3 className="text-sm font-semibold text-mt-fg">Inventario mientras corre</h3>
        <MetricsChart metrics={graph.metrics} />
      </div>
    </section>
  );
}
