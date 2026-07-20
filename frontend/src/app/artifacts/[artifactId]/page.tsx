import { ArtifactDetailSurface } from "@/features/artifacts/artifact-detail-surface";

type ArtifactPageProps = {
  params: Promise<{ artifactId: string }>;
  searchParams: Promise<{ version_number?: string }>;
};

export default async function ArtifactPage({ params, searchParams }: ArtifactPageProps) {
  const { artifactId } = await params;
  const { version_number: versionNumber } = await searchParams;
  const parsedVersion = versionNumber ? Number.parseInt(versionNumber, 10) : undefined;
  return (
    <ArtifactDetailSurface
      artifactId={artifactId}
      initialVersionNumber={Number.isInteger(parsedVersion) && parsedVersion && parsedVersion > 0 ? parsedVersion : undefined}
    />
  );
}
