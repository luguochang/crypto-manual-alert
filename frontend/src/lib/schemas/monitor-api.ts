import { z } from "zod";

const absoluteTimestampSchema = z
  .string()
  .regex(
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/,
    "Timestamp must include an explicit UTC offset",
  )
  .refine((value) => !Number.isNaN(Date.parse(value)), "Invalid timestamp");

const localTimeSchema = z
  .string()
  .regex(/^(?:[01]\d|2[0-3]):[0-5]\d$/, "Time must use HH:mm");

export const monitorStatusFilterSchema = z.enum([
  "running",
  "paused",
  "attention",
  "closed",
  "all",
]);

export const monitorStatusSchema = z.enum([
  "draft",
  "active",
  "paused",
  "degraded",
  "expired",
  "disabled",
]);

export const monitorRunTaskTypeSchema = z.enum([
  "market_analysis",
  "deep_research",
]);

export const monitorConditionSchema = z.discriminatedUnion("kind", [
  z.strictObject({
    kind: z.literal("price"),
    operator: z.enum(["gte", "lte"]),
    threshold: z.number().finite().positive(),
  }),
  z.strictObject({
    kind: z.literal("thesis"),
    statement: z.string().trim().min(3).max(500),
  }),
  z.strictObject({
    kind: z.literal("provider_health"),
    provider: z.enum(["okx", "tavily", "builtin_web_search"]),
    consecutive_failures: z.number().int().min(1).max(10),
  }),
  z.strictObject({
    kind: z.literal("scheduled_review"),
  }),
]);

export const monitorScheduleSchema = z.enum([
  "*/5 * * * *",
  "*/15 * * * *",
  "0 * * * *",
  "0 */4 * * *",
  "0 0 * * *",
]);

export const monitorTimezoneSchema = z
  .string()
  .trim()
  .min(1)
  .max(64)
  .refine((value) => {
    try {
      new Intl.DateTimeFormat("en", { timeZone: value }).format();
      return true;
    } catch {
      return false;
    }
  }, "Invalid IANA timezone");

export const monitorQuietHoursSchema = z
  .strictObject({
    start: localTimeSchema,
    end: localTimeSchema,
  })
  .refine((value) => value.start !== value.end, {
    message: "Quiet hours must have different start and end times",
    path: ["end"],
  });

export const createMonitorRequestSchema = z
  .strictObject({
    name: z.string().trim().min(1).max(120),
    artifact_id: z.string().uuid(),
    artifact_version_id: z.string().uuid(),
    run_task_type: monitorRunTaskTypeSchema,
    condition: monitorConditionSchema,
    schedule: monitorScheduleSchema,
    timezone: monitorTimezoneSchema,
    expires_at: absoluteTimestampSchema,
    quiet_hours: monitorQuietHoursSchema.nullable(),
    destination_ids: z.array(z.string().uuid()).max(8),
  })
  .superRefine((request, context) => {
    if (new Set(request.destination_ids).size !== request.destination_ids.length) {
      context.addIssue({
        code: "custom",
        message: "Destination IDs must be unique",
        path: ["destination_ids"],
      });
    }
  });

export const monitorVersionMutationSchema = z.strictObject({
  expected_version: z.number().int().positive(),
});

export const monitorTriggerSchema = z.strictObject({
  id: z.string().uuid(),
  trigger_kind: z.enum(["cron", "manual"]),
  status: z.enum(["received", "suppressed", "admitted", "failed"]),
  reason: z.string().trim().min(1).max(128).nullable(),
  task_id: z.string().uuid().nullable(),
  triggered_at: absoluteTimestampSchema,
  created_at: absoluteTimestampSchema,
});

export const monitorSchema = z.strictObject({
    id: z.string().uuid(),
    version: z.number().int().positive(),
    name: z.string().trim().min(1).max(120),
    status: monitorStatusSchema,
    run_task_type: monitorRunTaskTypeSchema,
    artifact_id: z.string().uuid(),
    artifact_version_id: z.string().uuid(),
    symbol: z.enum(["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]),
    horizon: z.string().trim().min(1).max(32),
    condition: monitorConditionSchema,
    schedule: monitorScheduleSchema,
    timezone: monitorTimezoneSchema,
    quiet_hours: monitorQuietHoursSchema.nullable(),
    expires_at: absoluteTimestampSchema.nullable(),
    destination_ids: z.array(z.string().uuid()),
    schedule_version: z.number().int().positive(),
    cron_configured: z.boolean(),
    next_run_at: absoluteTimestampSchema.nullable(),
    latest_trigger: monitorTriggerSchema.nullable(),
    created_at: absoluteTimestampSchema,
    updated_at: absoluteTimestampSchema,
});

export const monitorListSchema = z.strictObject({
  items: z.array(monitorSchema),
});

export const monitorTriggerListSchema = z.strictObject({
  items: z.array(monitorTriggerSchema),
});

export type CreateMonitorRequest = z.infer<typeof createMonitorRequestSchema>;
export type Monitor = z.infer<typeof monitorSchema>;
export type MonitorCondition = z.infer<typeof monitorConditionSchema>;
export type MonitorList = z.infer<typeof monitorListSchema>;
export type MonitorQuietHours = z.infer<typeof monitorQuietHoursSchema>;
export type MonitorRunTaskType = z.infer<typeof monitorRunTaskTypeSchema>;
export type MonitorSchedule = z.infer<typeof monitorScheduleSchema>;
export type MonitorStatus = z.infer<typeof monitorStatusSchema>;
export type MonitorStatusFilter = z.infer<typeof monitorStatusFilterSchema>;
export type MonitorTrigger = z.infer<typeof monitorTriggerSchema>;
export type MonitorTriggerList = z.infer<typeof monitorTriggerListSchema>;
export type MonitorVersionMutation = z.infer<typeof monitorVersionMutationSchema>;
