import { CoverageView } from "@/components/run/workspace/coverage-view";
import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";

export default async function RunCoveragePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <RunWorkspaceShell runId={runId}>
      <CoverageView />
    </RunWorkspaceShell>
  );
}
