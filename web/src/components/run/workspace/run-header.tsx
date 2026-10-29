"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AbortRunButton, DeleteRunDialog } from "@/components/run/run-actions";
import { isLive, RUN_STATUS_LABEL } from "@/components/run/run-model";
import { ExportLinks } from "@/components/run/export-links";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useActor } from "@/lib/session";
import { formatWhen } from "@/lib/time";

import { InvestigationMembership } from "./investigation-membership";
import { useWorkspace } from "./workspace-context";

export const RUN_TABS = [
  { segment: "", label: "Overview", hint: "Progress and the findings on this run" },
  { segment: "assets", label: "Assets", hint: "Files this run actually fetched" },
  { segment: "metadata", label: "Metadata", hint: "Original values, with a normalized reading when one exists" },
  { segment: "findings", label: "Findings", hint: "Evidence, severity, and triage" },
  { segment: "coverage", label: "Coverage", hint: "What the crawl did not fetch" },
] as const;

export function RunSectionNav({ runId, active }: { runId: string; active: string }) {
  return (
    <nav aria-label="Run sections" className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
      {RUN_TABS.map((tab) => {
        const href = tab.segment ? `/runs/${runId}/${tab.segment}` : `/runs/${runId}`;
        const isActive = active === tab.segment;
        return (
          <Link
            key={tab.segment || "overview"}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className="mt-card flex flex-col gap-1 p-3 text-mt-muted aria-[current=page]:border-mt-accent aria-[current=page]:bg-mt-accent-soft aria-[current=page]:text-mt-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
          >
            <span className="text-sm font-semibold text-mt-fg">{tab.label}</span>
            <span className="text-xs text-mt-muted">{tab.hint}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function currentTab(pathname: string, runId: string): string {
  const base = `/runs/${runId}`;
  const rest = pathname.slice(base.length).replace(/^\//, "");
  return rest.split("/")[0] ?? "";
}

/**
 * Run header: status, counters, actions and the workspace tab strip.
 *
 * The run itself comes from the shared workspace context (one `fetchRun`
 * query), so switching tabs never refetches it.
 */
export function RunHeader() {
  const { runId, run, setDeleted } = useWorkspace();
  const actor = useActor();
  const pathname = usePathname();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const active = currentTab(pathname, runId);
  const canMutate = actor === "operator";

  if (!run) return <p className="text-sm text-mt-muted">Loading run…</p>;

  const live = isLive(run.status);
  const finished = run.status === "completed";

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-mt-border pb-3">
        <div className="min-w-0">
          <h1 className="mt-title">
            Scan of <span className="mt-tech">{run.target}</span>
          </h1>
          <p className="mt-tech text-xs text-mt-muted">{run.run_id}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-mt-muted">
            <Badge variant={run.status}>{RUN_STATUS_LABEL[run.status]}</Badge>
            <span>{run.total_assets} asset(s)</span>
            <span aria-hidden="true">·</span>
            <span>{run.total_findings} finding(s)</span>
            {run.completed_at ? (
              <>
                <span aria-hidden="true">·</span>
                <span>Completed {formatWhen(run.completed_at)}</span>
              </>
            ) : null}
          </div>
          <InvestigationMembership run={run} canMutate={canMutate} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {live && canMutate ? <AbortRunButton runId={run.run_id} /> : null}
          {!live && canMutate ? (
            <Button variant="danger" onClick={() => setConfirmDelete(true)}>
              Delete run
            </Button>
          ) : null}
        </div>
      </div>

      <RunSectionNav runId={runId} active={active} />
      {finished ? <ExportLinks runId={run.run_id} /> : null}

      <DeleteRunDialog
        runId={run.run_id}
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        onDeleted={() => setDeleted(true)}
      />
    </div>
  );
}
