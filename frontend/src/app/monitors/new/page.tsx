import { CreateMonitorSurface } from "@/features/monitors/create-monitor";

type NewMonitorPageProps = {
  searchParams: Promise<{
    artifact_id?: string;
    artifact_version_id?: string;
    version_number?: string;
  }>;
};

export default async function NewMonitorPage({ searchParams }: NewMonitorPageProps) {
  const params = await searchParams;
  const versionNumber = params.version_number
    ? Number.parseInt(params.version_number, 10)
    : Number.NaN;
  return (
    <CreateMonitorSurface
      artifactId={params.artifact_id ?? null}
      artifactVersionId={params.artifact_version_id ?? null}
      versionNumber={Number.isInteger(versionNumber) && versionNumber > 0 ? versionNumber : null}
    />
  );
}
