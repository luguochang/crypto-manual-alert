import { describe, expect, it, vi } from "vitest";

import {
  createDataDeletion,
  createDataExport,
  getDataExportBundle,
  getDataLifecyclePolicy,
} from "../../src/lib/api/product-client";
import {
  dataDeletionSchema,
  dataExportBundleSchema,
  dataLifecyclePolicySchema,
} from "../../src/lib/schemas/product-api";
import {
  clearPersistedExportId,
  persistExportId,
  readPersistedExportId,
  type LifecycleStorage,
} from "../../src/features/settings/data-lifecycle-state";

const ids = {
  tenant: "11111111-1111-4111-8111-111111111111",
  workspace: "22222222-2222-4222-8222-222222222222",
  owner: "33333333-3333-4333-8333-333333333333",
};

function policy() {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    tenant_id: ids.tenant,
    workspace_id: ids.workspace,
    owner_user_id: ids.owner,
    product_retention_days: 365,
    artifact_retention_days: 365,
    task_retention_days: 365,
    run_retention_days: 365,
    decision_retention_days: 365,
    usage_retention_days: 365,
    completed_checkpoint_retention_days: 30,
    technical_projection_retention_days: 30,
    log_retention_days: 30,
    backup_retention_days: 35,
    retain_raw_prompt: false,
    retain_raw_response: false,
    legal_hold_active: false,
    legal_hold_reason: null,
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T00:00:00Z",
  };
}

function deletion() {
  return {
    id: "55555555-5555-4555-8555-555555555555",
    tenant_id: ids.tenant,
    workspace_id: ids.workspace,
    owner_user_id: ids.owner,
    scope: "user_data",
    idempotency_key: "delete-1",
    status: "pending_external",
    attempt: 1,
    lease_expires_at: null,
    requested_at: "2026-07-20T00:00:00Z",
    completed_at: null,
    expired_at: null,
    legal_hold_active: false,
    legal_hold_reason: null,
    system_status: { product_db: "succeeded", langsmith: "pending_external" },
    external_deletion_reference: { langsmith: null },
    last_error: null,
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T00:00:00Z",
  };
}

describe("data lifecycle Product API contract", () => {
  it("scopes durable export rejoin state to a validated owner", () => {
    const values = new Map<string, string>();
    const storage: LifecycleStorage = {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => void values.set(key, value),
      removeItem: (key) => void values.delete(key),
    };
    const exportId = "66666666-6666-4666-8666-666666666666";

    expect(persistExportId(ids.owner, exportId, storage)).toBe(true);
    expect(readPersistedExportId(ids.owner, storage)).toBe(exportId);
    expect(readPersistedExportId("not-a-user-id", storage)).toBeNull();

    clearPersistedExportId(ids.owner, storage);
    expect(readPersistedExportId(ids.owner, storage)).toBeNull();
  });

  it("fails closed when durable export storage is invalid or unavailable", () => {
    const invalidStorage: LifecycleStorage = {
      getItem: () => "not-an-export-id",
      setItem: () => undefined,
      removeItem: vi.fn(),
    };
    const deniedStorage: LifecycleStorage = {
      getItem: () => { throw new Error("denied"); },
      setItem: () => { throw new Error("denied"); },
      removeItem: () => { throw new Error("denied"); },
    };

    expect(readPersistedExportId(ids.owner, invalidStorage)).toBeNull();
    expect(invalidStorage.removeItem).toHaveBeenCalledOnce();
    expect(persistExportId(ids.owner, "invalid", invalidStorage)).toBe(false);
    expect(readPersistedExportId(ids.owner, deniedStorage)).toBeNull();
    expect(persistExportId(ids.owner, "66666666-6666-4666-8666-666666666666", deniedStorage)).toBe(false);
    expect(() => clearPersistedExportId(ids.owner, deniedStorage)).not.toThrow();
  });

  it("keeps default retention and raw-I/O policy explicit", () => {
    const parsed = dataLifecyclePolicySchema.parse(policy());
    expect(parsed.product_retention_days).toBe(365);
    expect(parsed.completed_checkpoint_retention_days).toBe(30);
    expect(parsed.backup_retention_days).toBe(35);
    expect(parsed.retain_raw_prompt).toBe(false);
    expect(parsed.retain_raw_response).toBe(false);
  });

  it("preserves pending_external deletion instead of treating it as success", () => {
    expect(dataDeletionSchema.parse(deletion()).status).toBe("pending_external");
    expect(() => dataDeletionSchema.parse({ ...deletion(), status: "unknown" })).toThrow();
  });

  it("uses Product paths, stable idempotency keys, and strict export responses", async () => {
    const exportJob = {
      id: "66666666-6666-4666-8666-666666666666",
      tenant_id: ids.tenant,
      workspace_id: ids.workspace,
      owner_user_id: ids.owner,
      scope: "user_data",
      idempotency_key: "export-1",
      status: "queued",
      attempt: 0,
      lease_expires_at: null,
      requested_at: "2026-07-20T00:00:00Z",
      completed_at: null,
      expired_at: null,
      manifest_version: null,
      manifest_hash: null,
      last_error: null,
      created_at: "2026-07-20T00:00:00Z",
      updated_at: "2026-07-20T00:00:00Z",
    };
    const bundle = {
      export_id: exportJob.id,
      status: "succeeded",
      manifest_version: 1,
      manifest_hash: "a".repeat(64),
      bundle: { bundle_version: 1, records: {} },
    };
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      const path = String(input);
      if (path.endsWith("/policy")) return Response.json(policy());
      if (path.endsWith("/exports")) return Response.json(exportJob, { status: 202 });
      if (path.endsWith("/bundle")) return Response.json(bundle);
      if (path.endsWith("/deletions")) return Response.json(deletion(), { status: 202 });
      return Response.json(exportJob);
    });

    expect((await getDataLifecyclePolicy(fetcher)).product_retention_days).toBe(365);
    await createDataExport(fetcher, "stable-export-key");
    const loaded = await getDataExportBundle(exportJob.id, fetcher);
    expect(dataExportBundleSchema.parse(loaded).bundle).toEqual({ bundle_version: 1, records: {} });
    await createDataDeletion("DELETE MY DATA", fetcher, "stable-delete-key");

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/product/api/v2/data-lifecycle/policy",
      "/api/product/api/v2/data-lifecycle/exports",
      `/api/product/api/v2/data-lifecycle/exports/${exportJob.id}/bundle`,
      "/api/product/api/v2/data-lifecycle/deletions",
    ]);
    expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).get("idempotency-key")).toBe("stable-export-key");
    expect(new Headers(fetcher.mock.calls[3]?.[1]?.headers).get("idempotency-key")).toBe("stable-delete-key");
  });
});
