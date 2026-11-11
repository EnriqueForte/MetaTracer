import type { Confidence, FindingResponse, Severity, SeverityKey, TriageStatus } from "@/lib/api/types";
import { severityKey } from "@/lib/api/types";
import { CONFIDENCE_LABEL, SEVERITY_LABEL, TRIAGE_LABEL } from "@/lib/ui-copy";

export { CONFIDENCE_LABEL, SEVERITY_LABEL, TRIAGE_LABEL };

export type Finding = FindingResponse;

export const SEVERITY_FILTERS = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
  "unclassified",
] as const satisfies readonly SeverityKey[];

export const CONFIDENCE_LEVELS = ["high", "medium", "low"] as const satisfies readonly Confidence[];

/** Ascending order, used to decide the feedback vote direction. */
export const SEVERITY_ASCENDING = ["info", "low", "medium", "high", "critical"] as const satisfies readonly Severity[];

export const TRIAGE_STATUSES = ["open", "confirmed", "fixed", "false_positive"] as const satisfies readonly TriageStatus[];

export type Filters = {
  severity: SeverityKey | "all";
  type: string;
  confidence: Confidence | "all";
  q: string;
  asset: string;
  /** "any" keeps every status except false_positive unless `dismissed` is on. */
  triage: TriageStatus | "any";
  dismissed: boolean;
};

export const EMPTY_FILTERS: Filters = {
  severity: "all",
  type: "all",
  confidence: "all",
  q: "",
  asset: "",
  triage: "any",
  dismissed: false,
};

export function triageOf(finding: Finding): TriageStatus {
  return finding.triage_status ?? "open";
}

function isTriage(value: string): value is TriageStatus {
  return (TRIAGE_STATUSES as readonly string[]).includes(value);
}

function isSeverityFilter(value: string): value is SeverityKey {
  return (SEVERITY_FILTERS as readonly string[]).includes(value);
}

function isConfidence(value: string): value is Confidence {
  return (CONFIDENCE_LEVELS as readonly string[]).includes(value);
}

/** Read filters from `?severity=&type=&confidence=&q=&asset=`. Unknown values fall back to "all". */
export function filtersFromSearch(search: string): Filters {
  const params = new URLSearchParams(search);
  const severity = params.get("severity") ?? "";
  const confidence = params.get("confidence") ?? "";
  const triage = params.get("triage") ?? "";
  return {
    severity: isSeverityFilter(severity) ? severity : "all",
    type: params.get("type") || "all",
    confidence: isConfidence(confidence) ? confidence : "all",
    q: params.get("q") ?? "",
    asset: params.get("asset") ?? "",
    triage: isTriage(triage) ? triage : "any",
    dismissed: params.get("dismissed") === "1",
  };
}

/** Write filters into an existing query string, keeping unrelated params. */
export function filtersToSearch(filters: Filters, base: string): string {
  const params = new URLSearchParams(base);
  const set = (key: string, value: string, empty: string) => {
    if (value && value !== empty) params.set(key, value);
    else params.delete(key);
  };
  set("severity", filters.severity, "all");
  set("type", filters.type, "all");
  set("confidence", filters.confidence, "all");
  set("q", filters.q.trim(), "");
  set("asset", filters.asset, "");
  set("triage", filters.triage, "any");
  set("dismissed", filters.dismissed ? "1" : "", "");
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function assetOf(finding: Finding): string {
  return finding.asset_final_url || finding.asset_source_url;
}

/** Triage gate only: the base the severity chips count from. */
export function triageVisible(findings: Finding[], filters: Filters): Finding[] {
  return findings.filter((finding) => {
    const status = triageOf(finding);
    if (filters.triage !== "any") return status === filters.triage;
    return filters.dismissed || status !== "false_positive";
  });
}

export function dismissedCount(findings: Finding[]): number {
  return findings.filter((finding) => triageOf(finding) === "false_positive").length;
}

export function applyFilters(findings: Finding[], filters: Filters): Finding[] {
  const needle = filters.q.trim().toLowerCase();
  return triageVisible(findings, filters).filter((finding) => {
    if (filters.severity !== "all" && severityKey(finding.severity) !== filters.severity) return false;
    if (filters.type !== "all" && finding.finding_type !== filters.type) return false;
    if (filters.confidence !== "all" && finding.confidence !== filters.confidence) return false;
    if (filters.asset && assetOf(finding) !== filters.asset) return false;
    if (!needle) return true;
    const blob = [
      finding.title,
      finding.evidence_snippet,
      finding.field_source,
      finding.asset_source_url,
      finding.asset_final_url,
      finding.type_label,
    ]
      .join(" ")
      .toLowerCase();
    return blob.includes(needle);
  });
}

export function severityCounts(findings: Finding[]): Record<SeverityKey, number> {
  const counts: Record<SeverityKey, number> = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
    unclassified: 0,
  };
  for (const finding of findings) counts[severityKey(finding.severity)] += 1;
  return counts;
}

export function typeOptions(findings: Finding[]): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const finding of findings) {
    if (!seen.has(finding.finding_type)) seen.set(finding.finding_type, finding.type_label);
  }
  return Array.from(seen, ([value, label]) => ({ value, label }));
}

/** Group by asset in first-appearance order (the API order), not by size. */
export function groupByAsset(findings: Finding[]): [string, Finding[]][] {
  const groups = new Map<string, Finding[]>();
  for (const finding of findings) {
    const key = assetOf(finding);
    if (!key) continue;
    const list = groups.get(key);
    if (list) list.push(finding);
    else groups.set(key, [finding]);
  }
  return [...groups.entries()];
}
