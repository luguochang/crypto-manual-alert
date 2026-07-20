import { MonitorListSurface } from "@/features/monitors/monitor-list";
import { monitorStatusFilterSchema } from "@/lib/schemas/monitor-api";

type MonitorsPageProps = {
  searchParams: Promise<{ status?: string }>;
};

export default async function MonitorsPage({ searchParams }: MonitorsPageProps) {
  const { status: requestedStatus } = await searchParams;
  const parsedStatus = monitorStatusFilterSchema.safeParse(requestedStatus ?? "running");
  return <MonitorListSurface status={parsedStatus.success ? parsedStatus.data : "running"} />;
}
