import type {
  MarketSnapshot,
  ProductError,
  ProductTask,
  RunStatus,
  WebEvidence,
} from "@/lib/schemas/product-api";

export type StatusTone = "pending" | "active" | "warning" | "blocked" | "danger" | "success" | "neutral";

export interface AnalysisStatusViewModel {
  value: RunStatus;
  label: string;
  description: string;
  tone: StatusTone;
  terminal: boolean;
  expired: boolean;
}

export interface AnalysisFailureViewModel {
  title: string;
  message: string;
  code: string;
  retryable: boolean;
  explanation: string | null;
  provider: string | null;
  errorType: string | null;
  attempt: number | null;
  endpoint: string | null;
  fallbackFrom: string | null;
  primaryAttempt: number | null;
  correlationId: string;
}

export interface AnalysisSourceViewModel {
  label: string;
  href: string;
  provider: string | null;
  relation: string | null;
  publishedAt: string | null;
  fetchedAt: string | null;
  evidenceMatched: boolean;
}

export interface ModelExecutionAuditViewModel {
  promptVersion: string;
  callCount: number;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  latencyMs: number;
  observationIds: string[];
}

export interface AnalysisResultViewModel {
  state: "committed" | "blocked" | "historical" | "expired";
  actionable: boolean;
  action: string;
  reference: number;
  entry: number | null;
  stop: number | null;
  targets: number[];
  probabilityPercent: number;
  horizon: string;
  instrument: string;
  regime: string;
  rationale: string[];
  whyNotOpposite: string;
  invalidation: string;
  unavailableData: string[];
  validity: {
    expiresInSeconds: number;
    expiresAt: string;
    remainingSeconds: number;
    expired: boolean;
  };
  evidence: {
    sufficient: boolean;
    confidenceCapPercent: number;
    missingRequired: string[];
    missingOptional: string[];
    warnings: string[];
  };
  risk: {
    allowed: boolean;
    confidenceCapPercent: number;
    maxLeverage: number;
    riskPercent: number;
    positionSize: string;
    blockedReasons: string[];
    warnings: string[];
  };
  provenance: {
    marketProvider: string;
    searchProvider: string;
    searchParserVersion: string;
    modelProvider: string;
    modelName: string;
    modelEndpointHost: string | null;
    modelAudits: ModelExecutionAuditViewModel[];
  } | null;
  sources: AnalysisSourceViewModel[];
}

export interface MarketSnapshotViewModel {
  symbol: string;
  sourceLevel: MarketSnapshot["source_level"];
  provider: string;
  disclosure: string | null;
  fetchedAt: string;
  summary: string;
  metrics: Array<{ label: string; value: string }>;
}

export interface WebEvidenceViewModel {
  title: string;
  provider: string;
  href: string;
  fetchedAt: string;
  publishedAt: string | null;
  summary: string;
  author: string | null;
  relation: string;
}

export interface AnalysisResearchViewModel {
  state: "available" | "partial" | "collecting" | "unavailable" | "empty";
  marketSnapshot: MarketSnapshotViewModel | null;
  webEvidence: WebEvidenceViewModel[];
}

export interface AnalysisViewModel {
  taskId: string;
  symbol: string;
  horizon: string;
  createdAt: string;
  completedAt: string | null;
  status: AnalysisStatusViewModel;
  failure: AnalysisFailureViewModel | null;
  research: AnalysisResearchViewModel;
  result: AnalysisResultViewModel | null;
  incompleteMessage: string | null;
}

const statusMetadata: Record<RunStatus, Omit<AnalysisStatusViewModel, "value" | "expired">> = {
  queued: {
    label: "已排队",
    description: "请求已接收，正在等待分析资源。",
    tone: "pending",
    terminal: false,
  },
  running: {
    label: "分析中",
    description: "正在获取市场、检索与模型分析结果。",
    tone: "active",
    terminal: false,
  },
  waiting_human: {
    label: "等待人工确认",
    description: "分析已暂停，等待人工确认后继续。",
    tone: "warning",
    terminal: false,
  },
  succeeded: {
    label: "分析完成",
    description: "分析结果已写入产品投影。",
    tone: "success",
    terminal: true,
  },
  blocked: {
    label: "已被风险门禁阻断",
    description: "风险或证据门禁阻止了当前计划。",
    tone: "blocked",
    terminal: true,
  },
  failed: {
    label: "分析失败",
    description: "外部服务或分析过程未能完成。",
    tone: "danger",
    terminal: true,
  },
  cancelled: {
    label: "已取消",
    description: "本次分析已取消，历史记录仍保留。",
    tone: "neutral",
    terminal: true,
  },
};

