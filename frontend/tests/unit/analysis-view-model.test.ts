import { describe, expect, it } from "vitest";

import { productTaskSchema } from "../../src/lib/schemas/product-api";
import { toAnalysisViewModel } from "../../src/features/analysis/analysis-view-model";

const correlationId = "11111111-1111-5111-8111-111111111111";

describe("analysis view model", () => {
  it.each([
    ["queued", "已排队", "pending"],
    ["running", "分析中", "active"],
    ["waiting_human", "等待人工确认", "warning"],
    ["failed", "分析失败", "danger"],
    ["blocked", "已被风险门禁阻断", "blocked"],
    ["succeeded", "分析完成", "success"],
    ["cancelled", "已取消", "neutral"],
  ] as const)("maps %s into a readable status", (status, label, tone) => {
    const projection = status === "succeeded"
      ? successTask()
      : status === "waiting_human"
        ? waitingTask()
        : baseTask(status);
    const task = productTaskSchema.parse(projection);
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:00:00Z"));

    expect(viewModel.status.label).toBe(label);
    expect(viewModel.status.tone).toBe(tone);
  });

  it("renders a resolved selected-Run review as history rather than an active pause", () => {
    const projection = waitingTask();
    projection.pending_interrupts = null as never;
    Object.assign(projection, {
      projection_scope: {
        mode: "selected_run",
        selected_run_id: "22222222-2222-4222-8222-222222222222",
      },
    });

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.status).toMatchObject({
      label: "历史审核节点",
      tone: "neutral",
      terminal: true,
    });
    expect(viewModel.status.description).toContain("后续运行状态");
  });

  it.each([
    ["provider_unavailable", "行情提供方暂时不可用", "外部数据服务失败"],
    ["search_timeout", "搜索服务超过时间限制", "信息检索失败"],
    ["model_invalid_output", "模型未返回有效分析", "分析模型失败"],
  ])("keeps %s failures readable and visible", (code, message, title) => {
    const task = productTaskSchema.parse({
      ...baseTask("failed"),
      errors: [{ code, message, retryable: true, correlation_id: correlationId }],
    });
    const viewModel = toAnalysisViewModel(task);

    expect(viewModel.failure?.title).toBe(title);
    expect(viewModel.failure?.message).toBe(message);
    expect(viewModel.failure?.retryable).toBe(true);
  });

  it.each([
    [
      "invalid_agent_output",
      "分析模型失败",
      "模型返回内容未通过结构校验，系统没有生成交易建议。请重新分析；若持续失败，请使用关联 ID 联系支持。",
    ],
    [
      "model_output_mismatch",
      "分析模型失败",
      "模型返回内容未通过结构校验，系统没有生成交易建议。请重新分析；若持续失败，请使用关联 ID 联系支持。",
    ],
    [
      "agent_run_error",
      "分析执行失败",
      "分析执行未能完成，系统没有生成交易建议。请重新分析；若持续失败，请使用关联 ID 联系支持。",
    ],
    [
      "agent_server_unavailable",
      "分析执行服务不可用",
      "分析执行服务当前不可用，系统没有生成交易建议。请稍后重试；若持续失败，请使用关联 ID 联系支持。",
    ],
  ])("maps %s into actionable product copy", (code, title, message) => {
    const task = productTaskSchema.parse({
      ...baseTask("failed"),
      errors: [{
        code,
        message: "Provider-owned diagnostic must not become the primary copy.",
        retryable: true,
        correlation_id: correlationId,
      }],
    });

    const viewModel = toAnalysisViewModel(task);

    expect(viewModel.failure).toMatchObject({ title, message, code, correlationId });
  });

  it("translates terminal projection failures without discarding raw support diagnostics", () => {
    const task = productTaskSchema.parse({
      ...baseTask("failed"),
      errors: [{
        code: "terminal_projection_unavailable",
        message: "The terminal Product projection could not be committed.",
        retryable: true,
        correlation_id: correlationId,
        error_type: "DatabaseOperationalError",
        attempt: 3,
      }],
    });

    const viewModel = toAnalysisViewModel(task);

    expect(viewModel.failure).toMatchObject({
      title: "最终结果暂时不可用",
      message: "分析执行已结束，但最终结果未能保存，系统已回滚未完成的写入，没有留下部分报告。请点击“重新分析”重试。",
      code: "terminal_projection_unavailable",
      errorType: "DatabaseOperationalError",
      attempt: 3,
      correlationId,
    });
    expect(viewModel.failure?.message).not.toContain("DatabaseOperationalError");
  });

  it("explains an exhausted exchange path followed by a failed Web Search fallback", () => {
    const task = productTaskSchema.parse({
      ...baseTask("failed"),
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
    });

    const viewModel = toAnalysisViewModel(task);

    expect(viewModel.failure).toMatchObject({
      title: "市场数据与后备检索均失败",
      message: "交易所行情重试耗尽后仍不可用，后备 Web Search 行情检索也未完成，系统没有生成交易建议。请稍后重新分析。",
      provider: "builtin_web_search",
      errorType: "SearchEvidenceUnavailable",
      endpoint: "web_search_market",
      fallbackFrom: "okx",
      primaryAttempt: 3,
    });
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

  it("renders deterministic availability codes as readable product labels", () => {
    const projection = successTask();
    projection.artifact.analysis.unavailable_data = [
      "funding_rate",
      "vix",
      "real_yield_10y",
      "dxy",
      "verified_web_evidence",
    ];

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.result?.unavailableData).toEqual([
      "资金费率",
      "VIX 波动率",
      "美国 10 年期实际利率",
      "美元指数 DXY",
      "可验证 Web 来源",
    ]);
  });

  it("projects model execution audits into readable provenance", () => {
    const projection = successTask();
    Object.assign(projection.artifact, { provenance: {
      market_provider: "okx",
      search_provider: "builtin_web_search",
      search_parser_version: "openai-responses-citation-v1",
      model_provider: "openai-compatible",
      model_name: "gpt-5.5",
      model_endpoint_host: "model.example",
      model_audits: [{
        prompt_version: "research-extraction-v1",
        call_count: 1,
        input_tokens: 120,
        output_tokens: 34,
        total_tokens: 154,
        latency_ms: 842.4,
        observation_ids: ["resp_research_1"],
      }, {
        prompt_version: "market-analysis-v1",
        call_count: 1,
        input_tokens: null,
        output_tokens: null,
        total_tokens: null,
        latency_ms: 1201,
        observation_ids: [],
      }],
    } });

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.result?.provenance?.modelAudits).toEqual([
      {
        promptVersion: "research-extraction-v1",
        callCount: 1,
        inputTokens: 120,
        outputTokens: 34,
        totalTokens: 154,
        latencyMs: 842.4,
        observationIds: ["resp_research_1"],
      },
      {
        promptVersion: "market-analysis-v1",
        callCount: 1,
        inputTokens: null,
        outputTokens: null,
        totalTokens: null,
        latencyMs: 1201,
        observationIds: [],
      },
    ]);
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

  it("does not call an excluded-only evidence set verified research", () => {
    const projection = successTask();
    const research = researchProjection();
    research.web_evidence = research.web_evidence.map((evidence) => ({
      ...evidence,
      evidence_relation: "excluded",
    }));
    Object.assign(projection, research);

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.research).toMatchObject({
      state: "empty",
      webEvidence: [expect.objectContaining({ relation: "excluded" })],
    });
  });

  it("discloses the Web Search fallback and marks missing market fields unavailable", () => {
    const projection = successTask();
    const research = researchProjection();
    research.market_snapshot.source_level = "web_search_verified";
    Object.assign(research.market_snapshot, {
      ticker: null,
      mark_price: null,
      funding_rate: null,
      open_interest: null,
      order_book: null,
    });
    Object.assign(projection, research);

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.research.marketSnapshot).toMatchObject({
      sourceLevel: "web_search_verified",
      provider: "Web Search 引用证据",
      disclosure: "交易所原生行情数据不可用；本次使用了带引用的 Web Search 市场证据。该证据不等同于交易所原生行情，缺失字段按不可用处理。",
      summary: "标记价 不可用 · 指数价 67,198.25 · 资金费率 不可用 · 未平仓量 不可用",
      metrics: [
        { label: "最新成交", value: "不可用" },
        { label: "最优买价", value: "不可用" },
        { label: "最优卖价", value: "不可用" },
        { label: "24h 成交量", value: "不可用" },
      ],
    });
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
      correlation_id: correlationId,
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
        correlation_id: correlationId,
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
        correlation_id: correlationId,
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

  it("keeps verified fallback evidence available when a later research stage fails", () => {
    const projection = {
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
    Object.assign(projection, researchProjection());

    const viewModel = toAnalysisViewModel(productTaskSchema.parse(projection));

    expect(viewModel.failure).toMatchObject({
      title: "后续研究检索未完成",
      message: "后续研究检索没有完成，系统未生成新的分析建议；本次运行已保留 1 条可验证 Web 来源。",
      explanation: "已保留的 Web 来源仍可用于审计本次失败，但不能替代缺失的研究结论。",
    });
    expect(viewModel.research).toMatchObject({
      state: "partial",
      webEvidence: [expect.objectContaining({
        href: "https://example.com/markets/fed-calendar",
      })],
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

  it("renders a blocked draft for audit without projecting actionable advice", () => {
    const task = productTaskSchema.parse(blockedDraftTask());
    const viewModel = toAnalysisViewModel(task, new Date("2026-07-13T09:30:00Z"));

    expect(viewModel.result).toMatchObject({
      state: "blocked",
      actionable: false,
      evidence: {
        sufficient: false,
        missingRequired: ["order_book"],
      },
      risk: {
        allowed: false,
        blockedReasons: ["evidence.insufficient:order_book"],
      },
    });
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
    correlation_id: correlationId,
    status,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    artifact: null,
    errors: [] as Array<{
      code: string;
      message: string;
      retryable: boolean;
      correlation_id: string;
    }>,
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

function waitingTask() {
  const artifact = successTask().artifact;
  artifact.status = "draft";
  return {
    ...baseTask("waiting_human"),
    pending_interrupts: {
      pause_id: "33333333-3333-4333-8333-333333333333",
      pause_version: 1,
      status: "pending",
      expires_at: "2026-07-13T10:00:00Z",
      members: [{
        interrupt_id: "review-waiting-human",
        response_version: 1,
        status: "pending",
        payload: {
          kind: "artifact_review",
          schema_version: "1.0",
          allowed_actions: ["approve", "reject", "edit"],
          review_iteration: 1,
          artifact,
        },
        response: null,
        responded_at: null,
      }],
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
