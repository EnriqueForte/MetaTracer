"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { DensitySwitch } from "@/components/ui/density-switch";
import { RawValue } from "@/components/ui/raw-value";
import { SplitPane } from "@/components/ui/split-pane";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { LayerChip } from "@/components/ui/status-chip";
import { errorMessage } from "@/lib/api/client";
import { fetchCoverage, fetchMetadata, type MetadataItemResponse } from "@/lib/api/workspace";
import { queryKeys } from "@/lib/query/keys";

import { CorrelationPanel } from "./correlation-panel";
import { useWorkspace } from "./workspace-context";

type ExplorerFilters = {
  namespace: string;
  q: string;
  asset: string;
};

const EMPTY: ExplorerFilters = { namespace: "", q: "", asset: "" };

function fromSearch(search: string): ExplorerFilters {
  const params = new URLSearchParams(search);
  return {
    namespace: params.get("namespace") ?? "",
    q: params.get("q") ?? "",
    asset: params.get("asset") ?? "",
  };
}

function toSearch(filters: ExplorerFilters, base: string): string {
  const params = new URLSearchParams(base);
  const set = (key: string, value: string) => {
    if (value) params.set(key, value);
    else params.delete(key);
  };
  set("namespace", filters.namespace);
  set("q", filters.q.trim());
  set("asset", filters.asset);
  const text = params.toString();
  return text ? `?${text}` : "";
}

function timezoneCopy(status: string | null | undefined): string | null {
  if (status === "known") return "Timezone stated";
  if (status === "assumed_utc") return "Timezone not stated; treated as UTC";
  if (status === "unzoned") return "Timezone not stated";
  if (status === "invalid") return "Date could not be read";
  return null;
}

function Summary({ item }: { item: MetadataItemResponse }) {
  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mt-section-title">Field</h2>
        <LayerChip layer="observed" />
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-mt-muted">Namespace</dt>
        <dd className="mt-tech">{item.namespace}</dd>
        <dt className="text-mt-muted">Key</dt>
        <dd className="mt-tech">{item.key}</dd>
        <dt className="text-mt-muted">Asset</dt>
        <dd className="mt-tech break-all">{item.asset_url}</dd>
      </dl>
      <p className="text-xs font-semibold text-mt-muted">Original</p>
      <RawValue value={item.value} truncated={item.truncated} />
      {item.value_normalized ? (
        <>
          <p className="text-xs font-semibold text-mt-muted">Normalized</p>
          <RawValue value={item.value_normalized} truncated={false} />
        </>
      ) : null}
      {timezoneCopy(item.timezone_status) ? (
        <p className="text-xs text-mt-muted">{timezoneCopy(item.timezone_status)}</p>
      ) : null}
      <p className="text-xs text-mt-muted">
        The asset itself is never stored or served: this is the sanitized value the
        extractor persisted.
      </p>
    </div>
  );
}

/**
 * Metadata explorer: every stored field of the run, including the ones that
 * never became a finding.
 *
 * Filters live in the URL (same convention as the findings panel), so a view is
 * shareable and survives a reload; the detail pane is persistent, so reading
 * one value does not close the list.
 */
