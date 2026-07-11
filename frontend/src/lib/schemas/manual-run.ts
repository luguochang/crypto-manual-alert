import { z } from "zod";
import { productFactLabel } from "@/app/shared/product-copy";
import { hasUnsafeDisplayText } from "@/app/shared/safe-error";

export const SAFE_REASON_FALLBACK = "风控结论已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";
export const SAFE_CONTENT_FALLBACK = "内容已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";
const SAFE_WARNING_FALLBACK = "风控提醒已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";
const SAFE_NOTIFICATION_FALLBACK = "通知状态已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";
const MARKET_DATA_FACT_NAMES = new Set(["index", "mark", "order_book"]);
const SAFE_ERROR_TYPE_PATTERN = /^[A-Z][A-Za-z0-9]{0,63}$/;

export const generationSummarySchema = z
  .object({
    mode_label: z.string(),
    provider: z.string().nullable().optional(),
    provider_label: z.string().nullable().optional(),
    model: z.string().nullable().optional(),
    status: z.string().nullable().optional(),
    status_label: z.string(),
    duration_text: z.string().nullable().optional(),
    token_text: z.string().nullable().optional(),
    finish_reason: z.string().nullable().optional(),
    response_summary: z.string(),
    raw_completion_label: z.string().nullable().optional(),
    raw_completion_excerpt: z.string().nullable().optional(),
    detail_bullets: z.array(z.string()).default([])
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    mode_label: safeDisplayText(value.mode_label),
    provider: safeNullableDisplayText(value.provider),
    provider_label: safeNullableDisplayText(value.provider_label),
    model: safeNullableDisplayText(value.model),
    status: safeNullableDisplayText(value.status),
    status_label: safeDisplayText(value.status_label),
    duration_text: safeNullableDisplayText(value.duration_text),
    token_text: safeNullableDisplayText(value.token_text),
    finish_reason: safeNullableDisplayText(value.finish_reason),
    response_summary: safeDisplayText(value.response_summary),
    raw_completion_label: safeNullableDisplayText(value.raw_completion_label),
    raw_completion_excerpt: safeNullableDisplayText(value.raw_completion_excerpt),
    detail_bullets: safeDisplayBullets(value.detail_bullets)
  }));

export const marketDataStatusItemSchema = z
  .object({
    name: z.string(),
    label: z.string(),
    status: z.string(),
    status_label: z.string(),
    source: z.string().nullable().optional(),
    source_label: z.string().nullable().optional(),
    can_satisfy_execution_fact: z.boolean().default(false),
    value_text: z.string().nullable().optional(),
    error_type: z.string().nullable().optional(),
    failure_reason: z.string().nullable().optional()
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    name: safeMarketDataName(value.name),
    label: safeMarketDataLabel(value.label, value.name),
    status: safeDisplayText(value.status),
    status_label: safeDisplayText(value.status_label),
    source: safeNullableDisplayText(value.source),
    source_label: safeNullableDisplayText(value.source_label),
    value_text: safeNullableDisplayText(value.value_text),
    error_type: safeNullableErrorType(value.error_type),
    failure_reason: safeNullableDisplayText(value.failure_reason)
  }));

export const marketDataStatusFailureSchema = z
  .object({
    name: z.string(),
    label: z.string(),
    error_type: z.string().nullable().optional(),
    reason: z.string().nullable().optional()
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    name: safeMarketDataName(value.name),
    label: safeMarketDataLabel(value.label, value.name),
    error_type: safeNullableErrorType(value.error_type),
    reason: safeNullableDisplayText(value.reason)
  }));

export const marketDataStatusSchema = z
  .object({
    provider: z.string().nullable().optional(),
    provider_label: z.string().nullable().optional(),
    symbol: z.string().nullable().optional(),
    summary: z.string().default("交易数据状态未记录。"),
    execution_facts_ready: z.boolean().default(false),
    success_count: z.number().default(0),
    failed_count: z.number().default(0),
    missing_count: z.number().default(0),
    items: z.array(marketDataStatusItemSchema).default([]),
    failures: z.array(marketDataStatusFailureSchema).default([])
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    provider: safeNullableDisplayText(value.provider),
    provider_label: safeNullableDisplayText(value.provider_label),
    symbol: safeNullableDisplayText(value.symbol),
    summary: safeDisplayText(value.summary),
    items: value.items,
    failures: value.failures
  }));

