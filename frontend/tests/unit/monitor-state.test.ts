import { describe, expect, it } from "vitest";

import { MonitorApiError } from "../../src/lib/api/monitor-client";
import {
  idempotencyKeyFor,
  monitorErrorMessage,
  mutationIdentity,
  prepareMonitorRequest,
} from "../../src/features/monitors/monitor-state";

describe("Monitor form and mutation state", () => {
  it("builds a typed request without raw JSON fields", () => {
    const expiry = new Date(Date.now() + 86_400_000).toISOString().slice(0, 16);
    const prepared = prepareMonitorRequest(
      {
        artifactId: "22222222-2222-4222-8222-222222222222",
        artifactVersionId: "33333333-3333-4333-8333-333333333333",
      },
      {
        name: "Daily thesis review",
        runTaskType: "market_analysis",
        condition: { kind: "scheduled_review" },
        schedule: "0 0 * * *",
        timezone: "Asia/Shanghai",
        expiresAtLocal: expiry,
        quietHours: null,
        destinationIds: [],
      },
    );

    expect(prepared.success).toBe(true);
    if (!prepared.success) return;
    expect(prepared.request.condition).toEqual({ kind: "scheduled_review" });
    expect(prepared.request.schedule).toBe("0 0 * * *");
    expect(prepared.request).not.toHaveProperty("raw_json");
  });

  it("reuses a key for an unchanged logical retry and rotates after input changes", () => {
    const firstIdentity = mutationIdentity("pause", { id: "monitor-1", version: 3 });
    const first = idempotencyKeyFor(null, firstIdentity, () => "key-1");
    const retry = idempotencyKeyFor(first, firstIdentity, () => "must-not-run");
    const changedIdentity = mutationIdentity("pause", { id: "monitor-1", version: 4 });
    const changed = idempotencyKeyFor(retry, changedIdentity, () => "key-2");

    expect(retry.key).toBe("key-1");
    expect(changed.key).toBe("key-2");
  });

  it.each([
    [401, "登录状态已失效"],
    [403, "没有管理持续监控的权限"],
    [409, "已被其他操作更新"],
    [422, "未通过校验"],
    [429, "额度已用尽"],
    [502, "无效响应"],
    [503, "暂时不可用"],
  ])("maps HTTP %i to explicit accessible feedback", (status, expected) => {
    expect(monitorErrorMessage(new MonitorApiError("upstream", status), "fallback"))
      .toContain(expected);
  });
});
