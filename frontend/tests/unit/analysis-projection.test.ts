import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AnalysisProjection } from "../../src/features/analysis/analysis-projection";
import { productTaskSchema } from "../../src/lib/schemas/product-api";

const correlationId = "22222222-2222-5222-8222-222222222222";

describe("analysis projection", () => {
  it("renders typed market and Web evidence as readable product content", () => {
    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(successTask()),
    }));

    expect(html).toContain("市场与研究证据");
    expect(html).toContain("市场摘要");
    expect(html).toContain("标记价 67,250.50 · 指数价 67,198.25 · 资金费率 0.01% · 未平仓量 48,210.75");
    expect(html).toContain("最新成交");
    expect(html).toContain("67,248.20");
    expect(html).toContain("Fed calendar keeps event risk elevated");
    expect(html).toContain("OpenAI Web Search");
    expect(html).toContain("发布时间");
    expect(html).toContain("抓取时间");
    expect(html).toContain("A scheduled policy speech may lift intraday volatility.");
    expect(html).toContain('href="https://example.com/markets/fed-calendar"');
    expect(html).toContain('dateTime="2026-07-13T08:28:00Z"');
    expect(html).not.toContain("content_hash");
    expect(html).not.toContain("parser_version");
    expect(html).not.toContain("BTC macro event risk");
  });

  it("labels DDGS automatic metasearch provenance without claiming DuckDuckGo", () => {
    const payload = successTask();
    payload.web_evidence[0].source = "ddgs_metasearch";
    payload.web_evidence[0].parser_version = "ddgs-metasearch-v1";
    Object.assign(payload.artifact, {
      provenance: {
        market_provider: "okx",
        search_provider: "ddgs_metasearch",
        search_parser_version: "ddgs-metasearch-v1",
        model_provider: "openai-compatible",
        model_name: "gpt-5.5",
        model_endpoint_host: null,
        model_audits: [],
      },
    });

    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("DDGS 元搜索");
    expect(html).toContain("ddgs-metasearch-v1");
    expect(html).not.toContain("DuckDuckGo");
  });

  it("renders typed unavailable capabilities without raw machine codes", () => {
    const payload = successTask();
    payload.artifact.analysis.unavailable_data = ["vix", "dxy"];

    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("VIX 波动率、美元指数 DXY");
    expect(html).not.toContain(">vix<");
    expect(html).not.toContain(">dxy<");
  });

  it("states research failure honestly while preserving the earlier artifact as history", () => {
    const payload = successTask();
    payload.status = "failed";
    payload.errors = [{
      code: "research_unavailable",
      message: "检索服务没有返回可验证来源，当前未生成分析结果。",
      retryable: true,
      correlation_id: correlationId,
    }];
    payload.web_evidence = [];
    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("研究检索不可用");
    expect(html).toContain(correlationId);
    expect(html).toContain("本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。");
    expect(html).toContain("本次检索未返回可验证来源");
    expect(html).toContain("历史成功报告");
    expect(html).toContain("不代表本次运行的结果");
    expect(html).toContain("原建议：开多");
    expect(html).not.toContain("必要证据完整");
  });

  it("renders the allowlisted provider diagnostics instead of hiding the root error", () => {
    const payload = {
      ...successTask(),
      status: "failed",
      artifact: null,
      errors: [{
        code: "research_unavailable",
        message: "检索服务没有返回可验证来源，当前未生成分析结果。",
        retryable: true,
        correlation_id: correlationId,
        provider: "builtin_web_search",
        error_type: "UnverifiedServerToolCall",
        attempt: 3,
      }],
    };

    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("builtin_web_search");
    expect(html).toContain("UnverifiedServerToolCall");
    expect(html).toContain("第 3 次尝试");
  });

  it("renders preserved evidence without claiming Web Search is unavailable", () => {
    const payload = {
      ...successTask(),
      status: "failed",
      artifact: null,
      errors: [{
        code: "research_unavailable",
        message: "检索服务没有返回可验证来源，当前未生成分析结果。",
        retryable: true,
        correlation_id: correlationId,
      }],
    };

    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("后续研究检索未完成");
    expect(html).toContain("本次运行已保留 1 条可验证 Web 来源");
    expect(html).toContain("已保留 1 条来源，研究未完成");
    expect(html).toContain("Fed calendar keeps event risk elevated");
    expect(html).not.toContain("检索不可用");
    expect(html).not.toContain("本次检索未返回可验证来源");
  });

  it("renders both layers of a failed market fallback", () => {
    const payload = {
      ...successTask(),
      status: "failed",
      artifact: null,
      errors: [{
        code: "provider_unavailable",
        message: "Market data provider failed.",
        retryable: true,
        correlation_id: correlationId,
        provider: "builtin_web_search",
        error_type: "SearchEvidenceUnavailable",
        endpoint: "web_search_market",
        fallback_from: "okx",
        primary_attempt: 3,
      }],
    };

    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("市场数据与后备检索均失败");
    expect(html).toContain("首选数据源");
    expect(html).toContain("okx");
    expect(html).toContain("首选源尝试");
    expect(html).toContain("第 3 次尝试");
    expect(html).toContain("后备 Provider");
    expect(html).toContain("builtin_web_search");
    expect(html).toContain("失败阶段");
    expect(html).toContain("web_search_market");
  });

  it("keeps database rollback failures actionable while collapsing raw diagnostics", () => {
    const payload = {
      ...successTask(),
      status: "failed",
      artifact: null,
      errors: [{
        code: "terminal_projection_unavailable",
        message: "The terminal Product projection could not be committed.",
        retryable: true,
        correlation_id: correlationId,
        error_type: "DatabaseOperationalError",
        attempt: 3,
      }],
    };

    const html = renderToStaticMarkup(createElement(AnalysisProjection, {
      task: productTaskSchema.parse(payload),
    }));

    expect(html).toContain("最终结果暂时不可用");
    expect(html).toContain("系统已回滚未完成的写入，没有留下部分报告");
    expect(html).toContain("请点击“重新分析”重试");
    expect(html).toContain("<details");
    expect(html).toContain("<summary>查看失败诊断</summary>");
    expect(html).toMatch(/<details[^>]*>[\s\S]*terminal_projection_unavailable[\s\S]*DatabaseOperationalError[\s\S]*<\/details>/);
    expect(html).not.toContain("<h2>terminal_projection_unavailable</h2>");
  });

  it("renders retryable failures as a real button only when retry is operable", () => {
    const payload = {
      ...successTask(),
      status: "failed",
      errors: [{
        code: "search_timeout",
        message: "搜索服务超时。",
        retryable: true,
        correlation_id: correlationId,
      }],
      artifact: null,
    };
    const task = productTaskSchema.parse(payload);

    const actionableHtml = renderToStaticMarkup(createElement(AnalysisProjection, {
      task,
      onRetry: () => undefined,
      retrying: false,
    }));
    expect(actionableHtml).toMatch(/<button[^>]*type="button"[^>]*>/);
    expect(actionableHtml).toContain("重新分析");
    expect(actionableHtml).not.toContain("retry-label");

    const unavailableHtml = renderToStaticMarkup(createElement(AnalysisProjection, { task }));
    expect(unavailableHtml).not.toContain("重新分析");
    expect(unavailableHtml).not.toContain("retry-label");
  });
});