export const businessSummarySchema = z
  .object({
    title: z.string(),
    mode_notice: z.string(),
    decision_label: z.string(),
    action_text: z.string(),
    confidence_text: z.string(),
    price_levels: z
      .object({
        reference_price: z.number().nullable().optional(),
        entry_trigger: z.number().nullable().optional(),
        stop_price: z.number().nullable().optional(),
        target_1: z.number().nullable().optional(),
        target_2: z.number().nullable().optional(),
        expires_at: z.string().nullable().optional()
      })
      .default({}),
    reason_bullets: z.array(z.string()).default([]),
    risk_bullets: z.array(z.string()).default([]),
    evidence_bullets: z.array(z.string()).default([]),
    data_gap_bullets: z.array(z.string()).default([]),
    next_steps: z.array(z.string()).default([]),
    safety_notice: z.string(),
    generation_summary: generationSummarySchema,
    market_data_status: marketDataStatusSchema.default({
      provider: null,
      provider_label: null,
      symbol: null,
      summary: "交易数据状态未记录。",
      execution_facts_ready: false,
      success_count: 0,
      failed_count: 0,
      missing_count: 0,
      items: [],
      failures: []
    }),
    notification: z
      .object({
        enabled: z.boolean(),
        channel: z.string().nullable().optional(),
        status: z.enum(["sent", "disabled", "failed", "not_recorded"]),
        status_code: z.number().nullable().optional(),
        sent_at: z.string().nullable().optional(),
        error: z.string().nullable().optional(),
        message: z.string()
      })
      .default({ enabled: false, status: "not_recorded", message: "通知状态未记录" })
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    title: safeDisplayText(value.title),
    mode_notice: safeDisplayText(value.mode_notice),
    decision_label: safeDisplayText(value.decision_label),
    action_text: safeDisplayText(value.action_text),
    confidence_text: safeDisplayText(value.confidence_text),
    reason_bullets: safeReasonBullets(value.reason_bullets),
    risk_bullets: safeDisplayBullets(value.risk_bullets),
    evidence_bullets: safeDisplayBullets(value.evidence_bullets),
    data_gap_bullets: safeDisplayBullets(value.data_gap_bullets),
    next_steps: safeDisplayBullets(value.next_steps),
    safety_notice: safeDisplayText(value.safety_notice),
    notification: {
      ...value.notification,
      channel: safeNullableDisplayText(value.notification.channel, SAFE_NOTIFICATION_FALLBACK),
      error: safeNullableDisplayText(value.notification.error, SAFE_NOTIFICATION_FALLBACK),
      message: safeDisplayText(value.notification.message, SAFE_NOTIFICATION_FALLBACK)
    }
  }));

export const resultReviewItemSchema = z
  .object({
    target_label: z.string(),
    source_label: z.string(),
    window_name: z.string().optional(),
    window_text: z.string(),
    matured: z.boolean(),
    can_score: z.boolean(),
    unscored_label: z.string(),
    price_result_text: z.string(),
    collected_at: z.string().nullable().optional()
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    target_label: safeDisplayText(value.target_label),
    source_label: safeDisplayText(value.source_label),
    window_name: safeNullableDisplayText(value.window_name),
    window_text: safeDisplayText(value.window_text),
    unscored_label: safeDisplayText(value.unscored_label),
    price_result_text: safeDisplayText(value.price_result_text)
  }));

export const resultReviewSchema = z
  .object({
    status: z.string(),
    label: z.string(),
    message: z.string(),
    quality_scope: z.string(),
    sample_count: z.number(),
    scored_count: z.number(),
    pending_count: z.number(),
    unscored_count: z.number(),
    can_score: z.boolean(),
    items: z.array(resultReviewItemSchema).default([])
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    label: safeDisplayText(value.label),
    message: safeDisplayText(value.message)
  }));

export const mainPathContractSchema = z
  .object({
    schema_version: z.string().optional(),
    runtime_role: z.string().optional(),
    proof_level: z.string().optional(),
    production_success: z.boolean().optional(),
    hosted_proof_required: z.boolean().optional(),
    does_not_prove: z.string().nullable().optional(),
    final_input_contract: z.record(z.unknown()).default({}),
    manual_only: z.record(z.unknown()).default({}),
    query_contract: z.record(z.unknown()).default({})
  })
  .passthrough();

