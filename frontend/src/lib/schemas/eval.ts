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
    metadata: z.record(z.unknown()).default({})
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
    input_summary: z.unknown(),
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

export type EvalCandidate = z.output<typeof evalCandidateSchema>;
export type EvalRunSummary = z.output<typeof evalRunSummarySchema>;
export type EvalRunDetail = z.output<typeof evalRunDetailSchema>;
export type EvalScore = z.output<typeof evalScoreSchema>;
