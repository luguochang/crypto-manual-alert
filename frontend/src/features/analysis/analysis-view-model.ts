import type {
  MarketSnapshot,
  ProductError,
  ProductTask,
  RunStatus,
  WebEvidence,
} from "@/lib/schemas/product-api";

export type StatusTone = "pending" | "active" | "warning" | "danger" | "success" | "neutral";

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

export interface AnalysisResultViewModel {
  state: "committed" | "historical" | "expired";
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
  sources: AnalysisSourceViewModel[];
}

export interface MarketSnapshotViewModel {
  symbol: string;
  provider: string;
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
  state: "available" | "collecting" | "unavailable" | "empty";
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
    tone: "danger",
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

export function toAnalysisViewModel(task: ProductTask, now = new Date()): AnalysisViewModel {
  const artifact = task.artifact;
  const committedArtifact = artifact?.status === "committed" ? artifact : null;
  const validity = committedArtifact
    ? toValidity(
        task.completed_at ?? task.created_at,
        committedArtifact.analysis.expires_in_seconds,
        now,
      )
    : null;
  const expired = task.status === "succeeded" && (validity?.expired ?? false);
  const status: AnalysisStatusViewModel = expired
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
      ? toFailure(task.errors[0], task.status, task.artifact?.status === "committed")
      : null,
    research: toResearch(task),
    result: committedArtifact && validity
      ? {
          state: task.status !== "succeeded" ? "historical" : expired ? "expired" : "committed",
          actionable: task.status === "succeeded" && !expired,
          action: actionLabels[committedArtifact.analysis.main_action] ?? committedArtifact.analysis.main_action,
          reference: committedArtifact.analysis.reference_price,
          entry: committedArtifact.analysis.entry_trigger,
          stop: committedArtifact.analysis.stop_price,
          targets: [committedArtifact.analysis.target_1, committedArtifact.analysis.target_2].filter(
            (value): value is number => value !== null,
          ),
          probabilityPercent: Math.round(committedArtifact.analysis.probability * 100),
          horizon: committedArtifact.analysis.horizon,
          instrument: committedArtifact.analysis.instrument,
          regime: committedArtifact.analysis.regime,
          rationale: committedArtifact.analysis.root_cause_chain,
          whyNotOpposite: committedArtifact.analysis.why_not_opposite,
          invalidation: committedArtifact.analysis.invalidation,
          unavailableData: committedArtifact.analysis.unavailable_data,
          validity,
          evidence: {
            sufficient: committedArtifact.evidence_verdict.sufficient,
            confidenceCapPercent: Math.round(committedArtifact.evidence_verdict.confidence_cap * 100),
            missingRequired: committedArtifact.evidence_verdict.missing_required,
            missingOptional: committedArtifact.evidence_verdict.missing_optional,
            warnings: committedArtifact.evidence_verdict.warnings,
          },
          risk: {
            allowed: committedArtifact.risk_verdict.allowed,
            confidenceCapPercent: Math.round(committedArtifact.risk_verdict.confidence_cap * 100),
            maxLeverage: committedArtifact.analysis.max_leverage,
            riskPercent: committedArtifact.analysis.risk_pct * 100,
            positionSize: committedArtifact.analysis.position_size_class,
            blockedReasons: committedArtifact.risk_verdict.blocked_reasons,
            warnings: committedArtifact.risk_verdict.warnings,
          },
          sources: toAnalysisSources(committedArtifact.source_references, task.web_evidence),
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
): AnalysisFailureViewModel {
  const normalizedCode = error.code.toLowerCase();
  let title = status === "blocked" ? "风险门禁已阻断" : "分析服务失败";
  let explanation: string | null = null;

  if (normalizedCode === "research_unavailable") {
    title = "研究检索不可用";
    explanation = hasHistoricalArtifact
      ? "本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。历史成功报告仍保留，仅供回看。"
      : "本次运行没有获得可验证的 Web 来源，因此没有生成新的分析建议。";
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
    message: error.message,
    code: error.code,
    retryable: error.retryable,
    explanation,
    provider: error.provider,
    errorType: error.error_type,
    attempt: error.attempt,
  };
}

function toResearch(task: ProductTask): AnalysisResearchViewModel {
  const researchUnavailable = task.errors.some(
    (error) => error.code.toLowerCase() === "research_unavailable",
  );
  const webEvidence = task.web_evidence.map(toWebEvidence);
  const state: AnalysisResearchViewModel["state"] = researchUnavailable
    ? "unavailable"
    : webEvidence.length > 0
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
  ].filter((item): item is { label: string; value: string } => item !== null);
  const summary = [
    summaryPart("标记价", snapshot.mark_price, formatMarketNumber),
    summaryPart("指数价", snapshot.index_price, formatMarketNumber),
    summaryPart("资金费率", snapshot.funding_rate, formatFundingRate),
    summaryPart("未平仓量", snapshot.open_interest, formatMarketNumber),
  ].filter((item): item is string => item !== null);

  return {
    symbol: snapshot.symbol,
    provider: snapshot.source_level === "exchange_native" ? "交易所原生" : snapshot.source_level,
    fetchedAt: snapshot.fetched_at,
    summary: summary.length > 0
      ? summary.join(" · ")
      : `${snapshot.symbol} 市场快照已获取`,
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
  return value === null || value === undefined ? null : { label, value: formatter(value) };
}

function summaryPart(
  label: string,
  value: number | null | undefined,
  formatter: (value: number) => string,
) {
  return value === null || value === undefined ? null : `${label} ${formatter(value)}`;
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
    openai_web_search: "OpenAI Web Search",
    tavily: "Tavily",
    tavily_search: "Tavily",
  };
  return knownProviders[normalized.toLowerCase()] ?? normalized;
}