function successTask() {
  return {
    task_id: "task-research-content",
    correlation_id: correlationId,
    status: "succeeded",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    completed_at: "2026-07-13T08:30:00Z",
    errors: [] as Array<{
      code: string;
      message: string;
      retryable: boolean;
      correlation_id: string;
    }>,
    agent_stream: null,
    market_snapshot: {
      symbol: "BTC-USDT-SWAP",
      fetched_at: "2026-07-13T08:29:00Z",
      source_level: "exchange_native",
      ticker: {
        last: "67248.2",
        bid: "67247.9",
        ask: "67248.4",
        volume_24h: "18750.25",
      },
      mark_price: "67250.5",
      index_price: "67198.25",
      funding_rate: "0.0001",
      open_interest: "48210.75",
      order_book: {
        bids: [{ price: "67247.9", size: "2.4" }],
        asks: [{ price: "67248.4", size: "1.8" }],
      },
      candles: [{
        timestamp: "2026-07-13T08:00:00Z",
        open: "67150",
        high: "67310",
        low: "67090",
        close: "67248.2",
        volume: "412.8",
      }],
    },
    web_evidence: [{
      query: "BTC macro event risk",
      final_url: "https://example.com/markets/fed-calendar",
      redirect_chain: [],
      http_status: 200,
      fetched_at: "2026-07-13T08:28:00Z",
      published_at: "2026-07-13T07:45:00Z",
      content_hash: "a".repeat(64),
      parser_version: "openai-responses-citation-v1",
      title: "Fed calendar keeps event risk elevated",
      author: "Markets desk",
      source: "openai_web_search",
      excerpt: "A scheduled policy speech may lift intraday volatility.",
      evidence_relation: "supports",
    }],
    artifact: {
      artifact_type: "analysis_report",
      schema_version: "1.0",
      content_version: 1,
      status: "committed",
      analysis: {
        regime: "risk_on",
        factor_scores: { momentum: 2 },
        total_score: 2,
        main_action: "open_long",
        instrument: "BTC-USDT-SWAP",
        horizon: "4h",
        reference_price: "67250.5",
        entry_trigger: "67400",
        stop_price: "65800",
        target_1: "68800",
        target_2: "70100",
        probability: 0.68,
        position_size_class: "light",
        max_leverage: 2,
        risk_pct: "0.01",
        root_cause_chain: ["Momentum improved"],
        why_not_opposite: "Short momentum lacks confirmation.",
        invalidation: "A 4h close below 65800 invalidates the setup.",
        unavailable_data: [] as string[],
        manual_execution_required: true,
        expires_in_seconds: 14400,
      },
      evidence_verdict: {
        sufficient: true,
        confidence_cap: 0.72,
        missing_required: [] as string[],
        missing_optional: [],
        warnings: [],
      },
      risk_verdict: {
        allowed: true,
        blocked_reasons: [] as string[],
        warnings: [],
        confidence_cap: 0.7,
      },
      source_references: ["https://example.com/markets/fed-calendar"],
    },
  };
}
