"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { EvidenceTable } from "@/components/dashboard/evidence-table";
import { FindingsTypeChart } from "@/components/dashboard/findings-type-chart";
import { MetricCard } from "@/components/dashboard/metric-card";
import { EstadoScene } from "@/components/dashboard/estado-scene";
import { SeverityOverview } from "@/components/dashboard/severity-overview";
import { parseTrend, SeverityTrend, type TrendPoint } from "@/components/dashboard/severity-trend";
import { TopDomains } from "@/components/dashboard/top-domains";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { apiFetch } from "@/lib/api/browser";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";

type Stats = {
  runs: Record<string, number>;
  assets: { total: number; with_issues: number };
  findings: {
    total: number;
    unclassified: number;
    dismissed: number;
    severity_breakdown: Record<string, number>;
    by_type: Record<string, number>;
  };
  top_domains: { domain: string; count: number }[];
  top_evidence: { signature: string; evidence_snippet: string; finding_type: string; occurrences: number }[];
  agent_usage: {
    calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    latency_ms: number;
  };
  trends: TrendPoint[];
};

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function formatCount(value: number): string {
  return value.toLocaleString("es-ES");
}

function parseStats(value: unknown): Stats | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const runs = row.runs;
  const assets = row.assets;
  const findings = row.findings;
  const agent = row.agent_usage;
  if (!runs || typeof runs !== "object" || !assets || typeof assets !== "object") return null;
  if (!findings || typeof findings !== "object" || !agent || typeof agent !== "object") return null;
  const runsRow = runs as Record<string, unknown>;
  const assetsRow = assets as Record<string, unknown>;
  const findingsRow = findings as Record<string, unknown>;
  const agentRow = agent as Record<string, unknown>;
  const total = num(runsRow.total);
  const findingsTotal = num(findingsRow.total);
  const unclassified = num(findingsRow.unclassified);
  const assetsTotal = num(assetsRow.total);
  const withIssues = num(assetsRow.with_issues);
  if (total === null || findingsTotal === null || unclassified === null) return null;
  if (assetsTotal === null || withIssues === null) return null;
  const usage = {
    calls: num(agentRow.calls),
    prompt_tokens: num(agentRow.prompt_tokens),
    completion_tokens: num(agentRow.completion_tokens),
    total_tokens: num(agentRow.total_tokens),
    latency_ms: num(agentRow.latency_ms),
  };
  if (Object.values(usage).some((item) => item === null)) return null;
  const breakdown = findingsRow.severity_breakdown;
  const byType = findingsRow.by_type;
  if (!breakdown || typeof breakdown !== "object" || !byType || typeof byType !== "object") return null;
  const domains: Stats["top_domains"] = [];
  if (Array.isArray(row.top_domains)) {
    for (const entry of row.top_domains) {
      if (!entry || typeof entry !== "object") continue;
      const item = entry as Record<string, unknown>;
      if (typeof item.domain === "string" && typeof item.count === "number") {
        domains.push({ domain: item.domain, count: item.count });
      }
    }
  }
  const evidence: Stats["top_evidence"] = [];
  if (Array.isArray(row.top_evidence)) {
    for (const entry of row.top_evidence) {
      if (!entry || typeof entry !== "object") continue;
      const item = entry as Record<string, unknown>;
      if (
        typeof item.signature === "string" &&
        typeof item.evidence_snippet === "string" &&
        typeof item.finding_type === "string" &&
        typeof item.occurrences === "number"
      ) {
        evidence.push({
          signature: item.signature,
          evidence_snippet: item.evidence_snippet,
          finding_type: item.finding_type,
          occurrences: item.occurrences,
        });
      }
    }
  }
  const runCounts: Record<string, number> = {};
  for (const [key, count] of Object.entries(runsRow)) {
    if (typeof count === "number") runCounts[key] = count;
  }
  const severityCounts: Record<string, number> = {};
  for (const [key, count] of Object.entries(breakdown as Record<string, unknown>)) {
    if (typeof count === "number") severityCounts[key] = count;
  }
  const typeCounts: Record<string, number> = {};
  for (const [key, count] of Object.entries(byType as Record<string, unknown>)) {
    if (typeof count === "number") typeCounts[key] = count;
  }
  return {
    runs: runCounts,
    assets: { total: assetsTotal, with_issues: withIssues },
    findings: {
      total: findingsTotal,
      unclassified,
      dismissed: num(findingsRow.dismissed) ?? 0,
      severity_breakdown: severityCounts,
      by_type: typeCounts,
    },
    top_domains: domains,
    top_evidence: evidence,
    agent_usage: usage as Stats["agent_usage"],
    trends: parseTrend(row.trends),
  };
}

async function fetchStats(): Promise<Stats> {
  const response = await apiFetch("/api/stats");
  if (!response.ok) throw new ApiError(response.status, "No se pudieron cargar los datos del panel.");
  const parsed = parseStats(await response.json());
  if (!parsed) throw new ApiError(200, "No se pudieron cargar los datos del panel.");
  return parsed;
}

