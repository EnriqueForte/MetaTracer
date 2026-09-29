"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/browser";

const SEVERITIES = ["critical", "high", "medium", "low", "info", "unclassified"] as const;
const TYPE_LABELS: Record<string, string> = {
  gps: "GPS",
  email: "Email",
  internal_path: "Internal path",
  software_version: "Software version",
  debug_comment: "Debug comment",
};
const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
  unclassified: "Unclassified",
};

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

  const maxSeverity = stats
    ? Math.max(1, ...SEVERITIES.map((key) => stats.findings.severity_breakdown[key] ?? 0))
    : 1;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="mt-title">Dashboard</h1>
          <p className="text-sm text-mt-fg">Aggregated view of every scan stored in this installation.</p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/">New scan</Link>
        </Button>
      </div>
      {loading && !stats ? (
        <p className="flex items-center gap-2 text-sm text-mt-muted">
          <span className="mt-spin" aria-hidden="true" /> Loading dashboard…
        </p>
      ) : null}
      {error ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-mt-danger-border bg-mt-danger-bg p-3 text-sm">
          <p>{error}</p>
          <Button variant="secondary" onClick={() => void load()}>Retry</Button>
        </div>
      ) : null}
      {stats && stats.runs.total === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-md border border-mt-border bg-mt-surface p-6 text-center">
          <p className="text-base font-semibold">No data yet</p>
          <p className="text-sm text-mt-muted">
            Run a scan to start building the dashboard — runs, findings, domains and agent usage will appear here.
          </p>
          <Button variant="secondary" asChild>
            <Link href="/">New scan</Link>
          </Button>
        </div>
      ) : null}
      {stats && stats.runs.total > 0 ? (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-4 rounded-md border border-mt-border bg-mt-surface p-4 lg:grid-cols-4">
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Runs</p>
              <p className="text-2xl text-mt-fg">{stats.runs.total}</p>
              <p className="text-xs text-mt-muted">
                Completed {stats.runs.completed ?? 0} · Failed {stats.runs.failed ?? 0}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Findings</p>
              <p className="text-2xl text-mt-fg">{stats.findings.total}</p>
              <p className="text-xs text-mt-muted">Unclassified {stats.findings.unclassified}</p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Assets</p>
              <p className="text-2xl text-mt-fg">{stats.assets.total}</p>
              <p className="text-xs text-mt-muted">With issues {stats.assets.with_issues}</p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Total tokens</p>
              <p className="text-2xl text-mt-fg">{stats.agent_usage.total_tokens}</p>
              <p className="text-xs text-mt-muted">{stats.agent_usage.calls} calls</p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-md border border-mt-border bg-mt-surface p-4">
              <h2 className="mb-4 text-xs font-semibold tracking-wide text-mt-muted uppercase">Severity</h2>
              <div className="flex flex-col gap-3">
                {SEVERITIES.map((severity) => {
                  const count = stats.findings.severity_breakdown[severity] ?? 0;
                  return (
                    <div key={severity} className="flex flex-col gap-1">
                      <div className="flex justify-between text-xs text-mt-muted">
                        <span>{SEVERITY_LABEL[severity]}</span>
                        <span>{count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-sm bg-mt-border">
                        <div
                          className="h-2 bg-mt-accent"
                          style={{ width: `${(count / maxSeverity) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="rounded-md border border-mt-border bg-mt-surface p-4">
              <h2 className="mb-4 text-xs font-semibold tracking-wide text-mt-muted uppercase">Findings by type</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.findings.by_type).map(([type, count]) => (
                  <span key={type} className="rounded-sm border border-mt-border-strong px-1.5 py-0.5 text-[11px] font-semibold">
                    {TYPE_LABELS[type] ?? type} {count}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div>
            <h2 className="mb-3 text-xs font-semibold tracking-wide text-mt-muted uppercase">Top domains</h2>
            {stats.top_domains.length === 0 ? (
              <p className="text-xs text-mt-muted">No scopes or assets scanned yet.</p>
            ) : (
              <table className="w-full text-sm">
                <caption className="sr-only">Top domains by asset mentions</caption>
                <thead>
                  <tr className="text-left text-xs text-mt-muted uppercase">
                    <th>Domain</th>
                    <th className="text-right">Mentions</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.top_domains.map((entry) => (
                    <tr key={entry.domain} className="border-t border-mt-border">
                      <td className="mt-tech py-2">{entry.domain}</td>
                      <td className="py-2 text-right">{entry.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div>
            <h2 className="mb-3 text-xs font-semibold tracking-wide text-mt-muted uppercase">Most repeated evidence</h2>
            {stats.top_evidence.length === 0 ? (
              <p className="text-xs text-mt-muted">No findings yet.</p>
            ) : (
              <table className="w-full text-sm">
                <caption className="sr-only">Most repeated evidence snippets</caption>
                <thead>
                  <tr className="text-left text-xs text-mt-muted uppercase">
                    <th>Evidence</th>
                    <th>Type</th>
                    <th className="text-right">Occurrences</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.top_evidence.map((entry) => (
                    <tr key={entry.signature} className="border-t border-mt-border">
                      <td className="mt-tech py-2">{entry.evidence_snippet.slice(0, 90)}</td>
                      <td className="py-2">{TYPE_LABELS[entry.finding_type] ?? entry.finding_type}</td>
                      <td className="py-2 text-right">{entry.occurrences}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4 rounded-md border border-mt-border bg-mt-surface p-4 lg:grid-cols-5">
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Calls</p>
              <p className="text-2xl">{stats.agent_usage.calls}</p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Prompt tokens</p>
              <p className="text-2xl">{stats.agent_usage.prompt_tokens}</p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Completion tokens</p>
              <p className="text-2xl">{stats.agent_usage.completion_tokens}</p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Total tokens</p>
              <p className="text-2xl">{stats.agent_usage.total_tokens}</p>
            </div>
            <div>
              <p className="text-xs font-semibold tracking-wide text-mt-muted uppercase">Latency (ms)</p>
              <p className="text-2xl">{stats.agent_usage.latency_ms}</p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
