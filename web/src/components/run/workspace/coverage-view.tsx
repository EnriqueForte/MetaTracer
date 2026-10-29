"use client";

import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/ui/states";
import { StatusChip } from "@/components/ui/status-chip";
import { errorMessage } from "@/lib/api/client";
import { SKIP_REASON_LABEL, fetchCoverage, formatBytes } from "@/lib/api/workspace";
import { queryKeys } from "@/lib/query/keys";

import { useWorkspace } from "./workspace-context";

/** Human label for a limit identifier; the wire value stays lowercase snake_case. */
const LIMIT_LABEL: Record<string, string> = {
  max_depth: "Crawl depth limit",
  max_pages: "Page limit",
  max_assets: "Asset limit",
  max_total_bytes: "Byte limit",
  max_seconds: "Time limit",
};

function Figure({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex flex-col gap-0.5 border border-mt-border bg-mt-bg p-3">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-mt-muted">{label}</dt>
      <dd className="m-0 text-xl font-semibold tabular-nums text-mt-fg">{value}</dd>
      {detail ? <dd className="m-0 text-xs text-mt-muted">{detail}</dd> : null}
    </div>
  );
}

/**
 * Coverage: what the run actually collected.
 *
 * The section exists to make one limitation explicit instead of implying
 * completeness: the crawl budget is not persisted yet (Fase 2), so the number
 * of discovered-but-not-attempted resources is *unknown*, not zero. Saying
 * "0 omitted" would be a lie; the panel says "not recorded".
 */
export function CoverageView() {
  const { runId } = useWorkspace();
  const query = useQuery({
    queryKey: [...queryKeys.run(runId), "coverage"],
    queryFn: () => fetchCoverage(runId),
  });

  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error, "Could not load the coverage summary")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (query.isPending || !query.data) {
    return <p className="text-sm text-mt-muted">Loading coverage…</p>;
  }

  const coverage = query.data;
  const skipReasons = Object.entries(coverage.by_skip_reason).sort((a, b) => b[1] - a[1]);
  const namespaces = Object.entries(coverage.by_namespace).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h2 className="mt-section-title">Coverage of this run</h2>
        <p className="mt-meta">
          What the pipeline stored. This is not a measure of exposure: absence of findings is not
          absence of metadata.
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        <Figure label="Assets recorded" value={String(coverage.total_assets)} />
        <Figure label="Extracted" value={String(coverage.ok)} detail="Metadata read" />
        <Figure label="Skipped" value={String(coverage.skipped)} detail="See reasons below" />
        <Figure label="Failed" value={String(coverage.failed)} detail="Parser or transport" />
        <Figure label="Bytes" value={formatBytes(coverage.bytes_downloaded)} detail="Bodies downloaded" />
      </dl>

      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Figure
          label="Metadata fields"
          value={String(coverage.metadata_fields)}
          detail="Stored as structured text, never as bytes"
        />
        <Figure label="Findings" value={String(coverage.findings)} detail="Subset of fields that matched a detector" />
      </dl>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="mt-card flex flex-col gap-2 p-4" aria-labelledby="coverage-skip-title">
          <h3 id="coverage-skip-title" className="mt-section-title">
            Why assets were skipped
          </h3>
          {skipReasons.length === 0 ? (
            <p className="text-sm text-mt-muted">No asset was skipped in this run.</p>
          ) : (
            <dl className="flex flex-col gap-1 text-sm">
              {skipReasons.map(([reason, count]) => (
                <div key={reason} className="flex items-center justify-between gap-2">
                  <dt>
                    <StatusChip tone="skipped" label={SKIP_REASON_LABEL[reason] ?? reason} />
                  </dt>
                  <dd className="m-0 tabular-nums text-mt-fg">{count}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section className="mt-card flex flex-col gap-2 p-4" aria-labelledby="coverage-namespace-title">
          <h3 id="coverage-namespace-title" className="mt-section-title">
            Fields by namespace
          </h3>
          {namespaces.length === 0 ? (
            <p className="text-sm text-mt-muted">No metadata field was stored.</p>
          ) : (
            <dl className="flex flex-col gap-1 text-sm">
              {namespaces.map(([namespace, count]) => (
                <div key={namespace} className="flex items-center justify-between gap-2">
                  <dt className="mt-tech">{namespace}</dt>
                  <dd className="m-0 tabular-nums text-mt-fg">{count}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      </div>

      <section
        className="rounded-md border border-mt-warning-border bg-mt-warning-bg p-3"
        aria-labelledby="coverage-limits-title"
      >
        <h3 id="coverage-limits-title" className="text-sm font-semibold text-mt-fg">
          Limits
        </h3>
        {coverage.counters_recorded ? (
          <>
            {coverage.limits_hit.length > 0 ? (
              <ul className="mt-1 flex list-disc flex-col gap-0.5 ps-5 text-sm text-mt-fg">
                {coverage.limits_hit.map((limit) => (
                  <li key={limit}>{LIMIT_LABEL[limit] ?? limit} was reached; the crawl stopped there.</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-mt-fg">
                No configured budget was reached in this run.
              </p>
            )}
            {Object.keys(coverage.budget).length > 0 ? (
              <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mt-muted">
                <div className="flex gap-1">
                  <dt>Crawl depth</dt>
                  <dd className="m-0 text-mt-fg">{coverage.budget.depth}</dd>
                </div>
                <div className="flex gap-1">
                  <dt>Pages</dt>
                  <dd className="m-0 text-mt-fg">
                    {coverage.pages_crawled}/{coverage.budget.max_pages}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>Assets</dt>
                  <dd className="m-0 text-mt-fg">
                    {coverage.assets_queued}/{coverage.budget.max_assets}
                  </dd>
                </div>
                <div className="flex gap-1">
                  <dt>Byte budget</dt>
                  <dd className="m-0 text-mt-fg">{formatBytes(coverage.budget.max_total_bytes)}</dd>
                </div>
                <div className="flex gap-1">
                  <dt>Time</dt>
                  <dd className="m-0 text-mt-fg">{coverage.budget.max_seconds}s</dd>
                </div>
                <div className="flex gap-1">
                  <dt>Concurrency</dt>
                  <dd className="m-0 text-mt-fg">{coverage.budget.max_concurrency}</dd>
                </div>
              </dl>
            ) : null}
            {coverage.robots_checked ? (
              <p className="mt-2 text-sm text-mt-fg">
                robots.txt was consulted. {coverage.robots_omitted ?? 0} URL(s) were omitted by
                Disallow. That is courtesy: it does not authorize any host, and an omitted URL was
                not requested.
              </p>
            ) : null}
            {(coverage.sitemaps_ignored ?? 0) > 0 ? (
              <p className="mt-1 text-sm text-mt-fg">
                {coverage.sitemaps_ignored} sitemap URL(s) were ignored because they are outside the
                confirmed scope. A sitemap never widens what this run may request.
              </p>
            ) : null}
            {coverage.sitemaps_truncated ? (
              <p className="mt-1 text-sm text-mt-fg">
                Sitemap reading stopped at its cap. Locations past the cap were not requested.
              </p>
            ) : null}
          </>
        ) : (
          <>
            <p className="mt-1 text-sm text-mt-fg">
              Discovery counters are <strong>not recorded</strong> for this run.
            </p>
            <p className="mt-1 text-sm text-mt-muted">
              This run predates the crawl budget, so the number of resources discovered but not
              attempted is unknown, not zero. Treat the totals above as what was processed, not as
              the whole of what exists on the target.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