const actionLabels: Record<string, string> = {
  open_long: "开多",
  open_short: "开空",
  hold_long: "持有多单",
  hold_short: "持有空单",
  close_long: "平多",
  close_short: "平空",
  flip_long_to_short: "由多转空",
  flip_short_to_long: "由空转多",
  trigger_long: "条件触发做多",
  trigger_short: "条件触发做空",
  no_trade: "暂不操作",
};

const dataAvailabilityLabels: Record<string, string> = {
  exchange_native_market_data: "交易所原生行情",
  ticker: "最新成交价",
  mark_price: "标记价格",
  index_price: "指数价格",
  order_book: "订单簿",
  candles: "K 线",
  funding_rate: "资金费率",
  open_interest: "未平仓量",
  vix: "VIX 波动率",
  real_yield_10y: "美国 10 年期实际利率",
  dxy: "美元指数 DXY",
  macro_event_scan: "宏观事件扫描",
  verified_web_evidence: "可验证 Web 来源",
};

function dataAvailabilityLabel(value: string): string {
  return dataAvailabilityLabels[value] ?? value;
}

export function toAnalysisViewModel(task: ProductTask, now = new Date()): AnalysisViewModel {
  const artifact = task.artifact;
  const committedArtifact = artifact?.status === "committed" ? artifact : null;
  const blockedArtifact = task.status === "blocked" && artifact?.status === "draft" ? artifact : null;
  const displayArtifact = committedArtifact ?? blockedArtifact;
  const validity = displayArtifact
    ? toValidity(
        task.completed_at ?? task.created_at,
        displayArtifact.analysis.expires_in_seconds,
        now,
      )
    : null;
  const expired = task.status === "succeeded" && (validity?.expired ?? false);
  const resolvedHistoricalReview = task.status === "waiting_human"
    && task.pending_interrupts === null
    && task.projection_scope?.mode === "selected_run";
  const status: AnalysisStatusViewModel = resolvedHistoricalReview
    ? {
        value: task.status,
        label: "历史审核节点",
        description: "该次审核已结束，后续运行状态请以当前任务为准。",
        tone: "neutral",
        terminal: true,
        expired: false,
      }
    : expired
    ? {
        value: task.status,
        label: "分析已过期",
        description: "报告有效期已结束，不可作为当前交易计划。",
        tone: "danger",
        terminal: true,
        expired: true,
      }
    : {
        value: task.status,
        ...statusMetadata[task.status],
        expired: false,
      };

  return {
    taskId: task.task_id,
    symbol: task.symbol,
    horizon: task.horizon,
    createdAt: task.created_at,
    completedAt: task.completed_at,
    status,
    failure: task.errors[0]
      ? toFailure(
          task.errors[0],
          task.status,
          task.artifact?.status === "committed",
          task.web_evidence.filter(isEffectiveWebEvidence).length,
        )
      : null,
    research: toResearch(task),
    result: displayArtifact && validity
      ? {
          state: blockedArtifact
            ? "blocked"
            : task.status !== "succeeded"
              ? "historical"
              : expired
                ? "expired"
                : "committed",
          actionable: task.status === "succeeded" && !expired,
          action: actionLabels[displayArtifact.analysis.main_action] ?? displayArtifact.analysis.main_action,
          reference: displayArtifact.analysis.reference_price,
          entry: displayArtifact.analysis.entry_trigger,
          stop: displayArtifact.analysis.stop_price,
          targets: [displayArtifact.analysis.target_1, displayArtifact.analysis.target_2].filter(
            (value): value is number => value !== null,
          ),
          probabilityPercent: Math.round(displayArtifact.analysis.probability * 100),
          horizon: displayArtifact.analysis.horizon,
          instrument: displayArtifact.analysis.instrument,
          regime: displayArtifact.analysis.regime,
          rationale: displayArtifact.analysis.root_cause_chain,
          whyNotOpposite: displayArtifact.analysis.why_not_opposite,
          invalidation: displayArtifact.analysis.invalidation,
          unavailableData: displayArtifact.analysis.unavailable_data.map(dataAvailabilityLabel),
          validity,
          evidence: {
            sufficient: displayArtifact.evidence_verdict.sufficient,
            confidenceCapPercent: Math.round(displayArtifact.evidence_verdict.confidence_cap * 100),
            missingRequired: displayArtifact.evidence_verdict.missing_required,
            missingOptional: displayArtifact.evidence_verdict.missing_optional,
            warnings: displayArtifact.evidence_verdict.warnings,
          },
          risk: {
            allowed: displayArtifact.risk_verdict.allowed,
            confidenceCapPercent: Math.round(displayArtifact.risk_verdict.confidence_cap * 100),
            maxLeverage: displayArtifact.analysis.max_leverage,
            riskPercent: displayArtifact.analysis.risk_pct * 100,
            positionSize: displayArtifact.analysis.position_size_class,
            blockedReasons: displayArtifact.risk_verdict.blocked_reasons,
            warnings: displayArtifact.risk_verdict.warnings,
          },
          provenance: displayArtifact.provenance
            ? {
                marketProvider: displayArtifact.provenance.market_provider,
                searchProvider: displayArtifact.provenance.search_provider,
                searchParserVersion: displayArtifact.provenance.search_parser_version,
                modelProvider: displayArtifact.provenance.model_provider,
                modelName: displayArtifact.provenance.model_name,
                modelEndpointHost: displayArtifact.provenance.model_endpoint_host,
                modelAudits: displayArtifact.provenance.model_audits.map((audit) => ({
                  promptVersion: audit.prompt_version,
                  callCount: audit.call_count,
                  inputTokens: audit.input_tokens,
                  outputTokens: audit.output_tokens,
                  totalTokens: audit.total_tokens,
                  latencyMs: audit.latency_ms,
                  observationIds: audit.observation_ids,
                })),
              }
            : null,
          sources: toAnalysisSources(displayArtifact.source_references, task.web_evidence),
        }
      : null,
    incompleteMessage: toIncompleteMessage(task),
  };
}

