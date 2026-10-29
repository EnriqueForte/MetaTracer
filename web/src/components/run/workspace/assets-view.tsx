"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DensitySwitch } from "@/components/ui/density-switch";
import { LayerChip, StatusChip } from "@/components/ui/status-chip";
import { Button } from "@/components/ui/button";
import { SplitPane } from "@/components/ui/split-pane";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { errorMessage } from "@/lib/api/client";
import {
  EXTRACTION_LABEL,
  SKIP_REASON_LABEL,
  fetchAssets,
  fetchMetadata,
  formatBytes,
  shortType,
  type AssetResponse,
} from "@/lib/api/workspace";
import { queryKeys } from "@/lib/query/keys";
import { formatWhen } from "@/lib/time";

import { useWorkspace } from "./workspace-context";

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "ok", label: "Extracted" },
  { value: "skipped", label: "Skipped" },
  { value: "failed", label: "Failed" },
] as const;

type StatusFilter = (typeof STATUS_FILTERS)[number]["value"];

function toneOf(status: string): "ok" | "skipped" | "failed" {
  if (status === "ok") return "ok";
  if (status === "failed") return "failed";
  return "skipped";
}

function AssetDetail({ asset }: { asset: AssetResponse }) {
  const { runId } = useWorkspace();
  const metadata = useQuery({
    queryKey: [...queryKeys.run(runId), "asset-metadata", asset.id],
    queryFn: () => fetchMetadata(runId, { limit: 50 }, asset.id),
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-col gap-1">
        <h2 className="mt-section-title">Asset</h2>
        <p className="mt-tech break-all">{asset.source_url}</p>
        {asset.final_url !== asset.source_url ? (
          <p className="mt-tech text-xs text-mt-muted">Final: {asset.final_url}</p>
        ) : null}
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-mt-muted">Status</dt>
        <dd>
          <StatusChip tone={toneOf(asset.extraction_status)} label={EXTRACTION_LABEL[asset.extraction_status] ?? asset.extraction_status} />
        </dd>
        <dt className="text-mt-muted">Type</dt>
        <dd className="mt-tech">{asset.content_type || "unknown"}</dd>
        <dt className="text-mt-muted">Size</dt>
        <dd className="tabular-nums">{formatBytes(asset.file_size_bytes)}</dd>
        <dt className="text-mt-muted">Fields</dt>
        <dd className="tabular-nums">{asset.metadata_fields}</dd>
        <dt className="text-mt-muted">Findings</dt>
        <dd className="tabular-nums">{asset.findings}</dd>
        <dt className="text-mt-muted">Discovered</dt>
        <dd className="mt-tech text-xs">{formatWhen(asset.discovered_at)}</dd>
        <dt className="text-mt-muted">SHA-256</dt>
        <dd className="mt-tech text-xs break-all" title={asset.file_hash_sha256}>
          {asset.file_hash_sha256 || "—"}
        </dd>
      </dl>

      {asset.skip_reason || asset.error_message ? (
        <div className="rounded-md border border-mt-warning-border bg-mt-warning-bg p-2">
          <p className="text-xs font-semibold text-mt-fg">
            {asset.skip_reason ? SKIP_REASON_LABEL[asset.skip_reason] ?? asset.skip_reason : "Extraction failed"}
          </p>
          {asset.error_message ? <p className="mt-tech text-xs">{asset.error_message}</p> : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-2 border-t border-mt-border pt-3">
        <div className="flex items-center gap-2">
          <h3 className="mt-section-title">Metadata</h3>
          <LayerChip layer="observed" />
        </div>
        {metadata.isPending ? <p className="text-sm text-mt-muted">Loading fields…</p> : null}
        {metadata.isError ? (
          <ErrorState message={errorMessage(metadata.error, "Could not load this asset's metadata")} onRetry={() => void metadata.refetch()} />
        ) : null}
        {metadata.data && metadata.data.items.length === 0 ? (
          <p className="text-sm text-mt-muted">No metadata fields were extracted from this asset.</p>
        ) : null}
        {metadata.data && metadata.data.items.length > 0 ? (
          <table className="mt-table">
            <caption className="sr-only">Metadata fields of this asset</caption>
            <thead>
              <tr>
                <th scope="col">Namespace</th>
                <th scope="col">Field</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {metadata.data.items.map((item) => (
                <tr key={item.id} className="mt-row">
                  <td className="text-mt-muted">{item.namespace}</td>
                  <td className="mt-tech">{item.key}</td>
                  <td className="mt-tech break-all">
                    {item.value}
                    {item.truncated ? <span className="ml-1 text-xs text-mt-muted">(truncated)</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {metadata.data && metadata.data.total > metadata.data.items.length ? (
          <p className="text-xs text-mt-muted">
            Showing {metadata.data.items.length} of {metadata.data.total} fields.
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Asset inventory: every asset of the run, not only the broken ones.
 *
 * Before Fase 1 the UI only ever showed `asset_issues`, i.e. the failed and
 * skipped rows; the successful extractions were invisible.
 */
export function AssetsView() {
  const { runId } = useWorkspace();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [cursor, setCursor] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const query = useQuery({
    queryKey: [...queryKeys.run(runId), "assets", status, cursor],
    queryFn: () =>
      fetchAssets(runId, {
        status: status === "all" ? undefined : status,
        cursor,
      }),
    placeholderData: keepPreviousData,
  });

  const assets = query.data?.assets ?? [];
  const selected = assets.find((asset) => asset.id === selectedId) ?? null;
  const loaded = query.isSuccess || query.isError;

  function changeStatus(next: StatusFilter) {
    setStatus(next);
    setCursor(null);
    setSelectedId(null);
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by extraction status">
          {STATUS_FILTERS.map((filter) => (
            <Button
              key={filter.value}
              variant="toggle"
              aria-pressed={status === filter.value}
              onClick={() => changeStatus(filter.value)}
            >
              {filter.label}
            </Button>
          ))}
        </div>
        <DensitySwitch />
      </div>

      <p className="text-xs text-mt-muted" aria-live="polite">
        {loaded && query.data ? `${query.data.total} asset(s) in this run` : ""}
      </p>

      {query.isError ? (
        <ErrorState message={errorMessage(query.error, "Could not load the asset inventory")} onRetry={() => void query.refetch()} />
      ) : null}

      {loaded && !query.isError && assets.length === 0 ? (
        <EmptyState title="No assets">
          This run did not record any asset with the current filter.
        </EmptyState>
      ) : null}

      {assets.length > 0 ? (
        <SplitPane
          panel={selected ? <AssetDetail asset={selected} /> : null}
          panelLabel="Asset detail"
        >
          <div className="overflow-x-auto">
            <table className="mt-table">
              <caption className="sr-only">Assets discovered in this run</caption>
              <thead>
                <tr>
                  <th scope="col">Asset</th>
                  <th scope="col">Type</th>
                  <th scope="col">Status</th>
                  <th scope="col" className="text-right">Fields</th>
                  <th scope="col" className="text-right">Findings</th>
                  <th scope="col" className="text-right">Size</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr
                    key={asset.id}
                    className="mt-row cursor-pointer"
                    aria-selected={asset.id === selectedId}
                    tabIndex={0}
                    onClick={() => setSelectedId(asset.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedId(asset.id);
                      }
                    }}
                  >
                    <td className="max-w-[28rem]">
                      <span className="mt-tech block truncate" title={asset.source_url}>
                        {asset.source_url}
                      </span>
                      {asset.skip_reason ? (
                        <span className="text-xs text-mt-muted">
                          {SKIP_REASON_LABEL[asset.skip_reason] ?? asset.skip_reason}
                        </span>
                      ) : null}
                    </td>
                    <td className="text-mt-muted">{shortType(asset.content_type)}</td>
                    <td>
                      <StatusChip
                        tone={toneOf(asset.extraction_status)}
                        label={EXTRACTION_LABEL[asset.extraction_status] ?? asset.extraction_status}
                      />
                    </td>
                    <td className="text-right tabular-nums">{asset.metadata_fields}</td>
                    <td className="text-right tabular-nums">{asset.findings}</td>
                    <td className="text-right tabular-nums text-mt-muted">{formatBytes(asset.file_size_bytes)}</td>
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
            Load more assets
          </Button>
        </div>
      ) : null}
    </div>
  );
}
