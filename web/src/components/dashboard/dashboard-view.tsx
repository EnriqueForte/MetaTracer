"use client";

import { Files, ScanSearch, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EvidenceTable } from "@/components/dashboard/evidence-table";
import { FindingsTypeChart } from "@/components/dashboard/findings-type-chart";
import { MetricCard } from "@/components/dashboard/metric-card";
import { SeverityOverview } from "@/components/dashboard/severity-overview";
import { TopDomains } from "@/components/dashboard/top-domains";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { apiFetch } from "@/lib/api/browser";

type Stats = {
  runs: Record<string, number>;
  assets: { total: number; with_issues: number };
  findings: {
    total: number;
    unclassified: number;
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
};

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
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
      severity_breakdown: severityCounts,
      by_type: typeCounts,
    },
    top_domains: domains,
    top_evidence: evidence,
    agent_usage: usage as Stats["agent_usage"],
  };
}

export function DashboardView() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/api/stats");
      if (!response.ok) {
        setError("Could not load the dashboard data.");
        setStats(null);
        return;
      }
      const parsed = parseStats(await response.json());
      if (!parsed) {
        setError("Could not load the dashboard data.");
        setStats(null);
        return;
      }
      setStats(parsed);
    } catch {
      setError("Network error: the API is unreachable.");
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="mt-page-title">Dashboard</h1>
          <p className="mt-meta">Security overview of every scan stored in this installation.</p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/">New scan</Link>
        </Button>
      </div>
      {loading && !stats ? <LoadingState label="Loading dashboard" /> : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {stats && stats.runs.total === 0 ? (
        <p className="text-sm text-mt-muted">
          No data yet. Run a scan to start building the dashboard — runs, findings, domains and agent usage will appear here.
        </p>
      ) : null}
      {stats && stats.runs.total > 0 ? (
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Scans"
              value={formatCount(stats.runs.total)}
              detail={`Completed ${stats.runs.completed ?? 0} · Failed ${stats.runs.failed ?? 0}`}
              icon={ScanSearch}
              accentClass="bg-mt-secondary"
            />
            <MetricCard
              label="Findings"
              value={formatCount(stats.findings.total)}
              detail={`High ${stats.findings.severity_breakdown.high ?? 0} · Unclassified ${stats.findings.unclassified}`}
              icon={ShieldAlert}
              accentClass="bg-mt-sev-high"
            />
            <MetricCard
              label="Assets"
              value={formatCount(stats.assets.total)}
              detail={`With issues ${stats.assets.with_issues}`}
              icon={Files}
              accentClass="bg-mt-chart-3"
            />
            <MetricCard
              label="AI usage"
              value={formatCount(stats.agent_usage.total_tokens)}
              detail={`${formatCount(stats.agent_usage.calls)} calls`}
              icon={Sparkles}
              accentClass="bg-mt-accent"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <SeverityOverview total={stats.findings.total} breakdown={stats.findings.severity_breakdown} />
            <FindingsTypeChart rows={typeRank} />
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
            <TopDomains rows={domainRank} />
            <EvidenceTable rows={stats.top_evidence} />
          </div>
          <section
            aria-label="Agent usage"
            className="flex flex-wrap gap-x-5 gap-y-1 border-t border-mt-border pt-3 text-xs text-mt-muted"
          >
            <p>
              Calls <span className="text-mt-fg tabular-nums">{stats.agent_usage.calls}</span>
            </p>
            <p>
              Prompt tokens <span className="text-mt-fg tabular-nums">{stats.agent_usage.prompt_tokens}</span>
            </p>
            <p>
              Completion tokens{" "}
              <span className="text-mt-fg tabular-nums">{stats.agent_usage.completion_tokens}</span>
            </p>
            <p>
              Total tokens <span className="text-mt-fg tabular-nums">{stats.agent_usage.total_tokens}</span>
            </p>
            <p>
              Latency (ms) <span className="text-mt-fg tabular-nums">{stats.agent_usage.latency_ms}</span>
            </p>
          </section>
        </div>
      ) : null}
    </div>
  );
}
