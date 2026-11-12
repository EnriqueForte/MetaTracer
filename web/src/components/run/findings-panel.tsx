"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AssetFindings } from "@/components/run/findings/asset-findings";
import { BulkTriageBar, BULK_TRIAGE_LIMIT } from "@/components/run/findings/bulk-triage-bar";
import { FiltersBar } from "@/components/run/findings/filters-bar";
import { FindingDetail } from "@/components/run/findings/finding-detail";
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
import { DensitySwitch } from "@/components/ui/density-switch";
import { SplitPane } from "@/components/ui/split-pane";
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
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const searchRef = useRef<HTMLInputElement>(null);
  const canBulk = actor === "operator";
  const [desktop, setDesktop] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(min-width: 1024px)");
    const apply = () => setDesktop(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

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
      if ((selected && !desktop) || hasModifier(event) || isTypingTarget(event.target)) return;
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
      } else if (event.key === "x" && canBulk) {
        event.preventDefault();
        const index = activeIndex < 0 ? 0 : activeIndex;
        const row = filtered[index];
        if (!row) return;
        setActiveIndex(index);
        setSelectedIds((current) => {
          const next = new Set(current);
          if (next.has(row.id)) next.delete(row.id);
          else if (next.size < BULK_TRIAGE_LIMIT) next.add(row.id);
          return next;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeIndex, canBulk, desktop, filtered, selected]);

  const loaded = query.isSuccess || query.isError;
  const error = query.isError
    ? query.error instanceof ApiError
      ? query.error.status === 200
        ? "Hallazgos no disponibles."
        : `Hallazgos no disponibles (HTTP ${query.error.status}).`
      : "Error de red: la API no está accesible."
    : "";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FiltersBar
          filters={filters}
          onChange={changeFilters}
          total={base.length}
          counts={counts}
          types={types}
          dismissed={dismissed}
          searchRef={searchRef}
        />
        <DensitySwitch />
      </div>

      {error ? (
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-mt-fg">Hallazgos no disponibles</p>
          <ErrorState message={error} onRetry={() => void query.refetch()} />
        </div>
      ) : null}

      {loaded && !error && findings.length === 0 ? (
        <EmptyState title="Sin hallazgos">
          No se identificó metadato sensible en el/los {totalAssets} activo(s) analizado(s).
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

      {canBulk && selectedIds.size > 0 ? (
        <BulkTriageBar
          runId={runId}
          selectedIds={[...selectedIds]}
          onClear={() => setSelectedIds(new Set())}
        />
      ) : null}

      {filtered.length > 0 ? (
        <SplitPane
          panel={
            desktop && selected ? (
              <FindingDetail
                finding={selected}
                canMutate={actor === "operator"}
                onClose={() => setSelected(null)}
                extra={(finding) => (
                  <TriageForm
                    key={`triage:${finding.id}`}
                    runId={runId}
                    finding={finding}
                    canMutate={actor === "operator"}
                  />
                )}
              />
            ) : null
          }
          panelLabel="Detalle del hallazgo"
        >
          <FindingsTable
            rows={filtered}
            activeIndex={activeIndex}
            onActiveChange={setActiveIndex}
            onOpen={setSelected}
            selectable={canBulk}
            selectedIds={selectedIds}
            onToggle={(finding) =>
              setSelectedIds((current) => {
                const next = new Set(current);
                if (next.has(finding.id)) next.delete(finding.id);
                else if (next.size < BULK_TRIAGE_LIMIT) next.add(finding.id);
                return next;
              })
            }
            onToggleAll={() =>
              setSelectedIds((current) => {
                const visible = filtered.slice(0, BULK_TRIAGE_LIMIT);
                const allOn = visible.every((row) => current.has(row.id));
                return allOn ? new Set() : new Set(visible.map((row) => row.id));
              })
            }
            extraColumn={{
              header: "Triaje",
              cell: (finding) => {
                const status = triageOf(finding);
                if (status === "open" && finding.triage_suggestion) {
                  return (
                    <span className="text-xs text-mt-muted">
                      Sugerido: {TRIAGE_LABEL[finding.triage_suggestion.status]}
                    </span>
                  );
                }
                return status === "open" ? (
                  <span className="text-xs text-mt-muted">Abierto</span>
                ) : (
                  <Badge variant={triageVariant(status)}>{TRIAGE_LABEL[status]}</Badge>
                );
              },
            }}
          />
        </SplitPane>
      ) : null}
      {findings.length > 0 && filtered.length === 0 ? (
        <EmptyState title="Ningún hallazgo coincide con los filtros actuales">
          {dismissed > 0 && !filters.dismissed
            ? `Quita un filtro o la búsqueda, o muestra el/los ${dismissed} hallazgo(s) descartado(s).`
            : "Quita un filtro o la búsqueda para ver más hallazgos."}
        </EmptyState>
      ) : null}

      {desktop ? null : (
        <FindingSheet
          finding={selected}
          canMutate={actor === "operator"}
          onClose={() => setSelected(null)}
          extra={(finding) => (
            <TriageForm key={`triage:${finding.id}`} runId={runId} finding={finding} canMutate={actor === "operator"} />
          )}
        />
      )}
    </div>
  );
}
