import { z } from "zod";

// /api/system/health
export const systemHealthSchema = z
  .object({
    service: z.string(),
    storage: z.string(),
    mode: z.string()
  })
  .passthrough();

const readinessItemSchema = z
  .object({
    status: z.string(),
    message: z.string().optional(),
    summary: z.string().optional()
  })
  .passthrough();

export const readinessSchema = z
  .object({
    overall: readinessItemSchema.extend({
      real_external_ready: z.boolean().default(false)
    }),
    decision_engine: readinessItemSchema,
    openai_credentials: readinessItemSchema,
    market_data: readinessItemSchema,
    liquidity_order_book: readinessItemSchema,
    event_status: readinessItemSchema,
    notification: readinessItemSchema,
    trading_safety: readinessItemSchema,
    forbidden_env: readinessItemSchema,
    prod_actionable: readinessItemSchema.extend({
      prod_actionable_ready: z.boolean().default(false),
      real_external_ready: z.boolean().default(false),
      event_ready: z.boolean().default(false),
      candidate_sidecar_disabled: z.boolean().default(false),
      production_main_path_ready: z.boolean().default(false),
      main_path_blockers: z.array(z.string()).default([])
    })
  })
  .passthrough();

// /api/system/config — safe_dict() 返回的脱敏配置快照。
// value 类型多样（bool/str/num/list），readiness 是显式结构，其余段通用渲染。
export const systemConfigSchema = z
  .record(z.string(), z.record(z.string(), z.unknown()))
  .and(z.object({ readiness: readinessSchema }));

export type SystemHealth = z.output<typeof systemHealthSchema>;
export type SystemConfig = z.output<typeof systemConfigSchema>;
export type Readiness = z.output<typeof readinessSchema>;
