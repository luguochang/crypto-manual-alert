import { describe, expect, it } from "vitest";

import {
  createMonitorRequestSchema,
  monitorConditionSchema,
  monitorListSchema,
  monitorScheduleSchema,
  monitorTriggerListSchema,
} from "../../src/lib/schemas/monitor-api";

const ids = {
  monitor: "11111111-1111-4111-8111-111111111111",
  artifact: "22222222-2222-4222-8222-222222222222",
  artifactVersion: "33333333-3333-4333-8333-333333333333",
  trigger: "44444444-4444-4444-8444-444444444444",
  task: "55555555-5555-4555-8555-555555555555",
};

function monitorView() {
  return {
    id: ids.monitor,
    name: "BTC macro review",
    status: "active",
    run_task_type: "market_analysis",
    artifact_id: ids.artifact,
    artifact_version_id: ids.artifactVersion,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    condition: { kind: "price", operator: "gte", threshold: 70_000 },
    schedule: "0 * * * *",
    timezone: "Asia/Shanghai",
    quiet_hours: { start: "23:00", end: "07:00" },
    expires_at: "2026-08-19T10:00:00+08:00",
    destination_ids: [],
    version: 3,
    schedule_version: 2,
    cron_configured: true,
    next_run_at: "2026-07-19T19:00:00+08:00",
    latest_trigger: {
      id: ids.trigger,
      trigger_kind: "cron",
      status: "admitted",
      reason: "condition_matched",
      task_id: ids.task,
      triggered_at: "2026-07-19T18:00:00+08:00",
      created_at: "2026-07-19T18:00:00+08:00",
    },
    created_at: "2026-07-19T10:00:00+08:00",
    updated_at: "2026-07-19T18:00:00+08:00",
  } as const;
}

describe("Monitor API schemas", () => {
  it("accepts only the five backend-controlled cron schedules", () => {
    for (const schedule of [
      "*/5 * * * *",
      "*/15 * * * *",
      "0 * * * *",
      "0 */4 * * *",
      "0 0 * * *",
    ]) {
      expect(monitorScheduleSchema.parse(schedule)).toBe(schedule);
    }
    expect(() => monitorScheduleSchema.parse("1 2 3 4 5")).toThrow();
  });

  it("parses the exact strict discriminated condition union", () => {
    expect(monitorConditionSchema.parse({ kind: "price", operator: "lte", threshold: 65_000 }))
      .toEqual({ kind: "price", operator: "lte", threshold: 65_000 });
    expect(monitorConditionSchema.parse({ kind: "thesis", statement: "ETF inflows remain positive" }).kind)
      .toBe("thesis");
    expect(monitorConditionSchema.parse({ kind: "provider_health", provider: "okx", consecutive_failures: 3 }).kind)
      .toBe("provider_health");
    expect(monitorConditionSchema.parse({ kind: "scheduled_review" }))
      .toEqual({ kind: "scheduled_review" });
    expect(() => monitorConditionSchema.parse({
      kind: "price",
      operator: "gte",
      threshold: 70_000,
      query: "must remain forbidden",
    })).toThrow();
  });

  it("validates an exact create DTO and forbids browser-owned extras", () => {
    const request = {
      name: "BTC macro review",
      artifact_id: ids.artifact,
      artifact_version_id: ids.artifactVersion,
      run_task_type: "market_analysis",
      condition: { kind: "scheduled_review" },
      schedule: "0 */4 * * *",
      timezone: "Asia/Shanghai",
      expires_at: "2026-08-19T10:00:00+08:00",
      quiet_hours: null,
      destination_ids: [],
    } as const;
    expect(createMonitorRequestSchema.parse(request)).toEqual(request);
    expect(() => createMonitorRequestSchema.parse({
      ...request,
      artifact: { content: "must stay server-owned" },
    })).toThrow();
    expect(() => createMonitorRequestSchema.parse({
      ...request,
      quiet_hours: { start: "09:00", end: "09:00" },
    })).toThrow();
  });

  it("strictly parses the fixed MonitorView and MonitorTriggerView fields", () => {
    expect(monitorListSchema.parse({ items: [monitorView()] }).items[0]?.schedule_version).toBe(2);
    expect(monitorTriggerListSchema.parse({ items: [monitorView().latest_trigger] }).items[0]?.trigger_kind)
      .toBe("cron");
    expect(() => monitorListSchema.parse({
      items: [{ ...monitorView(), source_artifact: { title: "frontend invention" } }],
    })).toThrow();
    expect(() => monitorTriggerListSchema.parse({
      monitor_id: ids.monitor,
      items: [monitorView().latest_trigger],
    })).toThrow();
  });
});
