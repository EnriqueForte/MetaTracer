import { MetadataExplorer } from "@/components/run/workspace/metadata-explorer";
import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";

export default async function RunMetadataPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <RunWorkspaceShell runId={runId}>
      <MetadataExplorer />
    </RunWorkspaceShell>
  );
}