function toValidity(createdAt: string, expiresInSeconds: number, now: Date) {
  const expiresAtMilliseconds = Date.parse(createdAt) + expiresInSeconds * 1000;
  const remainingSeconds = Math.max(0, Math.ceil((expiresAtMilliseconds - now.getTime()) / 1000));
  const expired = now.getTime() >= expiresAtMilliseconds;

  return {
    expiresInSeconds,
    expiresAt: new Date(expiresAtMilliseconds).toISOString(),
    remainingSeconds,
    expired,
  };
}

function toIncompleteMessage(task: ProductTask): string | null {
  if (task.status === "blocked") {
    const artifact = task.artifact;
    if (artifact?.status === "committed") {
      return "当前运行已被门禁阻断；下方保留的是历史成功报告，不能作为本次建议。";
    }
    const reasons = artifact
      ? [...artifact.risk_verdict.blocked_reasons, ...artifact.evidence_verdict.missing_required]
      : [];
    const uniqueReasons = [...new Set(reasons)];
    const suffix = uniqueReasons.length ? ` 原因：${uniqueReasons.join("；")}。` : "";
    return `分析草稿未提交，不能作为交易建议。${suffix}`;
  }
  if (task.status === "succeeded" && task.artifact?.status !== "committed") {
    return "分析已完成，但结果尚未完整写入。请稍后刷新。";
  }
  return null;
}

