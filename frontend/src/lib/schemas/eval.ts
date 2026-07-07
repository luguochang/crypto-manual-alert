import { z } from "zod";

export const evalTraceSummarySchema = z
  .object({
    trace_id: z.string(),
    symbol: z.string(),
    horizon: z.string().nullable().optional(),
    run_type: z.string(),
    status: z.string(),
    final_action: z.string().nullable().optional(),
    allowed: z.boolean().nullable().optional(),
    created_at: z.string(),
    span_count: z.number().default(0),
    llm_interaction_count: z.number().default(0)
  })
  .passthrough();

export const evalCandidateSchema = z
  .object({
    id: z.number(),
    trace_id: z.string(),
    plan_id: z.string().nullable().optional(),
    created_at: z.string(),
    category: z.string(),
    severity: z.string(),
    status: z.string(),
    source: z.string(),
    summary: z.string().default(""),
    comment: z.string().default(""),
    expected_behavior: z.string().nullable().optional(),
    actual_behavior: z.string().nullable().optional(),
    eval_dataset_name: z.string().nullable().optional(),
    evidence_refs: z.unknown().optional(),
    trace: evalTraceSummarySchema,
    plan_summary: z.record(z.unknown()).default({})
  })
  .passthrough();

export const evalCandidateListSchema = z.object({
  items: z.array(evalCandidateSchema)
});

export const predictionQualityMetricsSchema = z
  .object({
    scored_count: z.number().default(0),
    pending_count: z.number().default(0),
    unscored_count: z.number().default(0),
    no_trade_count: z.number().default(0),
    direction_hit_rate: z.number().nullable().optional(),
    target_hit_rate: z.number().nullable().optional(),
    invalidation_hit_rate: z.number().nullable().optional(),
    average_pnl_pct: z.number().nullable().optional(),
    average_r_multiple: z.number().nullable().optional(),
    brier_score: z.number().nullable().optional(),
    unscored_reasons: z.record(z.number()).default({})
  })
  .passthrough();

export const financialQualityTargetGateSchema = z
  .object({
    schema_version: z.number().default(1),
    status: z.string(),
    passed: z.boolean().optional(),
    blocking: z.boolean().default(false),
    decision_effect: z.string().default("none"),
    structural_release_gate_blocking: z.boolean().default(false),
    evaluation_target: z.string(),
    minimum_scored_count: z.number().default(0),
    observed_scored_count: z.number().default(0),
    blocking_reasons: z.array(z.string()).default([]),
    brier_event_label: z.string().optional(),
    metrics: predictionQualityMetricsSchema
  })
  .passthrough();

export const financialQualityGateSchema = z
  .object({
    schema_version: z.number().default(1),
    status: z.string().default("not_configured"),
    decision_effect: z.string().default("none"),
    structural_release_gate_blocking: z.boolean().default(false),
    blocking: z.boolean().default(false),
    blocking_reasons: z.array(z.string()).default([]),
    evaluation_targets: z.array(z.string()).default([]),
    target_gates: z.array(financialQualityTargetGateSchema).default([])
  })
  .passthrough();

export const evalRunMetadataSchema = z
  .object({
    judge_provider: z.string().optional(),
    replay: z.record(z.unknown()).optional(),
    side_effect_deltas: z.record(z.unknown()).optional(),
    report_json_ref: z.string().optional(),
    report_markdown_ref: z.string().optional(),
    financial_quality_gate: financialQualityGateSchema.optional(),
    release_gate: z.record(z.unknown()).optional()
  })
  .passthrough();

export const evalRunSummarySchema = z
  .object({
    eval_run_id: z.string(),
    dataset_name: z.string(),
    mode: z.string(),
    status: z.string(),
    started_at: z.string(),
    ended_at: z.string().nullable().optional(),
    case_count: z.number(),
    pass_count: z.number(),
    fail_count: z.number(),
    metadata: evalRunMetadataSchema.default({})
  })
  .passthrough();

export const evalRunListSchema = z.object({
  items: z.array(evalRunSummarySchema)
});

export const evalCaseSchema = z
  .object({
    case_id: z.string(),
    dataset_name: z.string(),
    source_trace_id: z.string(),
    source_badcase_id: z.number(),
    symbol: z.string(),
    horizon: z.string().nullable().optional(),
    failure_category: z.string(),
    severity: z.string(),
    expected_behavior: z.string(),
    actual_behavior: z.string(),
    summary: z.string(),
    frozen_input_hash: z.string(),
    input_summary: z.record(z.unknown()),
    replay_result: z
      .object({
        status: z.string(),
        mode: z.string(),
        final_action: z.string().nullable().optional(),
        allowed: z.boolean().nullable().optional(),
        output_hash: z.string().nullable().optional(),
        reason_summary: z.string().nullable().optional(),
        error_message: z.string().nullable().optional(),
        duration_ms: z.number().nullable().optional(),
        metadata: z.record(z.unknown()).default({})
      })
      .passthrough()
      .optional(),
    metadata: z.record(z.unknown()).default({})
  })
  .passthrough();

export const evalScoreSchema = z
  .object({
    score_id: z.string(),
    eval_run_id: z.string(),
    case_id: z.string(),
    source_trace_id: z.string().default(""),
    source_badcase_id: z.number().default(0),
    judge_name: z.string(),
    judge_type: z.string(),
    score: z.number().nullable().optional(),
    passed: z.boolean(),
    severity: z.string(),
    failure_category: z.string(),
    reason_summary: z.string(),
    evidence_refs: z.array(z.string()).default([]),
    needs_human_review: z.boolean().default(false),
    metadata: z.record(z.unknown()).default({})
  })
  .passthrough();

export const evalRunDetailSchema = z.object({
  run: evalRunSummarySchema,
  cases: z.array(evalCaseSchema).default([]),
  scores: z.array(evalScoreSchema).default([])
});

export const evalOutcomeWindowSchema = z
  .object({
    name: z.string(),
    symbol: z.string(),
    interval: z.string(),
    source_type: z.string(),
    window_start: z.string(),
    window_end: z.string(),
    collected_at: z.string(),
    open_price: z.number().nullable().optional(),
    high_price: z.number().nullable().optional(),
    low_price: z.number().nullable().optional(),
    close_price: z.number().nullable().optional(),
    matured: z.boolean().default(false),
    can_score_execution_outcome: z.boolean().default(false),
    unscored_reason: z.string().nullable().optional()
  })
  .passthrough();

export const evalOutcomeSchema = z
  .object({
    decision_ref: z.string(),
    evaluation_target: z.string(),
    symbol: z.string(),
    action: z.string(),
    probability: z.number().nullable().optional(),
    entry_price: z.number().nullable().optional(),
    stop_price: z.number().nullable().optional(),
    target_1: z.number().nullable().optional(),
    target_2: z.number().nullable().optional(),
    window: evalOutcomeWindowSchema,
    can_score: z.boolean().default(false),
    unscored_reason: z.string().nullable().optional(),
    regime: z.string().nullable().optional()
  })
  .passthrough();

export const evalOutcomeListSchema = z.object({
  items: z.array(evalOutcomeSchema)
});

export type EvalCandidate = z.output<typeof evalCandidateSchema>;
export type EvalCase = z.output<typeof evalCaseSchema>;
export type FinancialQualityGate = z.output<typeof financialQualityGateSchema>;
export type EvalRunSummary = z.output<typeof evalRunSummarySchema>;
export type EvalRunDetail = z.output<typeof evalRunDetailSchema>;
export type EvalScore = z.output<typeof evalScoreSchema>;
export type EvalOutcome = z.output<typeof evalOutcomeSchema>;
