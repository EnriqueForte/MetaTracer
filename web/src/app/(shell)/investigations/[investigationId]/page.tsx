import { InvestigationDetail } from "@/components/investigations/investigation-detail";

export default async function InvestigationPage({
  params,
}: {
  params: Promise<{ investigationId: string }>;
}) {
  const { investigationId } = await params;
  return <InvestigationDetail investigationId={investigationId} />;
}
