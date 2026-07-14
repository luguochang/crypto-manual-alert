import { z } from "zod";

export const productSymbolSchema = z.enum([
  "BTC-USDT-SWAP",
  "ETH-USDT-SWAP",
  "SOL-USDT-SWAP",
]);

export const runStatusSchema = z.enum([
  "queued",
  "running",
  "waiting_human",
  "succeeded",
  "blocked",
  "failed",
  "cancelled",
]);

export const analysisSubmissionSchema = z.strictObject({
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  query_text: z.string().trim().min(1).max(2000),
  notify: z.boolean().default(false),
});

const finiteNumberSchema = z
  .union([
    z.number(),
    z.string().trim().regex(/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/),
  ])
  .transform((value) => Number(value))
  .pipe(z.number().finite());

const positiveNumberSchema = finiteNumberSchema.pipe(z.number().positive());
const nonNegativeNumberSchema = finiteNumberSchema.pipe(z.number().nonnegative());
const ratioSchema = finiteNumberSchema.pipe(z.number().min(0).max(1));
const optionalPriceSchema = positiveNumberSchema.nullable().optional().default(null);
const timestampSchema = z
  .string()
  .refine((value) => !Number.isNaN(Date.parse(value)), "Invalid timestamp");
const sourceUrlSchema = z
  .string()
  .url()
  .refine((value) => {
    const protocol = new URL(value).protocol;
    return protocol === "http:" || protocol === "https:";
  }, "Only HTTP and HTTPS source links are allowed");

const tickerSchema = z.strictObject({
  last: positiveNumberSchema,
  bid: optionalPriceSchema,
  ask: optionalPriceSchema,
  volume_24h: nonNegativeNumberSchema.nullable().optional().default(null),
});

const priceLevelSchema = z.strictObject({
  price: positiveNumberSchema,
  size: positiveNumberSchema,
});

const orderBookSchema = z.strictObject({
  bids: z.array(priceLevelSchema).default([]),
  asks: z.array(priceLevelSchema).default([]),
});

const candleSchema = z.strictObject({
  timestamp: timestampSchema,
  open: positiveNumberSchema,
  high: positiveNumberSchema,
  low: positiveNumberSchema,
  close: positiveNumberSchema,
  volume: nonNegativeNumberSchema,
});

export const marketSnapshotSchema = z.strictObject({
  symbol: productSymbolSchema,
  fetched_at: timestampSchema,
  source_level: z.literal("exchange_native"),
  ticker: tickerSchema.nullable().optional().default(null),
  mark_price: optionalPriceSchema,
  index_price: optionalPriceSchema,
  funding_rate: finiteNumberSchema.nullable().optional().default(null),
  open_interest: nonNegativeNumberSchema.nullable().optional().default(null),
  order_book: orderBookSchema.nullable().optional().default(null),
  candles: z.array(candleSchema).default([]),
});

export const webEvidenceSchema = z.strictObject({
  query: z.string(),
  final_url: sourceUrlSchema,
  redirect_chain: z.array(sourceUrlSchema).default([]),
  http_status: z.number().int().nullable().optional().default(null),
  fetched_at: timestampSchema,
  published_at: timestampSchema.nullable().optional().default(null),
  content_hash: z.string(),
  parser_version: z.string(),
  title: z.string(),
  author: z.string().nullable().optional().default(null),
  source: z.string(),
  excerpt: z.string(),
  evidence_relation: z.string(),
});

const actionSchema = z.enum([
  "open_long",
  "open_short",
  "hold_long",
  "hold_short",
  "close_long",
  "close_short",
  "flip_long_to_short",
  "flip_short_to_long",
  "trigger_long",
  "trigger_short",
  "no_trade",
]);

export const productRunSummarySchema = z.strictObject({
  run_id: z.string().uuid(),
  task_id: z.string().uuid(),
  attempt: z.number().int().positive(),
  status: runStatusSchema,
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  created_at: timestampSchema,
  finished_at: timestampSchema.nullable().default(null),
  main_action: actionSchema.nullable().default(null),
});

export const productRunListSchema = z.strictObject({
  items: z.array(productRunSummarySchema),
  limit: z.number().int().min(1).max(100),
});

const marketAnalysisSchema = z.strictObject({
  regime: z.enum(["risk_on", "risk_off", "event_compression", "surprise_repricing"]),
  factor_scores: z.record(z.string(), z.number().int().min(-2).max(2)),
  total_score: z.number().int(),
  main_action: actionSchema,
  instrument: productSymbolSchema,
  horizon: z.string().min(1),
  reference_price: positiveNumberSchema,
  entry_trigger: optionalPriceSchema,
  stop_price: optionalPriceSchema,
  target_1: optionalPriceSchema,
  target_2: optionalPriceSchema,
  probability: ratioSchema,
  position_size_class: z.enum(["light", "standard", "heavy", "none"]),
  max_leverage: z.number().int().min(1),
  risk_pct: ratioSchema,
  root_cause_chain: z.array(z.string().trim().min(1)).min(1),
  why_not_opposite: z.string().trim().min(1),
  invalidation: z.string(),
  unavailable_data: z.array(z.string()).default([]),
  manual_execution_required: z.boolean(),
  expires_in_seconds: z.number().int().positive(),
});

