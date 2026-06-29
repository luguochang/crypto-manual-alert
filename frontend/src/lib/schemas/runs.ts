import { z } from "zod";

export const runStatusSchema = z.enum(["running", "allowed", "blocked", "failed", "ok"]);

export const runSummarySchema = z
  .object({
    trace_id: z.string(),
    status: runStatusSchema,
    run_type: z.string(),
    symbol: z.string(),
    created_at: z.string(),
    ended_at: z.string().nullable().optional(),
    final_plan_id: z.string().nullable().optional(),
    final_action: z.string().nullable().optional(),
    allowed: z.boolean().nullable().optional(),
    span_count: z.number().default(0),
    llm_interaction_count: z.number().default(0)
  })
  .passthrough();

export const runListSchema = z.object({
  items: z.array(runSummarySchema)
});

export const traceSpanSchema = z
  .object({
    span_id: z.string(),
    span_name: z.string(),
    span_type: z.string(),
    status: z.string(),
    started_at: z.string(),
    ended_at: z.string(),
    duration_ms: z.number(),
    input_summary: z.unknown().optional(),
    output_summary: z.unknown().optional(),
    error_type: z.string().nullable().optional(),
    error_message: z.string().nullable().optional()
  })
  .passthrough();

export const llmInteractionSchema = z
  .object({
    id: z.number(),
    component: z.string(),
    provider: z.string(),
    model: z.string(),
    status: z.string(),
    input_hash: z.string(),
    output_hash: z.string(),
    input_summary: z.unknown().optional(),
    output_summary: z.unknown().optional(),
    request_json: z.string().optional(),
    response_json: z.string().optional(),
    error_message: z.string().nullable().optional()
  })
  .passthrough();

export const planRunSchema = z
  .object({
    plan_id: z.string(),
    created_at: z.string().optional(),
    status: z.string(),
    parsed_plan: z.record(z.unknown()).optional(),
    verdict: z.record(z.unknown()).optional(),
    redaction: z.record(z.unknown()).optional(),
    payload_keys: z.array(z.string()).default([])
  })
  .nullable();

export const runDetailSchema = z.object({
  trace: runSummarySchema,
  plan_run: planRunSchema,
  analysis: z.record(z.unknown()).default({}),
  spans: z.array(traceSpanSchema).default([]),
  llm_interactions: z.array(llmInteractionSchema).default([]),
  badcases: z.array(z.record(z.unknown())).default([])
});

export const dashboardStatsSchema = z.object({
  total_runs: z.number().default(0),
  running_runs: z.number().default(0),
  allowed_runs: z.number().default(0),
  blocked_runs: z.number().default(0),
  failed_runs: z.number().default(0),
  recent_runs: z.array(runSummarySchema).default([])
});

export type RunStatus = z.infer<typeof runStatusSchema>;
export type RunSummary = z.output<typeof runSummarySchema>;
export type RunList = z.output<typeof runListSchema>;
export type RunDetail = z.output<typeof runDetailSchema>;
export type DashboardStats = z.output<typeof dashboardStatsSchema>;
