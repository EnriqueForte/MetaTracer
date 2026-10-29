import { FindingsTab } from "@/components/run/workspace/findings-tab";
import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";

export default async function RunFindingsPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <RunWorkspaceShell runId={runId}>
      <FindingsTab />
    </RunWorkspaceShell>
  );
}