export const manualRunRequestSchema = z.object({
  symbol: z.string().min(1, "请输入交易对").default("ETH-USDT-SWAP"),
  query: z.string().min(1, "请输入关注点"),
  horizon: z.string().optional(),
  session_id: z.string().optional(),
  alert_channel: z.string().default("bark"),
  position: z
    .object({
      side: z.enum(["long", "short", "flat", "unknown"]).default("unknown"),
      entry_price: z.coerce.number().positive().optional(),
      size: z.string().optional(),
      leverage: z.coerce.number().positive().max(2).optional()
    })
    .default({ side: "unknown" }),
  risk_mode: z.enum(["conservative", "normal", "aggressive"]).default("normal")
});

export const manualRunPlanSchema = z.object({
  plan_id: z.string(),
  instrument: z.string(),
  main_action: z.string(),
  horizon: z.string(),
  manual_execution_required: z.boolean(),
  expires_at: z.string(),
  reference_price: z.number().nullable().optional(),
  entry_trigger: z.number().nullable().optional(),
  stop_price: z.number().nullable().optional(),
  target_1: z.number().nullable().optional(),
  target_2: z.number().nullable().optional(),
  probability: z.number().nullable().optional()
});

export const manualRunVerdictSchema = z
  .object({
    allowed: z.boolean(),
    reasons: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([])
  })
  .transform((value) => ({
    ...value,
    reasons: safeReasonBullets(value.reasons, SAFE_REASON_FALLBACK),
    warnings: safeReasonBullets(value.warnings, SAFE_WARNING_FALLBACK)
  }));

export const manualRunResponseSchema = z
  .object({
    trace_id: z.string(),
    plan: manualRunPlanSchema,
    verdict: manualRunVerdictSchema,
    business_summary: z.unknown().optional(),
    main_path_contract: mainPathContractSchema.optional(),
    result_review: z.unknown().optional()
  })
  .transform((value) => ({
    ...value,
    business_summary: safeBusinessSummary(value.business_summary, value),
    result_review: safeResultReview(value.result_review)
  }));

export type ManualRunRequest = z.infer<typeof manualRunRequestSchema>;
export type ManualRunResponse = z.output<typeof manualRunResponseSchema>;
export type BusinessSummary = z.output<typeof businessSummarySchema>;
export type ResultReview = z.output<typeof resultReviewSchema>;

export function safeBusinessSummary(
  value: unknown,
  response: { plan: z.output<typeof manualRunPlanSchema>; verdict: z.output<typeof manualRunVerdictSchema> }
): BusinessSummary {
  const parsed = businessSummarySchema.safeParse(value);
  if (parsed.success) {
    return parsed.data;
  }
  return fallbackBusinessSummary(response.plan, response.verdict);
}

export function safeResultReview(value: unknown): ResultReview {
  const parsed = resultReviewSchema.safeParse(value);
  if (parsed.success) {
    return parsed.data;
  }
  return fallbackResultReview();
}

