const PRODUCT_LABELS: Record<string, string> = {
  本地样本: "本地演练",
  "模拟 LLM": "模型链路演练",
  fixture: "演练数据"
};

const ENGINEERING_DETAIL_FALLBACK = "内容已记录，当前摘要不可读";
const INTERNAL_TOKEN_PATTERN = /\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b|\b[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\b/g;
const FULL_INTERNAL_TOKEN_PATTERN = /^(?:[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+|[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)$/;
const SAFE_MARKET_INDICATOR_PATTERN = /^(?:funding_rate|open_interest|BTC\.D|ETH\.BTC|CVD|VWAP|OI)$/i;

const PRODUCT_TEXT_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bindex:\s*present but not execution fact source;\s*source_types=([^;]+)/gi, "指数价来自$1，不能作为执行事实"],
  [/\bmark:\s*present but not execution fact source;\s*source_types=([^;]+)/gi, "标记价来自$1，不能作为执行事实"],
  [/\border_book:\s*present but not execution fact source;\s*source_types=([^;]+)/gi, "订单簿来自$1，不能作为执行事实"],
  [/\bactive_event_status:\s*missing\b/gi, "缺少宏观事件状态确认"],
  [/BTC structure is not confirming downside and funding is not crowded\./gi, "BTC 结构暂未确认下行，资金费率未拥挤。"],
  [/Invalid if ETH loses ([0-9.]+) on fresh OKX mark price\./gi, "若 ETH 最新 OKX 标记价跌破 $1，则本计划失效。"],
  [/default action '([^']+)' is outside candidate effective_allowed_actions/gi, "默认建议动作“$1”不在当前可复核动作范围内"],
  [/默认\s*建议动作\s*['“]([^'”]+)['”]\s*is outside\s*候选复核\s*当前可复核动作范围/gi, "默认建议动作“$1”不在当前可复核动作范围内"],
  [/default probability ([0-9.]+) exceeds candidate cap ([0-9.]+)/gi, "默认概率 $1 高于当前复核上限 $2"],
  [/worker contribution reported a hard block/gi, "审查结果报告硬性阻断"],
  [/Open OKX manually\. This service will not place orders\./gi, "请在 OKX 人工核对后手动操作；本系统不会下单。"],
  [/flip long to short/gi, "多单转空单"],
  [/flip short to long/gi, "空单转多单"],
  [/trigger long/gi, "触发做多"],
  [/trigger short/gi, "触发做空"],
  [/open long/gi, "开多"],
  [/open short/gi, "开空"],
  [/hold long/gi, "继续持有多单"],
  [/hold short/gi, "继续持有空单"],
  [/close long/gi, "平多"],
  [/close short/gi, "平空"],
  [/increase long/gi, "加多"],
  [/increase short/gi, "加空"],
  [/no trade/gi, "暂不操作"],
  [/本地样本\/规则模式/g, "本地演练模式"],
  [/未调用真实\s*LLM/g, "未调用外部模型"],
  [/使用\s+openai_compatible\s+决策引擎/gi, "使用外部模型决策引擎"],
  [/\bopenai_compatible\b/gi, "外部模型"],
  [/\bmock\s*LLM\b/gi, "本地模型模拟"],
  [/\bLLM\b/g, "外部模型"],
  [/\bfixture\b/gi, "演练数据"],
  [/manual_execution_required\s*必须保持为\s*true/gi, "必须保持人工手动执行"],
  [/\bmanual_execution_required\b/gi, "人工手动执行要求"],
  [/\blegacy_prompt\b/gi, "默认生成路径"],
  [/\bdecision_input\b/gi, "生成输入"],
  [/\blegacy\b/gi, "默认"],
  [/\braw\b/gi, "证据详情"],
  [/\btrace_id\b/gi, "提醒编号"],
  [/\btrace\b/gi, "提醒记录"],
  [/\bprovider\b/gi, "数据来源"],
  [/\beffective_allowed_actions\b/gi, "当前可复核动作范围"],
  [/\baction\b/gi, "建议动作"],
  [/\bprobability\b/gi, "概率"],
  [/\bworker contribution\b/gi, "审查结果"],
  [/\bhard block\b/gi, "硬性阻断"],
  [/\bcandidate\b/gi, "候选复核"],
  [/\bbaseline\b/gi, "基准评估"],
  [/\boutcome\b/gi, "结果复盘"],
  [/\bblocking\b/gi, "阻断"],
  [/\bwarn\b/gi, "提醒"],
  [/默认\s*建议动作\s*['“]([^'”]+)['”]\s*is outside\s*候选复核\s*当前可复核动作范围/gi, "默认建议动作“$1”不在当前可复核动作范围内"]
];

const FIELD_LABELS: Record<string, string> = {
  index: "指数价",
  mark: "标记价",
  order_book: "订单簿",
  active_event_status: "事件状态"
};

const ENUM_LABELS: Record<string, string> = {
  unknown: "未说明",
  normal: "普通",
  conservative: "保守",
  aggressive: "激进",
  long: "已有多单",
  short: "已有空单",
  flat: "空仓",
  allowed: "可人工复核",
  blocked: "已阻断",
  passed: "通过",
  failed: "未通过",
  not_configured: "未配置",
  not_enough_samples: "样本不足",
  baseline_reference: "基线参考",
  sent: "已发送",
  disabled: "未启用",
  manual_execution_required: "人工手动执行要求",
  trace_id: "提醒编号",
  legacy_prompt: "默认生成路径",
  decision_input: "生成输入",
  effective_allowed_actions: "当前可复核动作范围",
  active_event_status: "事件状态",
  price_source_not_exchange_native: "价格不是交易所原生样本",
  window_not_matured: "观察窗口尚未成熟"
};

export function productDecisionLabel(label: string | null | undefined): string | undefined {
  if (!label) return undefined;
  return PRODUCT_LABELS[label] ?? productDisplayText(label);
}

export function productDisplayText(text: string | null | undefined): string {
  if (!text) return "";
  const raw = text.trim();
  const rawLabel = FIELD_LABELS[raw] ?? ENUM_LABELS[raw];
  if (rawLabel) return rawLabel;
  if (isInternalToken(raw)) return ENGINEERING_DETAIL_FALLBACK;
  const normalized = PRODUCT_TEXT_REPLACEMENTS.reduce((current, [pattern, replacement]) => {
    return current.replace(pattern, replacement);
  }, raw);
  return FIELD_LABELS[normalized] ?? ENUM_LABELS[normalized] ?? hideUnknownInternalTokens(normalized);
}

export function productDisplayItems(items: string[] | undefined, limit?: number): string[] {
  const source = limit ? items?.slice(0, limit) : items;
  return (source ?? []).map(productDisplayText).filter(Boolean);
}

export function productFactLabel(value: string): string {
  return FIELD_LABELS[value] ?? productDisplayText(value);
}

export function productEnumLabel(value: unknown): string {
  if (typeof value !== "string") {
    return productDisplayText(String(value ?? ""));
  }
  return ENUM_LABELS[value] ?? productDisplayText(value);
}

function hideUnknownInternalTokens(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (isInternalToken(trimmed)) {
    return ENGINEERING_DETAIL_FALLBACK;
  }
  return trimmed.replace(INTERNAL_TOKEN_PATTERN, (token) =>
    SAFE_MARKET_INDICATOR_PATTERN.test(token) ? token : ENGINEERING_DETAIL_FALLBACK
  );
}

function isInternalToken(value: string): boolean {
  return FULL_INTERNAL_TOKEN_PATTERN.test(value);
}
