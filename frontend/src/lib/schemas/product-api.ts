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
const absoluteTimestampSchema = z
  .string()
  .regex(
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/,
    "Timestamp must include an explicit UTC offset",
  )
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

export const actionSchema = z.enum([
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

export const marketAnalysisSchema = z.strictObject({
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

const reviewCommentSchema = z.string().trim().min(1).max(1000);
const reviewTextSchema = z.string().trim().min(1).max(2000);

const artifactReviewEditShape = {
  regime: z.enum(["risk_on", "risk_off", "event_compression", "surprise_repricing"]),
  factor_scores: z.record(z.string(), z.number().int().min(-2).max(2)),
  total_score: z.number().int(),
  main_action: actionSchema,
  reference_price: positiveNumberSchema,
  entry_trigger: positiveNumberSchema.nullable(),
  stop_price: positiveNumberSchema.nullable(),
  target_1: positiveNumberSchema.nullable(),
  target_2: positiveNumberSchema.nullable(),
  probability: ratioSchema,
  position_size_class: z.enum(["light", "standard", "heavy", "none"]),
  max_leverage: z.number().int().min(1),
  risk_pct: ratioSchema,
  root_cause_chain: z.array(z.string().trim().min(1).max(2000)).min(1),
  why_not_opposite: reviewTextSchema,
  invalidation: reviewTextSchema,
  unavailable_data: z.array(z.string()),
  manual_execution_required: z.boolean(),
  expires_in_seconds: z.number().int().positive(),
};

export const artifactReviewEditsSchema = z
  .strictObject({
    regime: artifactReviewEditShape.regime.optional(),
    factor_scores: artifactReviewEditShape.factor_scores.optional(),
    total_score: artifactReviewEditShape.total_score.optional(),
    main_action: artifactReviewEditShape.main_action.optional(),
    reference_price: artifactReviewEditShape.reference_price.optional(),
    entry_trigger: artifactReviewEditShape.entry_trigger.optional(),
    stop_price: artifactReviewEditShape.stop_price.optional(),
    target_1: artifactReviewEditShape.target_1.optional(),
    target_2: artifactReviewEditShape.target_2.optional(),
    probability: artifactReviewEditShape.probability.optional(),
    position_size_class: artifactReviewEditShape.position_size_class.optional(),
    max_leverage: artifactReviewEditShape.max_leverage.optional(),
    risk_pct: artifactReviewEditShape.risk_pct.optional(),
    root_cause_chain: artifactReviewEditShape.root_cause_chain.optional(),
    why_not_opposite: artifactReviewEditShape.why_not_opposite.optional(),
    invalidation: artifactReviewEditShape.invalidation.optional(),
    unavailable_data: artifactReviewEditShape.unavailable_data.optional(),
    manual_execution_required: artifactReviewEditShape.manual_execution_required.optional(),
    expires_in_seconds: artifactReviewEditShape.expires_in_seconds.optional(),
  })
  .refine((edits) => Object.keys(edits).length > 0, {
    message: "At least one artifact edit is required",
  });

const reviewResponseBase = {
  response_version: z.number().int().min(1),
  comment: reviewCommentSchema.nullable().optional(),
};

export const interruptResponseSchema = z.discriminatedUnion("action", [
  z.strictObject({
    ...reviewResponseBase,
    action: z.literal("approve"),
    edits: z.null().optional(),
  }),
  z.strictObject({
    ...reviewResponseBase,
    action: z.literal("reject"),
    edits: z.null().optional(),
  }),
  z.strictObject({
    ...reviewResponseBase,
    action: z.literal("edit"),
    edits: artifactReviewEditsSchema,
  }),
]);

export const officialReviewPayloadSchema = z.strictObject({
  kind: z.literal("artifact_review"),
  schema_version: z.literal("1.0"),
  allowed_actions: z.tuple([
    z.literal("approve"),
    z.literal("reject"),
    z.literal("edit"),
  ]),
  review_iteration: z.number().int().min(1),
  artifact: analysisArtifactSchema,
});

const persistedArtifactReviewEditsSchema = z.strictObject({
  regime: artifactReviewEditShape.regime.nullable().optional(),
  factor_scores: artifactReviewEditShape.factor_scores.nullable().optional(),
  total_score: artifactReviewEditShape.total_score.nullable().optional(),
  main_action: artifactReviewEditShape.main_action.nullable().optional(),
  reference_price: artifactReviewEditShape.reference_price.nullable().optional(),
  entry_trigger: artifactReviewEditShape.entry_trigger.nullable().optional(),
  stop_price: artifactReviewEditShape.stop_price.nullable().optional(),
  target_1: artifactReviewEditShape.target_1.nullable().optional(),
  target_2: artifactReviewEditShape.target_2.nullable().optional(),
  probability: artifactReviewEditShape.probability.nullable().optional(),
  position_size_class: artifactReviewEditShape.position_size_class.nullable().optional(),
  max_leverage: artifactReviewEditShape.max_leverage.nullable().optional(),
  risk_pct: artifactReviewEditShape.risk_pct.nullable().optional(),
  root_cause_chain: artifactReviewEditShape.root_cause_chain.nullable().optional(),
  why_not_opposite: artifactReviewEditShape.why_not_opposite.nullable().optional(),
  invalidation: artifactReviewEditShape.invalidation.nullable().optional(),
  unavailable_data: artifactReviewEditShape.unavailable_data.nullable().optional(),
  manual_execution_required: artifactReviewEditShape.manual_execution_required.nullable().optional(),
  expires_in_seconds: artifactReviewEditShape.expires_in_seconds.nullable().optional(),
});

const persistedInterruptResponseSchema = z.discriminatedUnion("action", [
  z.strictObject({
    action: z.literal("approve"),
    comment: reviewCommentSchema.nullable().optional(),
    edits: z.null().optional(),
  }),
  z.strictObject({
    action: z.literal("reject"),
    comment: reviewCommentSchema.nullable().optional(),
    edits: z.null().optional(),
  }),
  z.strictObject({
    action: z.literal("edit"),
    comment: reviewCommentSchema.nullable().optional(),
    edits: persistedArtifactReviewEditsSchema,
  }),
]);

export const inboxQueryStatusSchema = z.enum([
  "active",
  "pending",
  "responding",
  "resolved",
  "expired",
  "all",
]);

export const inboxItemStatusSchema = z.enum([
  "pending",
  "responding",
  "resolved",
  "expired",
  "cancelled",
]);

export const inboxCursorSchema = z
  .string()
  .min(1)
  .max(2048)
  .regex(/^[A-Za-z0-9_-]+$/, "Invalid Inbox cursor");

export const inboxItemSchema = z
  .strictObject({
    task_id: z.string().trim().min(1).max(255),
    status: inboxItemStatusSchema,
    payload: officialReviewPayloadSchema,
    response: persistedInterruptResponseSchema.nullable().optional().default(null),
    expires_at: absoluteTimestampSchema.nullable().optional().default(null),
    responded_at: absoluteTimestampSchema.nullable().optional().default(null),
    created_at: absoluteTimestampSchema,
    updated_at: absoluteTimestampSchema,
    symbol: productSymbolSchema,
    horizon: z.string().trim().min(1).max(32),
    query_text: z.string().trim().min(1).max(2000).nullable().optional().default(null),
  })
  .superRefine((item, context) => {
    if (item.payload.artifact.analysis.instrument !== item.symbol) {
      context.addIssue({
        code: "custom",
        message: "Inbox review instrument must match its task symbol",
        path: ["payload", "artifact", "analysis", "instrument"],
      });
    }
    if (item.payload.artifact.analysis.horizon !== item.horizon) {
      context.addIssue({
        code: "custom",
        message: "Inbox review horizon must match its task horizon",
        path: ["payload", "artifact", "analysis", "horizon"],
      });
    }
    if (item.responded_at !== null && item.response === null) {
      context.addIssue({
        code: "custom",
        message: "A responded Inbox item requires its accepted response",
        path: ["response"],
      });
    }
    if (item.status === "pending" && (item.response !== null || item.responded_at !== null)) {
      context.addIssue({
        code: "custom",
        message: "A pending Inbox item cannot already contain a response",
        path: ["status"],
      });
    }
    if (
      (item.status === "responding" || item.status === "resolved")
      && item.response === null
    ) {
      context.addIssue({
        code: "custom",
        message: `A ${item.status} Inbox item requires an accepted response`,
        path: ["status"],
      });
    }
    if (item.status === "resolved" && item.responded_at === null) {
      context.addIssue({
        code: "custom",
        message: "A resolved Inbox item requires a response timestamp",
        path: ["responded_at"],
      });
    }
    if (item.status === "expired" && item.expires_at === null) {
      context.addIssue({
        code: "custom",
        message: "An expired Inbox item requires an expiry timestamp",
        path: ["expires_at"],
      });
    }
  });

export const inboxViewSchema = z.strictObject({
  items: z.array(inboxItemSchema),
  next_cursor: inboxCursorSchema.nullable().optional().default(null),
});

export const pendingInterruptSchema = z.strictObject({
  task_id: z.string().trim().min(1).max(255),
  interrupt_id: z.string().trim().min(1).max(255),
  response_version: z.number().int().min(1),
  status: z.enum(["pending", "responding"]),
  payload: officialReviewPayloadSchema,
  response: persistedInterruptResponseSchema.nullable().optional().default(null),
  expires_at: absoluteTimestampSchema.nullable().optional().default(null),
  responded_at: absoluteTimestampSchema.nullable().optional().default(null),
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
    cancel_requested_at: timestampSchema.nullable().default(null),
    artifact: analysisArtifactSchema.nullable().default(null),
    errors: z.array(productErrorSchema).default([]),
    agent_stream: agentStreamBindingSchema.nullable().default(null),
    market_snapshot: marketSnapshotSchema.nullable().default(null),
    web_evidence: z.array(webEvidenceSchema).default([]),
    pending_interrupts: z.array(pendingInterruptSchema).default([]),
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
    for (const [index, pendingInterrupt] of task.pending_interrupts.entries()) {
      if (pendingInterrupt.task_id !== task.task_id) {
        context.addIssue({
          code: "custom",
          message: "Pending interrupt task ID must match its task",
          path: ["pending_interrupts", index, "task_id"],
        });
      }
      if (pendingInterrupt.status === "pending" && pendingInterrupt.response !== null) {
        context.addIssue({
          code: "custom",
          message: "A pending interrupt cannot already contain a response",
          path: ["pending_interrupts", index, "response"],
        });
      }
      if (pendingInterrupt.status === "responding" && pendingInterrupt.response === null) {
        context.addIssue({
          code: "custom",
          message: "A responding interrupt requires its accepted response",
          path: ["pending_interrupts", index, "response"],
        });
      }
    }
  });

export type AnalysisSubmission = z.infer<typeof analysisSubmissionSchema>;
export type AgentStreamBinding = z.infer<typeof agentStreamBindingSchema>;
export type ArtifactReviewEdits = z.infer<typeof artifactReviewEditsSchema>;
export type InboxItem = z.infer<typeof inboxItemSchema>;
export type InboxItemStatus = z.infer<typeof inboxItemStatusSchema>;
export type InboxQueryStatus = z.infer<typeof inboxQueryStatusSchema>;
export type InboxView = z.infer<typeof inboxViewSchema>;
export type InterruptResponse = z.infer<typeof interruptResponseSchema>;
export type MarketSnapshot = z.infer<typeof marketSnapshotSchema>;
export type OfficialReviewPayload = z.infer<typeof officialReviewPayloadSchema>;
export type PendingInterrupt = z.infer<typeof pendingInterruptSchema>;
export type ProductError = z.infer<typeof productErrorSchema>;
export type ProductRunList = z.infer<typeof productRunListSchema>;
export type ProductRunSummary = z.infer<typeof productRunSummarySchema>;
export type ProductSymbol = z.infer<typeof productSymbolSchema>;
export type ProductTask = z.infer<typeof productTaskSchema>;
export type RunStatus = z.infer<typeof runStatusSchema>;
export type WebEvidence = z.infer<typeof webEvidenceSchema>;