const evidenceVerdictSchema = z
  .strictObject({
    sufficient: z.boolean(),
    confidence_cap: ratioSchema,
    missing_required: z.array(z.string()).default([]),
    missing_optional: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
  })
  .superRefine((verdict, context) => {
    if (verdict.sufficient && verdict.missing_required.length > 0) {
      context.addIssue({
        code: "custom",
        message: "Sufficient evidence cannot have missing required fields",
        path: ["missing_required"],
      });
    }
    if (!verdict.sufficient && verdict.missing_required.length === 0) {
      context.addIssue({
        code: "custom",
        message: "Insufficient evidence must identify missing required fields",
        path: ["missing_required"],
      });
    }
    if (!verdict.sufficient && verdict.confidence_cap !== 0) {
      context.addIssue({
        code: "custom",
        message: "Insufficient evidence must have a zero confidence cap",
        path: ["confidence_cap"],
      });
    }
  });

const riskVerdictSchema = z
  .strictObject({
    allowed: z.boolean(),
    blocked_reasons: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    confidence_cap: ratioSchema,
  })
  .superRefine((verdict, context) => {
    if (verdict.allowed && verdict.blocked_reasons.length > 0) {
      context.addIssue({
        code: "custom",
        message: "An allowed risk verdict cannot have blocked reasons",
        path: ["blocked_reasons"],
      });
    }
    if (!verdict.allowed && verdict.blocked_reasons.length === 0) {
      context.addIssue({
        code: "custom",
        message: "A blocked risk verdict must identify at least one reason",
        path: ["blocked_reasons"],
      });
    }
  });

export const analysisArtifactSchema = z.strictObject({
  artifact_type: z.literal("analysis_report"),
  schema_version: z.string().min(1),
  content_version: z.number().int().min(1),
  status: z.enum(["draft", "streaming", "committed", "failed"]),
  analysis: marketAnalysisSchema,
  evidence_verdict: evidenceVerdictSchema,
  risk_verdict: riskVerdictSchema,
  source_references: z.array(sourceUrlSchema).default([]),
});

export const productErrorSchema = z.strictObject({
  code: z.string().trim().min(1),
  message: z.string().trim().min(1),
  retryable: z.boolean().default(false),
  provider: z.string().regex(/^[A-Za-z0-9._-]+$/).max(64).nullable().optional().default(null),
  error_type: z.string().regex(/^[A-Za-z0-9._-]+$/).max(128).nullable().optional().default(null),
  attempt: z.number().int().min(1).max(100).nullable().optional().default(null),
});

export const agentStreamBindingSchema = z.strictObject({
  protocol: z.literal("langgraph-v2"),
  assistant_id: z.string().trim().min(1).max(255),
  thread_id: z.string().trim().min(1).max(255),
  run_id: z.string().trim().min(1).max(255),
});

export const productTaskSchema = z
  .strictObject({
    task_id: z.string().trim().min(1),
    status: runStatusSchema,
    symbol: productSymbolSchema,
    horizon: z.string().trim().min(1),
    query_text: z.string().trim().min(1).max(2000).nullable().default(null),
    created_at: timestampSchema,
    completed_at: timestampSchema.nullable().default(null),
    artifact: analysisArtifactSchema.nullable().default(null),
    errors: z.array(productErrorSchema).default([]),
    agent_stream: agentStreamBindingSchema.nullable().default(null),
    market_snapshot: marketSnapshotSchema.nullable().default(null),
    web_evidence: z.array(webEvidenceSchema).default([]),
  })
  .superRefine((task, context) => {
    const artifact = task.artifact;

    if (task.status === "succeeded" && artifact?.status !== "committed") {
      context.addIssue({
        code: "custom",
        message: "A succeeded task requires a committed artifact",
        path: ["artifact"],
      });
    }
    if (artifact?.status === "committed" && !artifact.risk_verdict.allowed) {
      context.addIssue({
        code: "custom",
        message: "A committed artifact requires an allowed risk verdict",
        path: ["artifact", "risk_verdict", "allowed"],
      });
    }
    if (artifact?.status === "committed" && !artifact.evidence_verdict.sufficient) {
      context.addIssue({
        code: "custom",
        message: "A committed artifact requires sufficient evidence",
        path: ["artifact", "evidence_verdict", "sufficient"],
      });
    }
    if (task.status === "blocked" && artifact?.status === "draft") {
      if (artifact.risk_verdict.allowed) {
        context.addIssue({
          code: "custom",
          message: "A blocked task cannot contain an allowed risk verdict",
          path: ["artifact", "risk_verdict", "allowed"],
        });
      }
    }
    if (artifact?.analysis.instrument !== undefined && artifact.analysis.instrument !== task.symbol) {
      context.addIssue({
        code: "custom",
        message: "Artifact instrument must match task symbol",
        path: ["artifact", "analysis", "instrument"],
      });
    }
    if (artifact?.analysis.horizon !== undefined && artifact.analysis.horizon !== task.horizon) {
      context.addIssue({
        code: "custom",
        message: "Artifact horizon must match task horizon",
        path: ["artifact", "analysis", "horizon"],
      });
    }
  });

export type AnalysisSubmission = z.infer<typeof analysisSubmissionSchema>;
export type AgentStreamBinding = z.infer<typeof agentStreamBindingSchema>;
export type MarketSnapshot = z.infer<typeof marketSnapshotSchema>;
export type ProductError = z.infer<typeof productErrorSchema>;
export type ProductRunList = z.infer<typeof productRunListSchema>;
export type ProductRunSummary = z.infer<typeof productRunSummarySchema>;
export type ProductSymbol = z.infer<typeof productSymbolSchema>;
export type ProductTask = z.infer<typeof productTaskSchema>;
export type RunStatus = z.infer<typeof runStatusSchema>;
export type WebEvidence = z.infer<typeof webEvidenceSchema>;
