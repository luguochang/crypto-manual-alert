import { describe, expect, it, vi } from "vitest";

import {
  createMonitor,
  deleteMonitor,
  listMonitors,
  listMonitorTriggers,
  pauseMonitor,
  resumeMonitor,
  triggerMonitor,
} from "../../src/lib/api/monitor-client";

const monitorId = "11111111-1111-4111-8111-111111111111";
const artifactId = "22222222-2222-4222-8222-222222222222";
const artifactVersionId = "33333333-3333-4333-8333-333333333333";

function monitorView(status = "active", version = 3) {
  return {
    id: monitorId,
    name: "BTC macro review",
    status,
    run_task_type: "market_analysis",
    artifact_id: artifactId,
    artifact_version_id: artifactVersionId,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    condition: { kind: "price", operator: "gte", threshold: 70_000 },
    schedule: "0 * * * *",
    timezone: "Asia/Shanghai",
    quiet_hours: { start: "23:00", end: "07:00" },
    expires_at: "2026-08-19T10:00:00+08:00",
    destination_ids: [],
    version,
    schedule_version: 2,
    cron_configured: true,
    next_run_at: "2026-07-19T19:00:00+08:00",
    latest_trigger: null,
    created_at: "2026-07-19T10:00:00+08:00",
    updated_at: "2026-07-19T18:00:00+08:00",
  };
}

const createRequest = {
  name: "BTC macro review",
  artifact_id: artifactId,
  artifact_version_id: artifactVersionId,
  run_task_type: "market_analysis" as const,
  condition: { kind: "price" as const, operator: "gte" as const, threshold: 70_000 },
  schedule: "0 * * * *" as const,
  timezone: "Asia/Shanghai",
  expires_at: "2026-08-19T10:00:00+08:00",
  quiet_hours: { start: "23:00", end: "07:00" },
  destination_ids: [],
};

describe("Monitor API client", () => {
  it("reads the URL-filtered list and exact trigger history endpoints", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      return String(input).endsWith("/triggers")
        ? Response.json({ items: [] })
        : Response.json({ items: [monitorView()] });
    });

    await listMonitors("attention", fetcher);
    await listMonitorTriggers(monitorId, fetcher);

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/product/api/v2/monitors?status=attention");
    expect(fetcher.mock.calls[1]?.[0]).toBe(`/api/product/api/v2/monitors/${monitorId}/triggers`);
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ method: "GET", cache: "no-store" });
  });

  it("creates with the strict DTO and caller-owned stable idempotency key", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(monitorView(), { status: 202 });
    });

    await createMonitor(createRequest, "monitor-create-retry-1", fetcher);
    await createMonitor(createRequest, "monitor-create-retry-1", fetcher);

    for (const [, init] of fetcher.mock.calls) {
      expect(new Headers(init?.headers).get("idempotency-key")).toBe("monitor-create-retry-1");
      expect(JSON.parse(String(init?.body))).toEqual(createRequest);
    }
  });

  it("sends expected_version for pause, resume, and soft delete", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      const path = String(input);
      const status = path.endsWith("/pause") ? "paused" : path.endsWith("/resume") ? "active" : "disabled";
      return Response.json(monitorView(status, 4), { status: 202 });
    });

    await pauseMonitor(monitorId, { expected_version: 3 }, "pause-key-3", fetcher);
    await resumeMonitor(monitorId, { expected_version: 3 }, "resume-key-3", fetcher);
    await deleteMonitor(monitorId, { expected_version: 3 }, "delete-key-3", fetcher);

    expect(fetcher.mock.calls.map(([, init]) => init?.method)).toEqual(["POST", "POST", "DELETE"]);
    expect(fetcher.mock.calls.map(([, init]) => JSON.parse(String(init?.body))))
      .toEqual([{ expected_version: 3 }, { expected_version: 3 }, { expected_version: 3 }]);
    expect(fetcher.mock.calls.map(([, init]) => new Headers(init?.headers).get("idempotency-key")))
      .toEqual(["pause-key-3", "resume-key-3", "delete-key-3"]);
  });

  it("manual trigger sends no invented body and parses the returned MonitorView", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({
        ...monitorView("active", 4),
        latest_trigger: {
          id: "44444444-4444-4444-8444-444444444444",
          trigger_kind: "manual",
          status: "received",
          reason: null,
          task_id: null,
          triggered_at: "2026-07-19T18:30:00+08:00",
          created_at: "2026-07-19T18:30:00+08:00",
        },
      }, { status: 202 });
    });

    const monitor = await triggerMonitor(monitorId, "trigger-key-4", fetcher);

    expect(monitor.latest_trigger?.trigger_kind).toBe("manual");
    expect(fetcher.mock.calls[0]?.[1]?.body).toBeUndefined();
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("idempotency-key"))
      .toBe("trigger-key-4");
  });

  it("rejects malformed success views and preserves safe HTTP details", async () => {
    const malformedFetcher = vi.fn(async () => Response.json({
      items: [{ ...monitorView(), raw_cron_config: { secret: true } }],
    }));
    await expect(listMonitors("all", malformedFetcher)).rejects.toMatchObject({
      name: "MonitorApiError",
      status: 502,
    });

    const conflictFetcher = vi.fn(async () => Response.json({
      detail: "Monitor version conflict",
    }, { status: 409 }));
    await expect(pauseMonitor(monitorId, { expected_version: 3 }, "pause-key-3", conflictFetcher))
      .rejects.toMatchObject({ status: 409, message: "Monitor version conflict" });
  });
});
