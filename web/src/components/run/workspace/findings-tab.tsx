"use client";

import { FindingsPanel } from "@/components/run/findings-panel";

import { useWorkspace } from "./workspace-context";

/**
 * Findings tab: the existing panel, fed the real asset count from the shared
 * run query (its empty state says "N asset(s) analyzed", so a hardcoded zero
 * would be a lie).
 */
export function FindingsTab() {
  const { runId, run } = useWorkspace();
  return <FindingsPanel runId={runId} totalAssets={run?.total_assets ?? 0} />;
}
