"use client";

import type { ReactNode } from "react";

import { useWorkspace, WorkspaceProvider } from "@/components/run/workspace/workspace-context";
import { RunHeader } from "@/components/run/workspace/run-header";

function DeletedNotice() {
  const { deleted } = useWorkspace();
  if (!deleted) return null;
  return (
    <div role="status" className="rounded-md border border-mt-border bg-mt-surface p-3">
      <p className="text-sm text-mt-fg">Este escaneo se eliminó.</p>
      <a href="/runs" className="text-sm font-semibold text-mt-accent-hover underline">
        Volver al historial
      </a>
    </div>
  );
}

/** Client shell of the run workspace: one run query, one header, one tab strip. */
export function RunWorkspaceShell({ runId, children }: { runId: string; children: ReactNode }) {
  return (
    <WorkspaceProvider runId={runId}>
      <div className="flex min-w-0 flex-col gap-4">
        <RunHeader />
        <DeletedNotice />
        {children}
      </div>
    </WorkspaceProvider>
  );
}
