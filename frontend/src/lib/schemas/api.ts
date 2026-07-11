import { z } from "zod";

export const apiErrorSchema = z.object({
  code: z.string().optional(),
  message: z.string(),
  detail: z.unknown().optional()
});

export type ApiError = z.infer<typeof apiErrorSchema>;

export const apiEnvelopeBaseSchema = z.object({
  ok: z.boolean(),
  error: apiErrorSchema.nullish(),
  trace_id: z.string().nullish()
});

export type ApiEnvelope<T> = {
  ok: boolean;
  data?: T;
  error?: ApiError | null;
  trace_id?: string | null;
};

export type ApiResult<T> =
  | { ok: true; data: T; traceId?: string | null }
  | { ok: false; error: ApiError; traceId?: string | null };

export function envelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return apiEnvelopeBaseSchema.extend({
    data: dataSchema.nullish()
  });
}