function toFailure(
  error: ProductError,
  status: RunStatus,
  hasHistoricalArtifact: boolean,
  verifiedWebEvidenceCount: number,
): AnalysisFailureViewModel {
  const normalizedCode = error.code.toLowerCase();
  let title = status === "blocked" ? "风险门禁已阻断" : "分析服务失败";
  let message = error.message;
  let explanation: string | null = null;

  if (normalizedCode === "research_unavailable") {
    if (verifiedWebEvidenceCount > 0) {
      title = "后续研究检索未完成";
      message = `后续研究检索没有完成，系统未生成新的分析建议；本次运行已保留 ${verifiedWebEvidenceCount} 条可验证 Web 来源。`;
      explanation = hasHistoricalArtifact
        ? "已保留的 Web 来源属于本次运行；历史成功报告仍保留，仅供回看。"
        : "已保留的 Web 来源仍可用于审计本次失败，但不能替代缺失的研究结论。";
    } else {
      title = "研究检索不可用";
      explanation = hasHistoricalArtifact
        ? "本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。历史成功报告仍保留，仅供回看。"
        : "本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。";
    }
  } else if (
    normalizedCode === "provider_unavailable"
    && error.endpoint === "web_search_market"
    && error.fallback_from !== null
  ) {
    title = "市场数据与后备检索均失败";
    message = error.retryable
      ? "交易所行情重试耗尽后仍不可用，后备 Web Search 行情检索也未完成，系统没有生成交易建议。请稍后重新分析。"
      : "交易所行情重试耗尽后仍不可用，后备 Web Search 行情检索也未完成，系统没有生成交易建议。请使用关联 ID 联系支持。";
    explanation = "失败诊断分别保留首选数据源和后备检索阶段，便于定位两层依赖。";
  } else if (normalizedCode === "terminal_projection_unavailable") {
    title = "最终结果暂时不可用";
    explanation = "本次任务未生成可用分析结果；失败诊断中保留了支持排查所需的原始字段。";
    message = error.retryable
      ? "分析执行已结束，但最终结果未能保存，系统已回滚未完成的写入，没有留下部分报告。请点击“重新分析”重试。"
      : "分析执行已结束，但最终结果未能保存，系统已回滚未完成的写入，没有留下部分报告。请稍后刷新，若仍未恢复请联系支持。";
  } else if (["invalid_agent_output", "model_output_mismatch"].includes(normalizedCode)) {
    title = "分析模型失败";
    message = error.retryable
      ? "模型返回内容未通过结构校验，系统没有生成交易建议。请重新分析；若持续失败，请使用关联 ID 联系支持。"
      : "模型返回内容未通过结构校验，系统没有生成交易建议。请使用关联 ID 联系支持。";
  } else if (normalizedCode === "agent_run_error") {
    title = "分析执行失败";
    message = error.retryable
      ? "分析执行未能完成，系统没有生成交易建议。请重新分析；若持续失败，请使用关联 ID 联系支持。"
      : "分析执行未能完成，系统没有生成交易建议。请使用关联 ID 联系支持。";
  } else if (normalizedCode === "agent_server_unavailable") {
    title = "分析执行服务不可用";
    message = error.retryable
      ? "分析执行服务当前不可用，系统没有生成交易建议。请稍后重试；若持续失败，请使用关联 ID 联系支持。"
      : "分析执行服务当前不可用，系统没有生成交易建议。请使用关联 ID 联系支持。";
  } else if (normalizedCode.includes("search") || normalizedCode.includes("research")) {
    title = "信息检索失败";
  } else if (
    normalizedCode.includes("model") ||
    normalizedCode.includes("llm") ||
    normalizedCode.includes("structured_output")
  ) {
    title = "分析模型失败";
  } else if (
    normalizedCode.includes("provider") ||
    normalizedCode.includes("market") ||
    normalizedCode.includes("okx")
  ) {
    title = "外部数据服务失败";
  }

  return {
    title,
    message,
    code: error.code,
    retryable: error.retryable,
    explanation,
    provider: error.provider,
    errorType: error.error_type,
    attempt: error.attempt,
    endpoint: error.endpoint,
    fallbackFrom: error.fallback_from,
    primaryAttempt: error.primary_attempt,
    correlationId: error.correlation_id,
  };
}

function toResearch(task: ProductTask): AnalysisResearchViewModel {
  const researchUnavailable = task.errors.some(
    (error) => error.code.toLowerCase() === "research_unavailable",
  );
  const webEvidence = task.web_evidence.map(toWebEvidence);
  const effectiveEvidenceCount = task.web_evidence.filter(isEffectiveWebEvidence).length;
  const state: AnalysisResearchViewModel["state"] = researchUnavailable
    ? effectiveEvidenceCount > 0
      ? "partial"
      : "unavailable"
    : effectiveEvidenceCount > 0
      ? "available"
      : statusMetadata[task.status].terminal
        ? "empty"
        : "collecting";

  return {
    state,
    marketSnapshot: task.market_snapshot ? toMarketSnapshot(task.market_snapshot) : null,
    webEvidence,
  };
}

