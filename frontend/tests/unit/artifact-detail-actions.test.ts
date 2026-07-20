import { describe, expect, it } from "vitest";

import { artifactCommandCoordinates } from "../../src/features/artifacts/artifact-detail-surface";
import type { ArtifactDetail } from "../../src/lib/schemas/product-api";

describe("Artifact detail Run commands", () => {
  it("binds Retry/Fork context to the selected Artifact version Run", () => {
    const detail = {
      task_id: "22222222-2222-4222-8222-222222222222",
      selected_version: {
        run_id: "11111111-1111-4111-8111-111111111111",
      },
    } as ArtifactDetail;

    expect(artifactCommandCoordinates(detail)).toEqual({
      taskId: "22222222-2222-4222-8222-222222222222",
      runId: "11111111-1111-4111-8111-111111111111",
    });
  });

  it("does not expose a command target when no version is selected", () => {
    expect(artifactCommandCoordinates({
      task_id: "22222222-2222-4222-8222-222222222222",
      selected_version: null,
    } as ArtifactDetail)).toBeNull();
    expect(artifactCommandCoordinates(null)).toBeNull();
  });
});