export function MetadataExplorer() {
  const { runId } = useWorkspace();
  const [filters, setFilters] = useState<ExplorerFilters>(EMPTY);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setFilters(fromSearch(window.location.search));
    setReady(true);
  }, []);

  const coverage = useQuery({
    queryKey: [...queryKeys.run(runId), "coverage"],
    queryFn: () => fetchCoverage(runId),
  });

  const query = useQuery({
    queryKey: [...queryKeys.run(runId), "metadata", filters.namespace, filters.q, filters.asset, cursor],
    queryFn: () =>
      fetchMetadata(runId, {
        namespace: filters.namespace || undefined,
        q: filters.q || undefined,
        asset: filters.asset || undefined,
        cursor,
      }),
    enabled: ready,
    placeholderData: keepPreviousData,
  });

  const items = query.data?.items ?? [];
  const selected = items.find((item) => item.id === selectedId) ?? null;

  const namespaces = useMemo(() => {
    const counts = coverage.data?.by_namespace ?? {};
    return Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [coverage.data]);

  function change(next: Partial<ExplorerFilters>) {
    const merged = { ...filters, ...next };
    setFilters(merged);
    setCursor(null);
    setSelectedId(null);
    const { pathname, search, hash } = window.location;
    const nextSearch = toSearch(merged, search);
    if (nextSearch !== search) {
      window.history.replaceState(window.history.state, "", `${pathname}${nextSearch}${hash}`);
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA";
      if (event.key === "/" && !typing) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const loaded = query.isSuccess || query.isError;

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <CorrelationPanel runId={runId} />
      <div className="flex flex-col gap-2" role="group" aria-label="Metadata filters">
        <div className="flex flex-wrap items-center gap-1">
          <Button
            variant="toggle"
            aria-pressed={filters.namespace === ""}
            onClick={() => change({ namespace: "" })}
          >
            All namespaces
          </Button>
          {namespaces.map(([name, count]) => (
            <Button
              key={name}
              variant="toggle"
              aria-pressed={filters.namespace === name}
              onClick={() => change({ namespace: filters.namespace === name ? "" : name })}
            >
              {name} ({count})
            </Button>
          ))}
          <div className="ml-auto">
            <DensitySwitch />
          </div>
        </div>
        {filters.asset ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-mt-muted">
            <span>Asset</span>
            <span className="mt-tech break-all">{filters.asset}</span>
            <Button variant="ghost" className="py-0.5 text-xs" onClick={() => change({ asset: "" })}>
              Clear asset filter
            </Button>
          </div>
        ) : null}
        <label className="sr-only" htmlFor="metadata-search">
          Search metadata by value or field name
        </label>
        <input
          ref={searchRef}
          id="metadata-search"
          type="search"
          value={filters.q}
          onChange={(event) => change({ q: event.target.value })}
          placeholder="Search a value or a field name (press / to focus)"
          className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint focus:border-mt-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
        />
      </div>

      <p className="text-xs text-mt-muted" aria-live="polite">
        {loaded && query.data ? `${query.data.total} field(s) match` : ""}
      </p>

      {query.isError ? (
        <ErrorState message={errorMessage(query.error, "Could not load the metadata")} onRetry={() => void query.refetch()} />
      ) : null}

      {loaded && !query.isError && items.length === 0 ? (
        <EmptyState title="No metadata fields">
          {filters.q || filters.namespace
            ? "Clear a filter or the search to see more fields."
            : "This run did not persist any metadata field."}
        </EmptyState>
      ) : null}

      {items.length > 0 ? (
        <SplitPane panel={selected ? <Summary item={selected} /> : null} panelLabel="Field detail">
          <div className="overflow-x-auto">
            <table className="mt-table">
              <caption className="sr-only">Metadata fields stored for this run</caption>
              <thead>
                <tr>
                  <th scope="col">Namespace</th>
                  <th scope="col">Field</th>
                  <th scope="col">Value</th>
                  <th scope="col">Asset</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="mt-row cursor-pointer"
                    aria-selected={item.id === selectedId}
                    tabIndex={0}
                    onClick={() => setSelectedId(item.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedId(item.id);
                      }
                    }}
                  >
                    <td className="whitespace-nowrap text-mt-muted">{item.namespace}</td>
                    <td className="mt-tech whitespace-nowrap">{item.key}</td>
                    <td className="max-w-[32rem]">
                      <span className="mt-tech block truncate" title={item.value}>
                        {item.value}
                      </span>
                      {item.value_normalized ? (
                        <span className="mt-tech block truncate text-mt-muted" title={item.value_normalized}>
                          {item.value_normalized}
                        </span>
                      ) : null}
                      {item.truncated ? <span className="text-xs text-mt-muted">(truncated)</span> : null}
                    </td>
                    <td className="max-w-[18rem]">
                      <button
                        type="button"
                        className="mt-tech block truncate text-left underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
                        title={`Only ${item.asset_url}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          change({ asset: item.asset_url });
                        }}
                      >
                        {item.asset_url}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SplitPane>
      ) : null}

      {query.data?.has_more ? (
        <div className="flex justify-end">
          <Button
            variant="secondary"
            disabled={query.isFetching}
            onClick={() => setCursor(query.data?.next_cursor ?? null)}
          >
            Load more fields
          </Button>
        </div>
      ) : null}
    </div>
  );
}
