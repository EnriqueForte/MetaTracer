"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiFetch, truncate } from "@/lib/api/browser";
import { safeUrl } from "@/lib/security/safe-url";

const SEVERITIES = ["critical", "high", "medium", "low", "info"] as const;
const CONFIDENCE = ["high", "medium", "low"] as const;

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
  unclassified: "Unclassified",
};

const SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"] as const;

type FeedbackRow = {
  vote: "up" | "down";
  severity_after: string;
};

const CONFIDENCE_LABEL: Record<(typeof CONFIDENCE)[number], string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

type Finding = {
  id: string;
  title: string;
  finding_type: string;
  type_label: string;
  severity: "critical" | "high" | "medium" | "low" | "info" | null;
  confidence: "high" | "medium" | "low";
  field_source: string;
  evidence_snippet: string;
  asset_source_url: string;
  asset_final_url: string;
  asset_content_type: string;
  severity_justification: string;
  impact_analysis: string;
  remediation_advice: string;
  reproduction_steps: string[];
};

function severityKey(severity: Finding["severity"]): "critical" | "high" | "medium" | "low" | "info" | "unclassified" {
  return severity ?? "unclassified";
}

function parseFindings(value: unknown): Finding[] | null {
  if (!value || typeof value !== "object") return null;
  const rows = (value as { findings?: unknown }).findings;
  if (!Array.isArray(rows)) return null;
  const findings: Finding[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const item = row as Record<string, unknown>;
    if (typeof item.id !== "string" || typeof item.title !== "string") return null;
    if (typeof item.finding_type !== "string" || typeof item.type_label !== "string") return null;
    if (typeof item.evidence_snippet !== "string" || typeof item.field_source !== "string") return null;
    if (item.confidence !== "high" && item.confidence !== "medium" && item.confidence !== "low") return null;
    if (
      item.severity !== null &&
      item.severity !== "critical" &&
      item.severity !== "high" &&
      item.severity !== "medium" &&
      item.severity !== "low" &&
      item.severity !== "info"
    ) {
      return null;
    }
    findings.push({
      id: item.id,
      title: item.title,
      finding_type: item.finding_type,
      type_label: item.type_label,
      severity: item.severity,
      confidence: item.confidence,
      field_source: item.field_source,
      evidence_snippet: item.evidence_snippet,
      asset_source_url: typeof item.asset_source_url === "string" ? item.asset_source_url : "",
      asset_final_url: typeof item.asset_final_url === "string" ? item.asset_final_url : "",
      asset_content_type: typeof item.asset_content_type === "string" ? item.asset_content_type : "",
      severity_justification: typeof item.severity_justification === "string" ? item.severity_justification : "",
      impact_analysis: typeof item.impact_analysis === "string" ? item.impact_analysis : "",
      remediation_advice: typeof item.remediation_advice === "string" ? item.remediation_advice : "",
      reproduction_steps: Array.isArray(item.reproduction_steps)
        ? item.reproduction_steps.filter((step): step is string => typeof step === "string")
        : [],
    });
  }
  return findings;
}

function AssetLink({ url }: { url: string }) {
  const href = safeUrl(url);
  if (!href) return <span className="mt-tech break-all">{url}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="mt-tech break-all underline">
      {url}
    </a>
  );
}

