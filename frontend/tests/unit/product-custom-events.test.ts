import { describe, expect, it } from "vitest";

import {
  parseProductCustomEvents,
  productCustomChannels,
  productCustomEventSchema,
  projectProductCustomEvents,
} from "../../src/features/agent-runtime/product-custom-events";

const identity = {
  schema_version: "1.0" as const,
  correlation_id: "correlation-1",
  task_id: "task-1",
  run_id: "run-1",
  thread_id: "thread-1",
  request_id: "request-1",
};

function event<T extends Record<string, unknown>>(
  sequence: number,
  payload: T,
): T & typeof identity & { sequence: number; event_id: string } {
  return {
    ...identity,
    sequence,
    event_id: sequence.toString(16).padStart(64, "0"),
    ...payload,
  };
}

describe("Product custom events", () => {
  it("subscribes only to the six approved named custom channels", () => {
    expect(productCustomChannels).toEqual([
      "custom:task_progress",
      "custom:artifact",
      "custom:evidence",
      "custom:usage",
      "custom:notification",
      "custom:quality",
    ]);
  });

  it("strictly rejects unknown names and raw payload fields", () => {
    expect(productCustomEventSchema.safeParse(event(1, {
      name: "provider_payload",
      payload: { api_key: "secret" },
    })).success).toBe(false);
    expect(productCustomEventSchema.safeParse(event(1, {
      name: "task_progress",
      phase: "request_validated",
      status: "active",
      raw_query: "must not pass",
    })).success).toBe(false);
  });

  it("unwraps protocol events, filters another run, deduplicates replay, and sorts", () => {
    const current = event(2, {
      name: "artifact" as const,
      status: "committed" as const,
      content_version: 1,
    });
    const otherRun = { ...event(1, {
      name: "notification" as const,
      status: "requested" as const,
    }), run_id: "run-2" };
    const wrapped = {
      method: "custom",
      params: { namespace: [], data: current },
    };

    expect(parseProductCustomEvents([wrapped, current, otherRun], "run-1")).toEqual([
      current,
    ]);
  });

  it("projects every event family into bounded human-readable progress", () => {
    const events = [
      event(1, { name: "task_progress" as const, phase: "request_validated", status: "active" as const }),
      event(2, { name: "evidence" as const, stage: "collected" as const, verified_source_count: 4, sufficient: null }),
      event(3, { name: "usage" as const, model_call_count: 2, input_tokens: 100, output_tokens: 40, total_tokens: 140, prompt_versions: ["v1"] }),
      event(4, { name: "quality" as const, evidence_sufficient: true, risk_allowed: true, warning_count: 1, blocked_reason_count: 0 }),
      event(5, { name: "artifact" as const, status: "committed" as const, content_version: 2 }),
      event(6, { name: "notification" as const, status: "requested" as const }),
    ];

    const projected = projectProductCustomEvents(events, "run-1");
    expect(projected).toEqual([
      { id: "lifecycle", label: "执行阶段", detail: "分析请求已校验", tone: "active" },
      { id: "web_evidence", label: "Web 证据", detail: "已汇总 4 条可验证来源", tone: "complete" },
      { id: "usage", label: "模型用量", detail: "2 次模型调用 · 140 tokens", tone: "complete" },
      { id: "quality", label: "质量门禁", detail: "门禁通过 · 1 条风险提示", tone: "complete" },
      { id: "artifact", label: "分析报告", detail: "第 2 版报告已提交", tone: "complete" },
      { id: "notification", label: "通知发送", detail: "本次任务已请求完成通知", tone: "active" },
    ]);
    expect(JSON.stringify(projected)).not.toMatch(/correlation-1|task-1|run-1|thread-1|request-1|prompt_versions/);
  });
});
