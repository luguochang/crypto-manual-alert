import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  officialAgentApiUrl,
  officialConnectionStatus,
  officialStreamSubtitle,
  projectOfficialValues,
} from "../../src/features/agent-runtime/official-run-stream";

const componentPath = resolve(
  process.cwd(),
  "src/features/agent-runtime/official-run-stream.tsx",
);

describe("official run stream", () => {
  it("provides the official root stream component", () => {
    expect(existsSync(componentPath)).toBe(true);
  });

  it("uses one read-only official useStream root with the same-origin SSE transport", () => {
    const source = readFileSync(componentPath, "utf8");

    expect(source.match(/\buseStream\s*</g)).toHaveLength(1);
    expect(source).toMatch(/\bassistantId\s*(?::|,)/);
    expect(source).toMatch(/\bthreadId\s*(?::|,)/);
    expect(source).toMatch(/apiUrl\s*:\s*officialAgentApiUrl\(window\.location\.origin\)/);
    expect(source).not.toMatch(/apiUrl\s*:\s*["']\/api\/agent["']/);
    expect(source).toMatch(/transport\s*:\s*["']sse["']/);
    expect(source).toMatch(/optimistic\s*:\s*false/);
    expect(source).not.toMatch(/JSON\.stringify|EventSource|fetch\s*\(/);
    expect(source).not.toMatch(/\.submit\s*\(|\.respond(?:All)?\s*\(|\.stop\s*\(|\.getThread\s*\(/);
    expect(source).not.toContain("实时连接仅用于读取当前执行投影");
    expect(source).toContain("officialStreamSubtitle(");
  });

  it("gives the official SDK an absolute same-origin BFF URL", () => {
    expect(officialAgentApiUrl("https://product.example.com")).toBe(
      "https://product.example.com/api/agent",
    );
    expect(officialAgentApiUrl("http://127.0.0.1:3105/work?task=1")).toBe(
      "http://127.0.0.1:3105/api/agent",
    );
  });

  it("never reports an errored stream as connected", () => {
    expect(officialConnectionStatus(true, undefined)).toEqual({
      label: "正在连接",
      tone: "active",
    });
    expect(officialConnectionStatus(false, undefined)).toEqual({
      label: "实时同步中",
      tone: "connected",
    });
    expect(officialConnectionStatus(false, new Error("transport closed"))).toEqual({
      label: "连接已中断",
      tone: "warning",
    });
  });

  it.each([
    ["completed", "执行已完成", "本次官方执行已完成，最终状态已同步。"],
    ["completed_blocked", "执行已阻断", "本次官方执行已被门禁阻断，最终状态已同步。"],
    ["completed_failed", "执行失败", "本次官方执行失败，最终状态已同步。"],
  ] as const)("uses terminal label and subtitle semantics for %s", (lifecycle, label, subtitle) => {
    expect(officialConnectionStatus(false, undefined, lifecycle)).toEqual({
      label,
      tone: "connected",
    });
    expect(officialStreamSubtitle(false, undefined, lifecycle)).toBe(subtitle);
    expect(`${label} ${subtitle}`).not.toMatch(/正在|等待/);
  });

  it("keeps loading and error subtitle semantics ahead of stale lifecycle values", () => {
    expect(officialStreamSubtitle(true, undefined, "completed")).toBe("正在连接官方执行流。");
    expect(officialStreamSubtitle(false, new Error("transport closed"), "completed")).toBe(
      "实时执行连接已中断，产品状态仍会继续更新。",
    );
  });

  it("projects a failed official execution as a terminal progress item", () => {
    expect(projectOfficialValues({ lifecycle: "completed_failed" })).toEqual([
      {
        id: "lifecycle",
        label: "执行阶段",
        detail: "官方执行未完成",
        tone: "danger",
      },
    ]);
  });

  it("projects only explicitly named execution fields into human-readable progress", () => {
    const projection = projectOfficialValues({
      lifecycle: "analysis_completed",
      market_snapshot: {
        symbol: "BTC-USDT-SWAP",
        mark_price: "67250.5",
        private_exchange_payload: "market-secret",
      },
      web_evidence: [
        { title: "ETF flows", summary: "Positive", source_url: "https://example.com/1" },
        { title: "Macro calendar", summary: "Event ahead", source_url: "https://example.com/2" },
      ],
      analysis: {
        main_action: "open_long",
        probability: 0.68,
        root_cause_chain: ["hidden chain must not render"],
      },
      evidence_verdict: {
        sufficient: true,
        confidence_cap: 0.72,
        missing_optional: ["options_skew"],
      },
      risk_verdict: {
        allowed: true,
        warnings: ["Use light sizing"],
      },
      messages: [{ content: "do not print the complete state" }],
      secret_provider_key: "provider-secret",
    });

    expect(projection).toEqual([
      { id: "lifecycle", label: "执行阶段", detail: "分析推演已完成", tone: "active" },
      { id: "market_snapshot", label: "市场快照", detail: "BTC-USDT-SWAP · 标记价格 67,250.50", tone: "complete" },
      { id: "web_evidence", label: "Web 证据", detail: "已汇总 2 条来源", tone: "complete" },
      { id: "analysis", label: "分析判断", detail: "偏向开多 · 置信度 68%", tone: "complete" },
      { id: "evidence_verdict", label: "证据门禁", detail: "证据充分 · 置信度上限 72%", tone: "complete" },
      { id: "risk_verdict", label: "风险门禁", detail: "允许进入人工决策 · 1 条风险提示", tone: "complete" },
    ]);
    const rendered = projection.map((item) => `${item.label} ${item.detail}`).join(" ");
    expect(rendered).not.toContain("provider-secret");
    expect(rendered).not.toContain("market-secret");
    expect(rendered).not.toContain("hidden chain");
    expect(rendered).not.toContain("complete state");
  });

  it("does not expose malformed or unnamed state values", () => {
    expect(projectOfficialValues({
      lifecycle: { raw: "secret" },
      market_snapshot: "raw-market-json",
      web_evidence: { raw: true },
      analysis: null,
      evidence_verdict: ["raw"],
      risk_verdict: "raw",
      arbitrary: "secret",
    })).toEqual([]);
  });
});
