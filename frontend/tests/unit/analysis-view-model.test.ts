import { describe, expect, it } from "vitest";

import { productTaskSchema } from "../../src/lib/schemas/product-api";
import { toAnalysisViewModel } from "../../src/features/analysis/analysis-view-model";

describe("analysis view model", () => {
  it.each([
    ["queued", "已排队", "pending"],
    ["running", "分析中", "active"],
    ["waiting_human", "等待人工确认", "warning"],
    ["failed", "分析失败", "danger"],
    ["blocked", "已被风险门禁阻断", "danger"],
    ["succeeded", "分析完成", "success"],
    ["cancelled", "已取消", "neutral"],
  ] as const)("maps %s into a readable status", (status, label, tone) => {
    const task = productTaskSchema.parse(status === "succeeded" ? successTask() : baseTask(status));
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:00:00Z"));

    expect(viewModel.status.label).toBe(label);
    expect(viewModel.status.tone).toBe(tone);
  });

  it.each([
    ["provider_unavailable", "行情提供方暂时不可用", "外部数据服务失败"],
    ["search_timeout", "搜索服务超过时间限制", "信息检索失败"],
    ["model_invalid_output", "模型未返回有效分析", "分析模型失败"],
  ])("keeps %s failures readable and visible", (code, message, title) => {
    const task = productTaskSchema.parse({
      ...baseTask("failed"),
      errors: [{ code, message, retryable: true }],
    });
    const viewModel = toAnalysisViewModel(task);

    expect(viewModel.failure?.title).toBe(title);
    expect(viewModel.failure?.message).toBe(message);
    expect(viewModel.failure?.retryable).toBe(true);
  });

  it("projects the decision, evidence, risk, and source links without raw payloads", () => {
    const task = productTaskSchema.parse(successTask());
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:30:00Z"));

    expect(viewModel.result).toMatchObject({
      state: "committed",
      actionable: true,
      action: "开多",
      reference: 67250.5,
      entry: 67400,
      stop: 65800,
      targets: [68800, 70100],
      probabilityPercent: 68,
      evidence: { sufficient: true, confidenceCapPercent: 72 },
      risk: { allowed: true, maxLeverage: 2, riskPercent: 1 },
      unavailableData: ["precise CVD", "liquidation heatmap"],
      validity: {
        expiresInSeconds: 14400,
        expiresAt: "2026-07-13T12:30:00.000Z",
        remainingSeconds: 10800,
        expired: false,
      },
    });
    expect(viewModel.result?.sources).toHaveLength(2);
  });

  it("projects typed market context and source metadata into display-ready research content", () => {
    const projection = successTask();
    Object.assign(projection, researchProjection());
    const task = productTaskSchema.parse(projection);

    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:30:00Z"));

    expect(viewModel.research).toMatchObject({
      state: "available",
      marketSnapshot: {
        symbol: "BTC-USDT-SWAP",
        provider: "交易所原生",
        fetchedAt: "2026-07-13T08:29:00Z",
        summary: "标记价 67,250.50 · 指数价 67,198.25 · 资金费率 0.01% · 未平仓量 48,210.75",
      },
      webEvidence: [{
        title: "Fed calendar keeps event risk elevated",
        provider: "OpenAI Web Search",
        href: "https://example.com/markets/fed-calendar",
        fetchedAt: "2026-07-13T08:28:00Z",
        publishedAt: "2026-07-13T07:45:00Z",
        summary: "A scheduled policy speech may lift intraday volatility.",
        author: "Markets desk",
      }],
    });
    expect(viewModel.research.marketSnapshot?.metrics).toEqual([
      { label: "最新成交", value: "67,248.20" },
      { label: "最优买价", value: "67,247.90" },
      { label: "最优卖价", value: "67,248.40" },
      { label: "24h 成交量", value: "18,750.25" },
    ]);
  });

  it("aligns report references with typed Web evidence without inventing verification", () => {
    const projection = successTask();
    const research = researchProjection();
    research.web_evidence[0].title = research.web_evidence[0].final_url;
    Object.assign(projection, research);
    projection.artifact.source_references = [
      research.web_evidence[0].final_url,
      "https://unmatched.example.net/reports/macro-note",
    ];

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.result?.sources).toEqual([
      {
        label: "example.com",
        href: "https://example.com/markets/fed-calendar",
        provider: "OpenAI Web Search",
        relation: "supports",
        publishedAt: "2026-07-13T07:45:00Z",
        fetchedAt: "2026-07-13T08:28:00Z",
        evidenceMatched: true,
      },
      {
        label: "unmatched.example.net",
        href: "https://unmatched.example.net/reports/macro-note",
        provider: null,
        relation: null,
        publishedAt: null,
        fetchedAt: null,
        evidenceMatched: false,
      },
    ]);
  });

  it("keeps an earlier committed artifact readable but non-actionable when research now fails", () => {
    const projection = successTask();
    projection.status = "failed";
    projection.errors = [{
      code: "research_unavailable",
      message: "检索服务没有返回可验证来源，当前未生成分析结果。",
      retryable: true,
    }];
    Object.assign(projection, {
      market_snapshot: researchProjection().market_snapshot,
      web_evidence: [],
    });
    const task = productTaskSchema.parse(projection);

    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T13:00:00Z"));

    expect(viewModel.status).toMatchObject({
      value: "failed",
      label: "分析失败",
      expired: false,
    });
    expect(viewModel.failure).toMatchObject({
      title: "研究检索不可用",
      code: "research_unavailable",
      explanation: "本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。历史成功报告仍保留，仅供回看。",
    });
    expect(viewModel.research).toMatchObject({
      state: "unavailable",
      webEvidence: [],
    });
    expect(viewModel.result).toMatchObject({
      state: "historical",
      actionable: false,
      action: "开多",
    });
  });

  it("does not claim a historical report exists when a failed task has no artifact", () => {
    const projection = {
      ...successTask(),
      status: "failed",
      artifact: null,
      errors: [{
        code: "research_unavailable",
        message: "检索服务没有返回可验证来源，当前未生成分析结果。",
        retryable: false,
      }],
    };

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.failure?.explanation).toBe(
      "本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。",
    );
  });

  it("keeps safe provider diagnostics visible on a research failure", () => {
    const projection = {
      ...successTask(),
      status: "failed",
      artifact: null,
      errors: [{
        code: "research_unavailable",
        message: "检索服务没有返回可验证来源，当前未生成分析结果。",
        retryable: true,
        provider: "builtin_web_search",
        error_type: "UnverifiedServerToolCall",
        attempt: 3,
      }],
    };

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.failure).toMatchObject({
      provider: "builtin_web_search",
      errorType: "UnverifiedServerToolCall",
      attempt: 3,
    });
  });

  it("keeps backend-valid sparse evidence readable with honest display fallbacks", () => {
    const projection = successTask();
    const research = researchProjection();
    Object.assign(research.web_evidence[0], {
      title: "  ",
      author: "",
      source: "",
      excerpt: "",
      evidence_relation: "",
    });
    Object.assign(projection, research);

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.research.webEvidence[0]).toMatchObject({
      title: "未命名来源",
      provider: "未知 Provider",
      summary: "该来源未提供摘要。",
      author: null,
      relation: "关系未标注",
    });
  });

  it.each([
    ["running", "draft"],
    ["running", "streaming"],
    ["failed", "failed"],
  ] as const)("never projects a %s task with a %s artifact as a result", (taskStatus, artifactStatus) => {
    const projection = successTask();
    projection.status = taskStatus;
    projection.artifact.status = artifactStatus;
    const task = productTaskSchema.parse(projection);
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:30:00Z"));

    expect(viewModel.result).toBeNull();
  });

  it("surfaces blocked draft risk and evidence reasons without projecting committed advice", () => {
    const task = productTaskSchema.parse(blockedDraftTask());
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:30:00Z"));

    expect(viewModel.result).toBeNull();
    expect(viewModel.incompleteMessage).toContain("未提交");
    expect(viewModel.incompleteMessage).toContain("evidence.insufficient:order_book");
    expect(viewModel.incompleteMessage).toContain("order_book");
  });

  it("marks a committed result expired at its derived validity boundary", () => {
    const task = productTaskSchema.parse(successTask());
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T12:30:00Z"));

    expect(viewModel.status).toMatchObject({
      label: "分析已过期",
      tone: "danger",
      expired: true,
    });
    expect(viewModel.result).toMatchObject({
      state: "expired",
      actionable: false,
      validity: {
        expiresAt: "2026-07-13T12:30:00.000Z",
        remainingSeconds: 0,
        expired: true,
      },
    });
  });
});

function baseTask(status: string) {
  return {
    task_id: `task-${status}`,
    status,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    artifact: null,
    errors: [] as Array<{ code: string; message: string; retryable: boolean }>,
  };
}

function successTask() {
  return {
    ...baseTask("succeeded"),
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
        unavailable_data: ["precise CVD", "liquidation heatmap"],
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
      source_references: [
        "https://example.com/market/btc",
        "https://example.com/macro/fed",
      ],
    },
  };
}

function blockedDraftTask() {
  const task = successTask();
  task.status = "blocked";
  task.artifact.status = "draft";
  task.artifact.evidence_verdict.sufficient = false;
  task.artifact.evidence_verdict.confidence_cap = 0;
  task.artifact.evidence_verdict.missing_required = ["order_book"];
  task.artifact.risk_verdict.allowed = false;
  task.artifact.risk_verdict.confidence_cap = 0;
  task.artifact.risk_verdict.blocked_reasons = ["evidence.insufficient:order_book"];
  return task;
}

function researchProjection() {
  return {
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
      source: "openai_builtin_web_search",
      excerpt: "A scheduled policy speech may lift intraday volatility.",
      evidence_relation: "supports",
    }],
  };
}