function Onboarding() {
  return (
    <EmptyState title="Aún no hay escaneos">
      <p>Confirma el alcance e inicia el primero.</p>
      <Button className="mt-3 self-start" asChild>
        <Link href="/">Iniciar el primer escaneo</Link>
      </Button>
    </EmptyState>
  );
}

function NowCard({ stats }: { stats: Stats }) {
  const failed = stats.runs.failed ?? 0;
  const unclassified = stats.findings.unclassified;
  const title =
    unclassified > 0
      ? `${formatCount(unclassified)} hallazgos sin severidad`
      : failed > 0
        ? `${formatCount(failed)} escaneos fallidos`
        : "Revisar lo ya observado";
  const hint =
    unclassified > 0
      ? "Abre un escaneo completado y clasifica lo que el detector dejó sin severidad."
      : failed > 0
        ? "Un escaneo fallido no tumba los demás. Revisa el error y vuelve a lanzar."
        : "Reabre un informe o compara dos corridas del mismo alcance.";
  return (
    <section
      className="mt-card flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between"
      aria-label="Ahora"
    >
      <div className="min-w-0">
        <p className="mt-kicker">Ahora</p>
        <h2 id="now-title" className="mt-section-title text-base">
          {title}
        </h2>
        <p className="mt-meta mt-1">{hint}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" asChild>
          <Link href="/runs?status=completed">Abrir escaneos completados</Link>
        </Button>
        {failed > 0 ? (
          <Button variant="secondary" asChild>
            <Link href="/runs?status=failed">Revisar escaneos fallidos</Link>
          </Button>
        ) : null}
        <Button variant="ghost" asChild>
          <Link href="/runs/compare">Abrir comparación</Link>
        </Button>
      </div>
    </section>
  );
}

export function DashboardView() {
  const query = useQuery({ queryKey: queryKeys.stats, queryFn: fetchStats });
  const stats = query.data ?? null;
  const loading = query.isPending;
  const error = query.isError
    ? query.error instanceof ApiError
      ? "No se pudieron cargar los datos del panel."
      : "Error de red: la API no está accesible."
    : "";
  const load = () => query.refetch();

  const typeRank = stats
    ? Object.entries(stats.findings.by_type)
        .filter((entry): entry is [string, number] => entry[1] > 0)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    : [];
  const domainRank = stats
    ? [...stats.top_domains].sort((a, b) => b.count - a.count || a.domain.localeCompare(b.domain))
    : [];

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <header className="relative flex flex-col items-center border-b border-mt-border pb-3">
        {stats && stats.runs.total > 0 ? (
          <div className="sm:absolute sm:right-0 sm:top-0">
            <Button asChild>
              <Link href="/">Nuevo escaneo</Link>
            </Button>
          </div>
        ) : null}
        <div className="mt-estado-lockup">
          <EstadoScene />
          <h1 className="mt-page-title mt-estado-title">
            <span className="mt-estado-title-text">Panel de Estado</span>
          </h1>
        </div>
      </header>
      {loading && !stats ? <LoadingState label="Cargando el panel" variant="page" /> : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {stats && stats.runs.total === 0 ? <Onboarding /> : null}
      {stats && stats.runs.total > 0 ? (
        <div className="flex flex-col gap-6">
          <NowCard stats={stats} />
          <section className="mt-section" aria-label="Inventario">
            <p className="mt-kicker">Inventario</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Escaneos"
                value={formatCount(stats.runs.total)}
                detail={`Completados ${stats.runs.completed ?? 0} · Fallidos ${stats.runs.failed ?? 0}`}
                href="/runs"
              />
              <MetricCard
                label="Hallazgos"
                value={formatCount(stats.findings.total)}
                detail={`Alta ${stats.findings.severity_breakdown.high ?? 0} · Sin clasificar ${stats.findings.unclassified} · Descartados ${stats.findings.dismissed}`}
                href="/runs?status=completed"
              />
              <MetricCard
                label="Activos"
                value={formatCount(stats.assets.total)}
                detail={`Con incidencias ${stats.assets.with_issues}`}
              />
              <MetricCard
                label="Uso de IA"
                value={formatCount(stats.agent_usage.total_tokens)}
                detail={`${formatCount(stats.agent_usage.calls)} llamadas`}
              />
            </div>
          </section>
          <section className="mt-section" aria-label="Composición">
            <p className="mt-kicker">Composición</p>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <SeverityOverview total={stats.findings.total} breakdown={stats.findings.severity_breakdown} />
              <FindingsTypeChart rows={typeRank} />
            </div>
          </section>
          {stats.trends.length > 0 ? (
            <section className="mt-section" aria-label="Tendencia">
              <p className="mt-kicker">Tendencia</p>
              <SeverityTrend points={stats.trends} />
            </section>
          ) : null}
          <section className="mt-section" aria-label="Qué se repite">
            <p className="mt-kicker">Qué se repite</p>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
              <TopDomains rows={domainRank} />
              <EvidenceTable rows={stats.top_evidence} />
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
