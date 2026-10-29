"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { fetchRun, runKey, TERMINAL, type RunSnapshot } from "@/components/run/run-model";

type WorkspaceValue = {
  runId: string;
  run: RunSnapshot | null;
  /** True once the run row was deleted from this session. */
  deleted: boolean;
  setDeleted: (value: boolean) => void;
};

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

/**
 * One `fetchRun` query for the whole run workspace.
 *
 * Every tab needs the run (status, counters, scope) and the header shows it on
 * all of them. Holding it here means TanStack issues one request per run id
 * instead of one per tab, and a deletion in the header is visible to the pages.
 */
export function WorkspaceProvider({ runId, children }: { runId: string; children: ReactNode }) {
  const [deleted, setDeleted] = useState(false);
  const query = useQuery({
    queryKey: runKey(runId),
    queryFn: () => fetchRun(runId),
    // Poll only while the run can still change; a terminal run never refetches
    // on a timer (the SSE stream is what updates it live).
    refetchInterval: (state) => {
      const status = state.state.data?.status;
      return status && TERMINAL.has(status) ? false : 2000;
    },
  });

  const value = useMemo<WorkspaceValue>(
    () => ({ runId, run: query.data ?? null, deleted, setDeleted }),
    [deleted, query.data, runId],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext);
  if (value === null) {
    throw new Error("useWorkspace must be used inside WorkspaceProvider");
  }
  return value;
}