function toMarketSnapshot(snapshot: MarketSnapshot): MarketSnapshotViewModel {
  const bestBid = snapshot.ticker?.bid ?? snapshot.order_book?.bids[0]?.price ?? null;
  const bestAsk = snapshot.ticker?.ask ?? snapshot.order_book?.asks[0]?.price ?? null;
  const metrics = [
    metric("最新成交", snapshot.ticker?.last, formatMarketNumber),
    metric("最优买价", bestBid, formatMarketNumber),
    metric("最优卖价", bestAsk, formatMarketNumber),
    metric("24h 成交量", snapshot.ticker?.volume_24h, formatMarketNumber),
  ];
  const summary = [
    summaryPart("标记价", snapshot.mark_price, formatMarketNumber),
    summaryPart("指数价", snapshot.index_price, formatMarketNumber),
    summaryPart("资金费率", snapshot.funding_rate, formatFundingRate),
    summaryPart("未平仓量", snapshot.open_interest, formatMarketNumber),
  ];
  const webSearchFallback = snapshot.source_level === "web_search_verified";

  return {
    symbol: snapshot.symbol,
    sourceLevel: snapshot.source_level,
    provider: marketProviderLabel(snapshot.source_level),
    disclosure: webSearchFallback
      ? "交易所原生行情数据不可用；本次使用了带引用的 Web Search 市场证据。该证据不等同于交易所原生行情，缺失字段按不可用处理。"
      : null,
    fetchedAt: snapshot.fetched_at,
    summary: summary.length > 0
      ? summary.join(" · ")
      : `${snapshot.symbol} 行情字段均不可用`,
    metrics,
  };
}

function toWebEvidence(evidence: WebEvidence): WebEvidenceViewModel {
  const title = evidence.title.trim();
  const summary = evidence.excerpt.trim();
  const author = evidence.author?.trim() || null;
  const relation = evidence.evidence_relation.trim();

  return {
    title: displaySourceTitle(title, evidence.final_url),
    provider: providerLabel(evidence.source),
    href: evidence.final_url,
    fetchedAt: evidence.fetched_at,
    publishedAt: evidence.published_at,
    summary: summary || "该来源未提供摘要。",
    author,
    relation: relation || "关系未标注",
  };
}

function isEffectiveWebEvidence(evidence: WebEvidence): boolean {
  return evidence.evidence_relation.trim().toLowerCase() !== "excluded";
}

function toAnalysisSources(sourceReferences: string[], webEvidence: WebEvidence[]): AnalysisSourceViewModel[] {
  const evidenceByUrl = new Map(
    webEvidence.map((evidence) => [canonicalSourceUrl(evidence.final_url), evidence]),
  );

  return sourceReferences.map((href) => {
    const evidence = evidenceByUrl.get(canonicalSourceUrl(href));
    if (!evidence) {
      return {
        label: sourceHostname(href),
        href,
        provider: null,
        relation: null,
        publishedAt: null,
        fetchedAt: null,
        evidenceMatched: false,
      };
    }

    return {
      label: displaySourceTitle(evidence.title, evidence.final_url),
      href,
      provider: providerLabel(evidence.source),
      relation: evidence.evidence_relation.trim() || "关系未标注",
      publishedAt: evidence.published_at,
      fetchedAt: evidence.fetched_at,
      evidenceMatched: true,
    };
  });
}

function displaySourceTitle(title: string, href: string): string {
  const normalizedTitle = title.trim();
  if (!normalizedTitle) return "未命名来源";
  return canonicalSourceUrl(normalizedTitle) === canonicalSourceUrl(href)
    ? sourceHostname(href)
    : normalizedTitle;
}

function canonicalSourceUrl(value: string): string {
  try {
    const url = new URL(value);
    url.hash = "";
    return url.toString();
  } catch {
    return value;
  }
}

function sourceHostname(href: string): string {
  try {
    return new URL(href).hostname || "外部来源";
  } catch {
    return "外部来源";
  }
}

function metric(
  label: string,
  value: number | null | undefined,
  formatter: (value: number) => string,
) {
  return { label, value: value === null || value === undefined ? "不可用" : formatter(value) };
}

function summaryPart(
  label: string,
  value: number | null | undefined,
  formatter: (value: number) => string,
) {
  return `${label} ${value === null || value === undefined ? "不可用" : formatter(value)}`;
}

function marketProviderLabel(sourceLevel: MarketSnapshot["source_level"]): string {
  return ({
    exchange_native: "交易所原生",
    controlled_dependency: "受控依赖",
    web_search_verified: "Web Search 引用证据",
  } as Record<MarketSnapshot["source_level"], string>)[sourceLevel];
}

function formatMarketNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatFundingRate(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  }).format(value);
}

function providerLabel(value: string): string {
  const normalized = value.trim();
  if (!normalized) return "未知 Provider";
  const knownProviders: Record<string, string> = {
    openai_builtin_web_search: "OpenAI Web Search",
    ddgs_metasearch: "DDGS 元搜索",
    openai_web_search: "OpenAI Web Search",
    tavily: "Tavily",
    tavily_search: "Tavily",
  };
  return knownProviders[normalized.toLowerCase()] ?? normalized;
}
