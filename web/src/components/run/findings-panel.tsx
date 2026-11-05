"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AssetFindings } from "@/components/run/findings/asset-findings";
import { FiltersBar } from "@/components/run/findings/filters-bar";
import { FindingSheet } from "@/components/run/findings/finding-sheet";
import { FindingsTable } from "@/components/run/findings/findings-table";
import { GpsMap } from "@/components/run/findings/gps-map";
import {
  applyFilters,
  dismissedCount,
  EMPTY_FILTERS,
  filtersFromSearch,
  filtersToSearch,
  severityCounts,
  TRIAGE_LABEL,
  triageOf,
  triageVisible,
  typeOptions,
  type Filters,
  type Finding,
} from "@/components/run/findings/model";
import { TriageForm, triageVariant } from "@/components/run/findings/triage-form";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { getJson, hasArray } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { FindingsResponse } from "@/lib/api/types";
import { hasModifier, isTypingTarget } from "@/lib/keyboard";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";

export const findingsKey = queryKeys.findings;

function initialFilters(): Filters {
  if (typeof window === "undefined") return EMPTY_FILTERS;
  return filtersFromSearch(window.location.search);
}

export function FindingsPanel({ runId, totalAssets }: { runId: string; totalAssets: number }) {
  const actor = useActor();
  const query = useQuery({
    queryKey: findingsKey(runId),
    queryFn: () =>
      getJson<FindingsResponse>(`/api/runs/${encodeURIComponent(runId)}/findings`, hasArray("findings")),
  });
  const findings: Finding[] = useMemo(() => query.data?.findings ?? [], [query.data]);
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Read through the query cache so a triage update shows in the open sheet.
  const selected = useMemo(
    () => (selectedId ? (findings.find((finding) => finding.id === selectedId) ?? null) : null),
    [findings, selectedId],
  );
  const setSelected = useCallback((finding: Finding | null) => setSelectedId(finding?.id ?? null), []);
  const [activeIndex, setActiveIndex] = useState(-1);
  const searchRef = useRef<HTMLInputElement>(null);

  const changeFilters = useCallback((next: Filters) => {
    setFilters(next);
    setActiveIndex(-1);
    const { pathname, search, hash } = window.location;
    const nextSearch = filtersToSearch(next, search);
    if (nextSearch !== search) {
      window.history.replaceState(window.history.state, "", `${pathname}${nextSearch}${hash}`);
    }
  }, []);

  useEffect(() => {
    const onPop = () => setFilters(filtersFromSearch(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const filtered = useMemo(() => applyFilters(findings, filters), [findings, filters]);
  const base = useMemo(() => triageVisible(findings, filters), [findings, filters]);
  const counts = useMemo(() => severityCounts(base), [base]);
  const types = useMemo(() => typeOptions(findings), [findings]);
  const dismissed = useMemo(() => dismissedCount(findings), [findings]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (selected || hasModifier(event) || isTypingTarget(event.target)) return;
      // The palette, the help or another dialog owns the keyboard while open.
      if (document.querySelector('[role="dialog"][data-state="open"]')) return;
      if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (filtered.length === 0) return;
      if (event.key === "j") {
        event.preventDefault();
        setActiveIndex((index) => Math.min(filtered.length - 1, index + 1));
      } else if (event.key === "k") {
        event.preventDefault();
        setActiveIndex((index) => Math.max(0, index - 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered.length, selected]);

  const loaded = query.isSuccess || query.isError;
  const error = query.isError
    ? query.error instanceof ApiError
      ? query.error.status === 200
        ? "Findings unavailable."
        : `Findings unavailable (HTTP ${query.error.status}).`
      : "Network error: the API is unreachable."
    : "";

  return (
    <div className="flex flex-col gap-4">
      <FiltersBar
        filters={filters}
        onChange={changeFilters}
        total={base.length}
        counts={counts}
        types={types}
        dismissed={dismissed}
        searchRef={searchRef}
      />

      {error ? (
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-mt-fg">Findings unavailable</p>
          <ErrorState message={error} onRetry={() => void query.refetch()} />
        </div>
      ) : null}

      {loaded && !error && findings.length === 0 ? (
        <EmptyState title="No findings">
          No sensitive metadata was identified in the {totalAssets} asset(s) analyzed.
        </EmptyState>
      ) : null}

      <GpsMap findings={filtered} onOpen={setSelected} />

      {filtered.length > 0 ? (
        <AssetFindings
          findings={filtered}
          activeAsset={filters.asset}
          onOpen={setSelected}
          onFilterAsset={(asset) => changeFilters({ ...filters, asset })}
        />
      ) : null}

      {filtered.length > 0 ? (
        <FindingsTable
          rows={filtered}
          activeIndex={activeIndex}
          onActiveChange={setActiveIndex}
          onOpen={setSelected}
          extraColumn={{
            header: "Triage",
            cell: (finding) => {
              const status = triageOf(finding);
              if (status === "open" && finding.triage_suggestion) {
                return (
                  <span className="text-xs text-mt-muted">
                    Suggested: {TRIAGE_LABEL[finding.triage_suggestion.status]}
                  </span>
                );
              }
              return status === "open" ? (
                <span className="text-xs text-mt-muted">Open</span>
              ) : (
                <Badge variant={triageVariant(status)}>{TRIAGE_LABEL[status]}</Badge>
              );
            },
          }}
        />
      ) : null}
      {findings.length > 0 && filtered.length === 0 ? (
        <EmptyState title="No findings match the current filters">
          {dismissed > 0 && !filters.dismissed
            ? `Clear a filter or the search, or show the ${dismissed} dismissed finding(s).`
            : "Clear a filter or the search to see more findings."}
        </EmptyState>
      ) : null}

      <FindingSheet
        finding={selected}
        canMutate={actor === "operator"}
        onClose={() => setSelected(null)}
        extra={(finding) => (
          <TriageForm key={`triage:${finding.id}`} runId={runId} finding={finding} canMutate={actor === "operator"} />
        )}
      />
    </div>
  );
}