export function FindingsPanel({ runId, totalAssets }: { runId: string; totalAssets: number }) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Finding | null>(null);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackRow | null>(null);
  const [feedbackSeverity, setFeedbackSeverity] = useState<(typeof SEVERITY_ORDER)[number]>("info");
  const [feedbackReason, setFeedbackReason] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}/findings`);
        if (cancelled) return;
        if (!response.ok) {
          setError(`Findings unavailable (HTTP ${response.status}).`);
          setLoaded(true);
          return;
        }
        const parsed = parseFindings(await response.json());
        if (!parsed) {
          setError("Findings unavailable.");
          setLoaded(true);
          return;
        }
        setFindings(parsed);
        setError("");
        setLoaded(true);
      } catch {
        if (!cancelled) {
          setError("Network error: the API is unreachable.");
          setLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const counts = useMemo(() => {
    const tallies: Record<string, number> = {};
    for (const finding of findings) {
      const key = severityKey(finding.severity);
      tallies[key] = (tallies[key] ?? 0) + 1;
    }
    return tallies;
  }, [findings]);

  const typeOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const finding of findings) {
      if (!seen.has(finding.finding_type)) seen.set(finding.finding_type, finding.type_label);
    }
    return Array.from(seen, ([value, label]) => ({ value, label }));
  }, [findings]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return findings.filter((finding) => {
      if (severityFilter !== "all" && severityKey(finding.severity) !== severityFilter) return false;
      if (typeFilter !== "all" && finding.finding_type !== typeFilter) return false;
      if (confidenceFilter !== "all" && finding.confidence !== confidenceFilter) return false;
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
  }, [findings, severityFilter, typeFilter, confidenceFilter, query]);

  useEffect(() => {
    if (!selected) return;
    setFeedback(null);
    setFeedbackError("");
    setFeedbackReason("");
    setFeedbackSeverity(selected.severity ?? "info");
    let cancelled = false;
    void (async () => {
      try {
        const response = await apiFetch(`/api/feedback/${encodeURIComponent(selected.id)}`);
        if (cancelled || response.status !== 200) return;
        const payload: unknown = await response.json();
        if (!payload || typeof payload !== "object") return;
        const row = payload as Record<string, unknown>;
        if ((row.vote === "up" || row.vote === "down") && typeof row.severity_after === "string") {
          setFeedback({ vote: row.vote, severity_after: row.severity_after });
        }
      } catch {
        if (!cancelled) setFeedback(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  async function saveFeedback() {
    if (!selected) return;
    const after = feedbackSeverity;
    if (!after || after === selected.severity) {
      setFeedbackError("Choose a different severity to save feedback.");
      return;
    }
    const beforeIndex = selected.severity ? SEVERITY_ORDER.indexOf(selected.severity) : -1;
    const vote = SEVERITY_ORDER.indexOf(after) > beforeIndex ? "up" : "down";
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      const response = await apiFetch(`/api/feedback/${encodeURIComponent(selected.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vote,
          severity_after: after,
          reason: feedbackReason.trim() || null,
        }),
      });
      if (response.ok) {
        const payload: unknown = await response.json();
        const row = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : null;
        if (row && (row.vote === "up" || row.vote === "down") && typeof row.severity_after === "string") {
          setFeedback({ vote: row.vote, severity_after: row.severity_after });
        }
      } else {
        const payload: unknown = await response.json().catch(() => null);
        const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : null;
        setFeedbackError(typeof detail === "string" ? detail : "Feedback could not be saved");
      }
    } catch {
      setFeedbackError("Feedback could not be saved");
    } finally {
      setFeedbackBusy(false);
    }
  }

  async function removeFeedback() {
    if (!selected) return;
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      const response = await apiFetch(`/api/feedback/${encodeURIComponent(selected.id)}`, { method: "DELETE" });
      if (response.status === 204) setFeedback(null);
      else setFeedbackError("Feedback could not be removed");
    } catch {
      setFeedbackError("Feedback could not be removed");
    } finally {
      setFeedbackBusy(false);
    }
  }

  async function copyEvidence(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          aria-pressed={severityFilter === "all"}
          onClick={() => setSeverityFilter("all")}
        >
          All ({findings.length})
        </Button>
        {SEVERITIES.map((severity) => (
          <Button
            key={severity}
            variant="secondary"
            aria-pressed={severityFilter === severity}
            onClick={() => setSeverityFilter((current) => (current === severity ? "all" : severity))}
          >
            {SEVERITY_LABEL[severity]} ({counts[severity] ?? 0})
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" aria-pressed={typeFilter === "all"} onClick={() => setTypeFilter("all")}>
          All types
        </Button>
        {typeOptions.map((type) => (
          <Button
            key={type.value}
            variant="secondary"
            aria-pressed={typeFilter === type.value}
            onClick={() => setTypeFilter((current) => (current === type.value ? "all" : type.value))}
          >
            {type.label}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          aria-pressed={confidenceFilter === "all"}
          onClick={() => setConfidenceFilter("all")}
        >
          All confidence
        </Button>
        {CONFIDENCE.map((level) => (
          <Button
            key={level}
            variant="secondary"
            aria-pressed={confidenceFilter === level}
            onClick={() => setConfidenceFilter((current) => (current === level ? "all" : level))}
          >
            {CONFIDENCE_LABEL[level]}
          </Button>
        ))}
      </div>
      <label className="sr-only" htmlFor="findings-search">
        Search findings
      </label>
      <input
        id="findings-search"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search evidence, title, field or URL"
        className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint focus:border-mt-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
      />

      {error ? (
        <div role="alert" className="rounded-md border border-mt-danger-border bg-mt-danger-bg p-3">
          <p className="text-sm font-semibold text-mt-fg">Findings unavailable</p>
          <p className="text-sm text-mt-fg">{error}</p>
        </div>
      ) : null}

      {loaded && !error && findings.length === 0 ? (
        <div className="rounded-md border border-mt-border bg-mt-surface p-3">
          <p className="text-base font-semibold text-mt-fg">No findings</p>
          <p className="text-sm text-mt-muted">
            No sensitive metadata was identified in the {totalAssets} asset(s) analyzed.
          </p>
        </div>
      ) : null}

      {findings.length > 0 ? (
        <Table>
          <caption className="sr-only">Findings of this scan, in API order</caption>
          <TableHeader>
            <TableRow>
              <TableHead>Severity</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Evidence</TableHead>
              <TableHead>Asset</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((finding) => (
              <TableRow
                key={finding.id}
                tabIndex={0}
                className="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-mt-focus"
                onClick={() => setSelected(finding)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setSelected(finding);
                }}
              >
                <TableCell>
                  <Badge variant={severityKey(finding.severity)}>
                    {SEVERITY_LABEL[severityKey(finding.severity)]}
                  </Badge>
                </TableCell>
                <TableCell>{finding.type_label}</TableCell>
                <TableCell className="mt-tech">{truncate(finding.evidence_snippet, 90)}</TableCell>
                <TableCell className="mt-tech">{truncate(finding.asset_final_url, 60)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      {findings.length > 0 && filtered.length === 0 ? (
        <p className="px-4 py-6 text-center text-xs text-mt-muted">No findings match the current filters.</p>
      ) : null}

      <Sheet open={selected !== null} onOpenChange={(open) => { if (!open) setSelected(null); }}>
        <SheetContent className="w-[min(36rem,100%)] overflow-y-auto">
          {selected ? (
            <div className="flex flex-col gap-6">
              <SheetTitle>{selected.title}</SheetTitle>
              <SheetDescription className="sr-only">{selected.type_label}</SheetDescription>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={severityKey(selected.severity)}>
                  {SEVERITY_LABEL[severityKey(selected.severity)]}
                </Badge>
                <span className="text-sm text-mt-fg">{selected.type_label}</span>
                <span className="text-xs text-mt-muted">Confidence</span>
                <Badge variant="confidence">{CONFIDENCE_LABEL[selected.confidence]}</Badge>
              </div>
              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold text-mt-fg">Evidence</h3>
                <pre className="mt-evidence border border-mt-border bg-mt-bg p-3">{selected.evidence_snippet}</pre>
                <p className="text-xs font-semibold text-mt-muted">Field</p>
                <p className="mt-tech">{selected.field_source}</p>
                <p className="text-xs font-semibold text-mt-muted">Source URL</p>
                <AssetLink url={selected.asset_source_url} />
                <p className="text-xs font-semibold text-mt-muted">Final URL</p>
                <AssetLink url={selected.asset_final_url} />
                <p className="text-xs font-semibold text-mt-muted">Content type</p>
                <p className="mt-tech">{selected.asset_content_type}</p>
                <Button variant="secondary" className="self-start" onClick={() => void copyEvidence(selected.evidence_snippet)}>
                  {copied ? "Copied" : "Copy"}
                </Button>
              </section>
              <section className="flex flex-col gap-3 rounded-md border border-mt-border-strong bg-mt-surface p-3">
                <p className="text-xs font-semibold text-mt-muted">AI analysis — not evidence</p>
                {selected.severity_justification ? (
                  <div>
                    <h3 className="text-xs font-semibold text-mt-muted">Justification</h3>
                    <p className="text-sm text-mt-fg">{selected.severity_justification}</p>
                  </div>
                ) : null}
                {selected.impact_analysis ? (
                  <div>
                    <h3 className="text-xs font-semibold text-mt-muted">Impact</h3>
                    <p className="text-sm text-mt-fg">{selected.impact_analysis}</p>
                  </div>
                ) : null}
                {selected.reproduction_steps.length > 0 ? (
                  <div>
                    <h3 className="text-xs font-semibold text-mt-muted">Reproduction steps</h3>
                    <ol className="flex list-decimal flex-col gap-1 ps-5">
                      {selected.reproduction_steps.map((step, index) => (
                        <li key={index} className="text-sm text-mt-fg">
                          {step}
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                {selected.remediation_advice ? (
                  <div>
                    <h3 className="text-xs font-semibold text-mt-muted">Remediation</h3>
                    <p className="text-sm text-mt-fg">{selected.remediation_advice}</p>
                  </div>
                ) : null}
              </section>
              <div className="flex flex-col gap-2 border-t border-mt-border pt-4">
                <h3 className="text-sm font-semibold text-mt-fg">Feedback</h3>
                <p className="text-xs text-mt-muted">
                  Correct the severity if the model got it wrong. Your correction is stored locally
                  and guides future runs with similar findings.
                </p>
                {feedback ? (
                  <p className="text-xs text-mt-muted">
                    Current feedback: {feedback.vote} → {SEVERITY_LABEL[feedback.severity_after] ?? feedback.severity_after}
                  </p>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <label htmlFor="feedback-severity" className="text-xs font-semibold text-mt-muted">
                    Corrected severity
                  </label>
                  <select
                    id="feedback-severity"
                    value={feedbackSeverity}
                    onChange={(event) => {
                      const next = event.target.value;
                      if (SEVERITY_ORDER.includes(next as (typeof SEVERITY_ORDER)[number])) {
                        setFeedbackSeverity(next as (typeof SEVERITY_ORDER)[number]);
                      }
                    }}
                    className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
                  >
                    {SEVERITY_ORDER.map((severity) => (
                      <option key={severity} value={severity}>
                        {SEVERITY_LABEL[severity]}
                      </option>
                    ))}
                  </select>
                  <Button variant="secondary" disabled={feedbackBusy} onClick={() => void saveFeedback()}>
                    {feedback ? "Update feedback" : "Save feedback"}
                  </Button>
                  {feedback ? (
                    <Button variant="danger" disabled={feedbackBusy} onClick={() => void removeFeedback()}>
                      Remove
                    </Button>
                  ) : null}
                  {feedbackBusy ? <span className="text-xs text-mt-muted">Saving…</span> : null}
                  {feedbackError ? (
                    <span role="alert" className="text-xs text-mt-danger">
                      {feedbackError}
                    </span>
                  ) : null}
                </div>
                <label htmlFor="feedback-reason" className="text-xs font-semibold text-mt-muted">
                  Reason (optional)
                </label>
                <input
                  id="feedback-reason"
                  type="text"
                  value={feedbackReason}
                  onChange={(event) => setFeedbackReason(event.target.value)}
                  placeholder="Optional: why (stored locally, never sent to the model)"
                  className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint"
                />
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