function fallbackBusinessSummary(
  plan: z.output<typeof manualRunPlanSchema>,
  verdict: z.output<typeof manualRunVerdictSchema>
): BusinessSummary {
  const blocked = !verdict.allowed;
  const reasonBullets = safeReasonBullets(verdict.reasons, SAFE_REASON_FALLBACK);
  return {
    title: `${plan.instrument} 手动提醒计划`,
    mode_notice: "提醒核心结果已返回，但业务摘要暂不可用。请打开详情页核对完整记录。",
    decision_label: blocked ? "已阻断：禁止作为操作依据" : "可人工复核",
    action_text: plan.main_action,
    confidence_text:
      typeof plan.probability === "number" ? `概率 ${(plan.probability * 100).toFixed(0)}%` : "概率未记录",
    price_levels: {
      reference_price: plan.reference_price,
      entry_trigger: plan.entry_trigger,
      stop_price: plan.stop_price,
      target_1: plan.target_1,
      target_2: plan.target_2,
      expires_at: plan.expires_at
    },
    reason_bullets:
      reasonBullets.length > 0
        ? reasonBullets
        : ["摘要暂不可用，已保留核心提醒计划和风控结论。"],
    risk_bullets: blocked
      ? ["当前风控结论为已阻断，禁止作为操作依据。"]
      : ["当前仅可进入人工复核，不代表自动下单许可。"],
    evidence_bullets: ["已返回核心提醒计划和详情入口，可继续核对摘要投影问题。"],
    data_gap_bullets: ["业务摘要暂不可用。"],
    next_steps: [
      "打开详情页查看完整记录和诊断信息。",
      "人工核对交易所行情、事件状态和风险后再决定。"
    ],
    safety_notice: "系统仅给人工提醒建议，不会自动下单。",
    generation_summary: {
      mode_label: "摘要暂不可用",
      provider: null,
      provider_label: null,
      model: null,
      status: null,
      status_label: "核心提醒已返回",
      duration_text: null,
      token_text: null,
      finish_reason: null,
      response_summary: "模型或规则摘要投影暂不可用。已保留计划、风控结论和详情入口。",
      raw_completion_label: "模型原始返回摘录",
      raw_completion_excerpt: null,
      detail_bullets: [
        "前端未收到完整 business_summary 展示投影。",
        "这不是生产成功证明，请以详情页和生产门禁为准。"
      ]
    },
    market_data_status: {
      provider: null,
      provider_label: null,
      symbol: plan.instrument,
      summary: "交易数据状态未记录。",
      execution_facts_ready: false,
      success_count: 0,
      failed_count: 0,
      missing_count: 0,
      items: [],
      failures: []
    },
    notification: {
      enabled: false,
      channel: null,
      status: "not_recorded",
      status_code: null,
      sent_at: null,
      error: null,
      message: "通知状态未记录"
    }
  };
}

export function safeReasonBullets(values: string[] | undefined, fallback: string = SAFE_REASON_FALLBACK): string[] {
  const sanitized = (values ?? []).map((value) => safeReasonBullet(value, fallback)).filter(Boolean);
  return Array.from(new Set(sanitized));
}

export function safeDisplayText(value: string, fallback: string = SAFE_CONTENT_FALLBACK): string {
  const text = value.trim();
  if (!text) {
    return "";
  }
  return hasUnsafeDisplayText(text) ? fallback : text;
}

export function safeDisplayBullets(values: string[] | undefined, fallback: string = SAFE_CONTENT_FALLBACK): string[] {
  const sanitized = (values ?? []).map((value) => safeDisplayText(value, fallback)).filter(Boolean);
  return Array.from(new Set(sanitized));
}

function safeNullableDisplayText(
  value: string | null | undefined,
  fallback: string = SAFE_CONTENT_FALLBACK
): string | null | undefined {
  return typeof value === "string" ? safeDisplayText(value, fallback) : value;
}

function safeMarketDataName(value: string): string {
  const text = value.trim();
  return MARKET_DATA_FACT_NAMES.has(text) ? text : safeDisplayText(text);
}

function safeMarketDataLabel(label: string, name: string): string {
  const factName = MARKET_DATA_FACT_NAMES.has(name.trim())
    ? name.trim()
    : MARKET_DATA_FACT_NAMES.has(label.trim())
      ? label.trim()
      : null;
  return factName ? productFactLabel(factName) : safeDisplayText(label);
}

function safeNullableErrorType(value: string | null | undefined): string | null | undefined {
  if (typeof value !== "string") {
    return value;
  }
  const text = value.trim();
  if (!text || !SAFE_ERROR_TYPE_PATTERN.test(text)) {
    return null;
  }
  return text;
}

function safeReasonBullet(value: string, fallback: string): string {
  const text = value.trim();
  if (!text) {
    return "";
  }
  return hasUnsafeDisplayText(text) ? fallback : text;
}

function fallbackResultReview(): ResultReview {
  return {
    status: "not_collected",
    label: "尚未产生复盘结果",
    message: "结果尚未生成。观察窗口成熟并完成采集后，会在这里显示复盘状态。",
    quality_scope: "none",
    sample_count: 0,
    scored_count: 0,
    pending_count: 0,
    unscored_count: 0,
    can_score: false,
    items: []
  };
}
