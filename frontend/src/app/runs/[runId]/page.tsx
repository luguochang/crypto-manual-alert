import { RunDetailSurface } from "@/features/runs/run-detail-surface";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <RunDetailSurface runId={runId} />;
}
