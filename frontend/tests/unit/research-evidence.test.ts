import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ResearchEvidence,
  evidenceSummaryDisclosure,
} from "../../src/features/analysis/research-evidence";
import type { AnalysisResearchViewModel } from "../../src/features/analysis/analysis-view-model";

describe("research evidence disclosure", () => {
  it("keeps the full evidence unchanged while creating a readable bounded preview", () => {
    const summary = `${"宏观流动性仍然偏紧，".repeat(9)}这一句形成完整边界。${"后续原文必须保留。".repeat(12)}FULL-TAIL`;

    const disclosure = evidenceSummaryDisclosure(summary);

    expect(disclosure.full).toBe(summary);
    expect(disclosure.truncated).toBe(true);
    expect(disclosure.preview).toMatch(/。…$/);
    expect(disclosure.preview).not.toContain("FULL-TAIL");
    expect(Array.from(disclosure.preview).length).toBeLessThanOrEqual(121);
  });

  it("does not truncate short content or split Unicode code points", () => {
    const short = "单一来源的短摘要保持原样。";
    expect(evidenceSummaryDisclosure(short)).toEqual({
      full: short,
      preview: short,
      truncated: false,
    });

    const emojiSummary = "市场结构稳定。" + "📈".repeat(200) + "完整结尾";
    const preview = evidenceSummaryDisclosure(emojiSummary).preview;
    expect(preview).not.toContain("�");
    expect(Array.from(preview).length).toBeLessThanOrEqual(121);
  });

  it("renders a collapsed control only for long summaries and preserves source metadata", () => {
    const longSummary = `${"A source-specific evidence sentence remains readable. ".repeat(8)}FULL-TAIL`;
    const html = renderToStaticMarkup(createElement(ResearchEvidence, {
      research: researchProjection(longSummary),
    }));

    expect(html).toContain("独立长摘要来源");
    expect(html).toContain("独立短摘要来源");
    expect(html).toContain("OpenAI Web Search");
    expect(html).toContain("支持判断");
    expect(html).toContain("背景信息");
    expect(html).toContain("发布时间");
    expect(html).toContain("抓取时间");
    expect(html).toContain('href="https://example.com/evidence/long"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("aria-controls=");
    expect(html.match(/class="evidence-summary-toggle"/g)).toHaveLength(1);
    expect(html).toContain("展开完整摘要");
    expect(html).toContain("短摘要完整显示。");
    expect(html).not.toContain("FULL-TAIL");
  });

  it("renders an explicit fallback disclosure without claiming exchange-native data", () => {
    const html = renderToStaticMarkup(createElement(ResearchEvidence, {
      research: {
        state: "available",
        marketSnapshot: {
          symbol: "BTC-USDT-SWAP",
          sourceLevel: "web_search_verified",
          provider: "Web Search 引用证据",
          disclosure: "交易所原生行情数据不可用；本次使用了带引用的 Web Search 市场证据。该证据不等同于交易所原生行情，缺失字段按不可用处理。",
          fetchedAt: "2026-07-17T08:12:00Z",
          summary: "标记价 不可用 · 指数价 不可用 · 资金费率 不可用 · 未平仓量 不可用",
          metrics: [
            { label: "最新成交", value: "不可用" },
            { label: "最优买价", value: "不可用" },
            { label: "最优卖价", value: "不可用" },
            { label: "24h 成交量", value: "不可用" },
          ],
        },
        webEvidence: [],
      },
    }));

    expect(html).toContain("市场来源说明");
    expect(html).toContain("Web Search 引用证据");
    expect(html).not.toContain(">交易所原生<");
    expect(html).toContain("交易所原生行情数据不可用");
    expect(html).toContain("带引用的 Web Search 市场证据");
    expect(html).toContain("该证据不等同于交易所原生行情");
    expect(html).toContain("不可用");
    expect(html).not.toContain("<pre");
    expect(html).not.toContain("{\"source_level\"");
  });

  it("keeps excluded provider results visible without presenting them as usable evidence", () => {
    const research = researchProjection("短摘要");
    research.webEvidence.push({
      title: "无关企业财报",
      provider: "Tavily",
      href: "https://example.com/earnings",
      fetchedAt: "2026-07-17T08:13:00Z",
      publishedAt: null,
      summary: "该来源与本次资产和宏观问题无关。",
      author: null,
      relation: "excluded",
    });

    const html = renderToStaticMarkup(createElement(ResearchEvidence, { research }));

    expect(html).toContain("已验证 2 条来源，另排除 1 条");
    expect(html).toContain("已排除（相关性不足）");
    expect(html).toContain('data-evidence-relation="excluded"');
    expect(html).toContain("无关企业财报");
  });
});

function researchProjection(longSummary: string): AnalysisResearchViewModel {
  return {
    state: "available",
    marketSnapshot: null,
    webEvidence: [
      {
        title: "独立长摘要来源",
        provider: "OpenAI Web Search",
        href: "https://example.com/evidence/long",
        fetchedAt: "2026-07-17T08:10:00Z",
        publishedAt: "2026-07-17T07:30:00Z",
        summary: longSummary,
        author: "Research desk",
        relation: "supports",
      },
      {
        title: "独立短摘要来源",
        provider: "Publisher feed",
        href: "https://example.com/evidence/short",
        fetchedAt: "2026-07-17T08:12:00Z",
        publishedAt: null,
        summary: "短摘要完整显示。",
        author: null,
        relation: "context",
      },
    ],
  };
}
