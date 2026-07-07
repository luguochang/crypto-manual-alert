import { z } from "zod";

export const manualRunRequestSchema = z.object({
  symbol: z.string().min(1, "请输入交易对").default("ETH-USDT-SWAP"),
  query: z.string().min(1, "请输入分析问题"),
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

export const manualRunResponseSchema = z.object({
  trace_id: z.string(),
  plan: z.object({
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
  }),
  verdict: z.object({
    allowed: z.boolean(),
    reasons: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([])
  })
});

export type ManualRunRequest = z.infer<typeof manualRunRequestSchema>;
export type ManualRunResponse = z.output<typeof manualRunResponseSchema>;
