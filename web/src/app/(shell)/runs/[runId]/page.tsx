import { RunProgress } from "@/components/run/run-progress";
import { RunWorkspaceShell } from "@/components/run/workspace/run-workspace-shell";

export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return (
    <RunWorkspaceShell runId={runId}>
      <RunProgress runId={runId} />
    </RunWorkspaceShell>
  );
}
