import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  buildDeepResearchEditResponse,
  deepResearchEditValuesFromPayload,
  DeepResearchReviewPanel,
  deepResearchReviewItemIdentity,
} from "@/features/work/deep-research-review-panel";
import {
  pendingInterruptSchema,
  type DeepResearchPendingInterrupt,
} from "@/lib/schemas/product-api";

describe("deep research review panel", () => {
  it("renders a typed report summary, review round, and read-only source catalog", () => {
    const interrupt = researchInterrupt();
    const html = renderReview(interrupt, {
      reviewPosition: { index: 1, total: 2 },
      deferSubmission: true,
    });

    expect(deepResearchReviewItemIdentity(interrupt, { index: 1, total: 2 }))
      .toBe("审核项 1/2，BTC-USDT-SWAP，7d，第 2 轮");
    expect(html).toContain("研究报告草稿待人工确认");
    expect(html).toContain("BTC 机构采用趋势仍然成立，但宏观流动性构成主要反证。");
    expect(html).toContain("2 条");
    expect(html).toContain("第 2 轮");
    expect(html).toContain("只读来源目录");
    expect(html).toContain('href="https://example.com/source-1"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).not.toMatch(/raw json|model_audits|content_hash/i);
  });

  it("builds only a complete report replacement and preserves server-owned fields", () => {
    const interrupt = researchInterrupt();
    const values = deepResearchEditValuesFromPayload(interrupt.payload);
    values.executiveSummary = "人工复核后收窄的研究结论。";
    values.riskNotes = "流动性收紧\n监管事件窗口";
    const response = buildDeepResearchEditResponse(
      values,
      interrupt.payload,
      "  收窄结论范围  ",
    );

    expect(response).toMatchObject({
      action: "edit",
      comment: "收窄结论范围",
      edits: {
        report: {
          executive_summary: "人工复核后收窄的研究结论。",
          risk_notes: ["流动性收紧", "监管事件窗口"],
        },
      },
    });
    expect(response.edits).not.toHaveProperty("sources");
    expect(response.edits).not.toHaveProperty("harness_mode");
    expect(response.edits).not.toHaveProperty("model_audits");
    expect(response.edits).not.toHaveProperty("status");
  });

  it("rejects no-op edits and citations outside the immutable source catalog", () => {
    const interrupt = researchInterrupt();
    const unchanged = deepResearchEditValuesFromPayload(interrupt.payload);

    expect(() => buildDeepResearchEditResponse(unchanged, interrupt.payload, ""))
      .toThrow("Deep research edits must change the report");

    const invalidCitation = deepResearchEditValuesFromPayload(interrupt.payload);
    invalidCitation.executiveSummary = "Changed summary.";
    invalidCitation.sections[0]!.findings[0]!.source_indexes = [8];
    expect(() => buildDeepResearchEditResponse(invalidCitation, interrupt.payload, ""))
      .toThrow();
  });
});

function renderReview(
  interrupt: DeepResearchPendingInterrupt,
  overrides: Partial<ComponentProps<typeof DeepResearchReviewPanel>> = {},
) {
  return renderToStaticMarkup(createElement(DeepResearchReviewPanel, {
    interrupt,
    expiresAt: "2026-07-19T12:10:00Z",
    onDecide: () => undefined,
    ...overrides,
  }));
}

function researchInterrupt(): DeepResearchPendingInterrupt {
  const parsed = pendingInterruptSchema.parse({
    interrupt_id: "research-review-1",
    response_version: 1,
    status: "pending",
    payload: {
      kind: "deep_research_review",
      schema_version: "1.0",
      allowed_actions: ["approve", "reject", "edit"],
      symbol: "BTC-USDT-SWAP",
      horizon: "7d",
      review_iteration: 2,
      artifact: {
        artifact_type: "deep_research_report",
        schema_version: "1.0",
        status: "draft",
        harness_mode: "deepagents",
        search_coverage: {
          status: "complete",
          attempted_queries: 1,
          successful_queries: 1,
          failed_queries: [],
        },
        report: {
          executive_summary: "BTC 机构采用趋势仍然成立，但宏观流动性构成主要反证。",
          sections: [{
            title: "机构采用",
            summary: "可验证来源支持采用趋势。",
            findings: [{ claim: "机构资金继续流入。", source_indexes: [1] }],
          }],
          risk_notes: ["宏观流动性可能收紧。"],
          evidence_gaps: ["缺少部分场外交易数据。"],
        },
        sources: [
          { index: 1, evidence: evidence(1) },
          { index: 2, evidence: evidence(2) },
        ],
        model_audits: [{
          prompt_version: "deep-research-v1",
          call_count: 1,
          input_tokens: 120,
          output_tokens: 80,
          total_tokens: 200,
          latency_ms: 500,
          observation_ids: ["observation-1"],
        }],
      },
    },
    response: null,
    responded_at: null,
  });
  if (parsed.payload.kind !== "deep_research_review") {
    throw new Error("research fixture did not parse as deep research review");
  }
  return parsed as DeepResearchPendingInterrupt;
}

function evidence(index: number) {
  return {
    query: `BTC research ${index}`,
    final_url: `https://example.com/source-${index}`,
    redirect_chain: [],
    http_status: 200,
    fetched_at: "2026-07-19T12:00:00Z",
    published_at: null,
    content_hash: String(index).repeat(64),
    parser_version: "test-v1",
    title: `Verified source ${index}`,
    author: null,
    source: "test_search",
    excerpt: "Provider-verified evidence excerpt.",
    evidence_relation: "supports",
  };
}
