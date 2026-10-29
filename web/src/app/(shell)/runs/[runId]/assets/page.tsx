import { AssetsView } from "@/components/run/workspace/assets-view";
import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";

export default async function RunAssetsPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <RunWorkspaceShell runId={runId}>
      <AssetsView />
    </RunWorkspaceShell>
  );
}
