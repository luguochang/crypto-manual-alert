import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DeepResearchProjection } from "@/features/research/deep-research-projection";
import { productTaskSchema } from "@/lib/schemas/product-api";

describe("Deep Research projection", () => {
  it("renders typed report content and source links without raw JSON", () => {
    const task = productTaskSchema.parse({
      task_id: "11111111-1111-4111-8111-111111111111",
      task_type: "deep_research",
      correlation_id: "22222222-2222-4222-8222-222222222222",
      status: "succeeded",
      symbol: "BTC-USDT-SWAP",
      horizon: "7d",
      query_text: "研究 BTC 机构采用趋势和主要反证。",
      created_at: "2026-07-19T12:00:00Z",
      completed_at: "2026-07-19T12:05:00Z",
      artifact: null,
      deep_research_artifact: {
        artifact_type: "deep_research_report",
        schema_version: "1.0",
        status: "committed",
        harness_mode: "deepagents",
        search_coverage: {
          status: "partial",
          attempted_queries: 3,
          successful_queries: 2,
          failed_queries: [{
            query_index: 2,
            provider: "builtin_web_search",
            error_kind: "timeout",
            retryable: true,
            attempt: 3,
          }],
        },
        report: {
          executive_summary: "BTC 机构采用仍在推进。",
          sections: [{
            title: "机构采用",
            summary: "可验证来源支持该趋势。",
            findings: [{
              claim: "机构采用仍在推进。",
              source_indexes: [1],
            }],
          }],
          risk_notes: ["事件窗口可能改变当前判断。"],
          evidence_gaps: ["缺少长期资金流样本。"],
        },
        sources: [{
          index: 1,
          evidence: {
            query: "BTC institutional adoption",
            final_url: "https://example.com/verified-source",
            redirect_chain: [],
            http_status: 200,
            fetched_at: "2026-07-19T12:00:00Z",
            published_at: null,
            content_hash: "a".repeat(64),
            parser_version: "test-v1",
            title: "Verified source",
            author: null,
            source: "test_search",
            excerpt: "A provider-verified source excerpt.",
            evidence_relation: "supports",
          },
        }],
        model_audits: [],
      },
      errors: [],
      market_snapshot: null,
      web_evidence: [],
      pending_interrupts: null,
    });

    const html = renderToStaticMarkup(
      createElement(DeepResearchProjection, { task }),
    );

    expect(html).toContain("深度研究已完成");
    expect(html).toContain("BTC 机构采用仍在推进");
    expect(html).toContain("Verified source");
    expect(html).toContain("2 / 3");
    expect(html).toContain("检索超时");
    expect(html).toContain('href="https://example.com/verified-source"');
    expect(html).not.toContain("<pre");
    expect(html).not.toContain("[object Object]");

    const blockedHtml = renderToStaticMarkup(
      createElement(DeepResearchProjection, {
        task: {
          ...task,
          status: "blocked",
          deep_research_artifact: null,
        },
      }),
    );
    expect(blockedHtml).toContain("研究已阻断");
    expect(blockedHtml).toContain("tone-blocked");
    expect(blockedHtml).not.toContain("tone-warning");
  });
});
