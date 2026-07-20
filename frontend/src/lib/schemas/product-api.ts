import { z } from "zod";

import { stableFingerprint } from "@/lib/stable-fingerprint";

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

export const taskTypeSchema = z.enum(["market_analysis", "deep_research"]);

export const taskProjectionScopeSchema = z
  .strictObject({
    mode: z.enum(["latest", "selected_run"]).default("latest"),
    selected_run_id: z.string().uuid().nullable().optional().default(null),
  })
  .superRefine((scope, context) => {
    if (scope.mode === "latest" && scope.selected_run_id !== null) {
      context.addIssue({
        code: "custom",
        message: "Latest Task projection cannot select a Run",
        path: ["selected_run_id"],
      });
    }
    if (scope.mode === "selected_run" && scope.selected_run_id === null) {
      context.addIssue({
        code: "custom",
        message: "Selected Run Task projection requires its Run ID",
        path: ["selected_run_id"],
      });
    }
  });

export const analysisSubmissionSchema = z.strictObject({
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  query_text: z.string().trim().min(1).max(2000),
  notify: z.boolean().default(false),
});

export const deepResearchSubmissionSchema = z.strictObject({
  task_type: z.literal("deep_research").default("deep_research"),
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  query_text: z.string().trim().min(1).max(4000),
});

export const forkSubmissionSchema = z.strictObject({
  source_run_id: z.string().uuid(),
  checkpoint_id: z.string().trim().min(1).max(255).nullable().optional(),
});

const finiteNumberSchema = z
  .union([
    z.number(),
    z.string().trim().regex(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/),
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
  source_level: z.enum(["exchange_native", "controlled_dependency", "web_search_verified"]),
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
  task_type: taskTypeSchema.default("market_analysis"),
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

export const feedbackSubmissionSchema = z.strictObject({
  rating: z.enum(["positive", "negative"]),
  comment: z.string().trim().max(2000).nullable().optional().default(null),
});

export const feedbackSchema = z.strictObject({
  feedback_id: z.string().uuid(),
  task_id: z.string().uuid(),
  run_id: z.string().uuid(),
  artifact_version_id: z.string().uuid().nullable().default(null),
  rating: z.enum(["positive", "negative"]),
  comment: z.string().trim().max(2000).nullable().default(null),
  created_at: timestampSchema,
  updated_at: timestampSchema,
});

export const runDetailSchema = z.strictObject({
  run: productRunSummarySchema,
  task: z.lazy(() => productTaskSchema),
  run_projection: z.lazy(() => productTaskSchema),
  is_current_run: z.boolean(),
  feedback: feedbackSchema.nullable().default(null),
}).superRefine((detail, context) => {
  if (detail.task.projection_scope.mode !== "latest") {
    context.addIssue({
      code: "custom",
      message: "Run detail Task must be the current projection",
      path: ["task", "projection_scope"],
    });
  }
  if (
    detail.run_projection.projection_scope.mode !== "selected_run"
    || detail.run_projection.projection_scope.selected_run_id !== detail.run.run_id
  ) {
    context.addIssue({
      code: "custom",
      message: "Run detail history must match its selected Run",
      path: ["run_projection", "projection_scope"],
    });
  }
  if (
    detail.task.task_id !== detail.run.task_id
    || detail.run_projection.task_id !== detail.run.task_id
  ) {
    context.addIssue({
      code: "custom",
      message: "Run detail projections must match their Run Task",
      path: ["task", "task_id"],
    });
  }
});

export const artifactLibraryItemSchema = z.strictObject({
  artifact_id: z.string().uuid(),
  artifact_version_id: z.string().uuid(),
  artifact_type: z.string().trim().min(1).max(64),
  schema_version: z.string().trim().min(1).max(32),
  version_number: z.number().int().positive(),
  status: z.enum(["draft", "streaming", "committed", "failed"]),
  task_id: z.string().uuid(),
  run_id: z.string().uuid(),
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  main_action: actionSchema.nullable().default(null),
  created_at: timestampSchema,
});

export const artifactLibrarySchema = z.strictObject({
  items: z.array(artifactLibraryItemSchema),
  limit: z.number().int().min(1).max(100),
});

const homeWatchlistItemSchema = z.strictObject({
  symbol: productSymbolSchema,
  latest_snapshot: marketSnapshotSchema.nullable().default(null),
  created_at: timestampSchema,
});

const homeActiveTaskSchema = z.strictObject({
  task_id: z.string().uuid(),
  run_id: z.string().uuid().nullable().default(null),
  status: z.enum(["queued", "running", "waiting_human"]),
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  created_at: timestampSchema,
});

export const homeViewSchema = z.strictObject({
  watchlist: z.array(homeWatchlistItemSchema),
  active_tasks: z.array(homeActiveTaskSchema),
  pending_inbox_count: z.number().int().nonnegative(),
  recent_reports: z.array(artifactLibraryItemSchema),
});

export const notificationAttemptSchema = z.strictObject({
  attempt_id: z.string().uuid(),
  attempt_number: z.number().int().min(1).max(5),
  trigger: z.enum(["automatic", "manual"]),
  result: z.enum([
    "leased",
    "sending",
    "delivered",
    "failed_retryable",
    "failed_terminal",
    "unknown",
    "released",
  ]),
  reason: z.string().trim().min(1).max(128).nullable().default(null),
  delay_seconds: z.number().int().nonnegative(),
  retry_after_seconds: z.number().int().nonnegative().nullable().default(null),
  cost_units: z.string().regex(/^\d+(?:\.\d{1,6})?$/),
  provider_receipt: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/).nullable().default(null),
  error_code: z.string().regex(/^[A-Za-z0-9_.:-]{1,128}$/).nullable().default(null),
  created_at: absoluteTimestampSchema,
  finished_at: absoluteTimestampSchema.nullable().default(null),
});

export const notificationSchema = z
  .strictObject({
    notification_id: z.string().uuid(),
    task_id: z.string().uuid(),
    run_id: z.string().uuid(),
    artifact_id: z.string().uuid(),
    artifact_version_id: z.string().uuid(),
    decision_id: z.string().uuid(),
    decision_version: z.number().int().positive(),
    channel: z.string().regex(/^[A-Za-z0-9._-]{1,64}$/),
    type: z.string().regex(/^[A-Za-z0-9._-]{1,128}$/),
    status: z.enum([
      "planned",
      "leased",
      "sending",
      "delivered",
      "failed_retryable",
      "failed_terminal",
      "unknown",
    ]),
    attempt_count: z.number().int().min(0).max(5),
    manual_resend_pending: z.boolean(),
    manual_resend_available: z.boolean(),
    manual_resend_requested_at: absoluteTimestampSchema.nullable().default(null),
    available_at: absoluteTimestampSchema,
    delivered_at: absoluteTimestampSchema.nullable().default(null),
    terminal_at: absoluteTimestampSchema.nullable().default(null),
    created_at: absoluteTimestampSchema,
    updated_at: absoluteTimestampSchema,
    attempts: z.array(notificationAttemptSchema).max(5),
  })
  .superRefine((notification, context) => {
    if (notification.attempts.length !== notification.attempt_count) {
      context.addIssue({
        code: "custom",
        message: "Notification attempt ledger must match attempt_count",
        path: ["attempts"],
      });
    }
    if (
      notification.manual_resend_pending
      !== (notification.manual_resend_requested_at !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Manual resend state is inconsistent",
        path: ["manual_resend_pending"],
      });
    }
    if (notification.status === "delivered" && notification.delivered_at === null) {
      context.addIssue({
        code: "custom",
        message: "Delivered notification requires delivered_at",
        path: ["delivered_at"],
      });
    }
  });

export const notificationListSchema = z.strictObject({
  task_id: z.string().uuid(),
  items: z.array(notificationSchema),
});

export const notificationResendSubmissionSchema = z.strictObject({
  reason: z.string().trim().min(4).max(500),
});

export const notificationSettingsSchema = z
  .strictObject({
    channel: z.literal("bark"),
    enabled: z.boolean(),
    configured: z.boolean(),
    updated_at: absoluteTimestampSchema.nullable(),
  })
  .superRefine((settings, context) => {
    if (settings.enabled && !settings.configured) {
      context.addIssue({
        code: "custom",
        message: "Enabled notification settings must be configured",
        path: ["configured"],
      });
    }
  });

export const notificationSettingsUpdateSchema = z.strictObject({
  enabled: z.boolean(),
  device_key: z.string().trim().min(8).max(255).optional(),
});

export const dataLifecyclePolicySchema = z.strictObject({
  id: z.string().uuid(),
  tenant_id: z.string().uuid(),
  workspace_id: z.string().uuid(),
  owner_user_id: z.string().uuid(),
  product_retention_days: z.number().int().positive(),
  artifact_retention_days: z.number().int().positive(),
  task_retention_days: z.number().int().positive(),
  run_retention_days: z.number().int().positive(),
  decision_retention_days: z.number().int().positive(),
  usage_retention_days: z.number().int().positive(),
  completed_checkpoint_retention_days: z.number().int().positive(),
  technical_projection_retention_days: z.number().int().positive(),
  log_retention_days: z.number().int().positive(),
  backup_retention_days: z.number().int().positive(),
  retain_raw_prompt: z.boolean(),
  retain_raw_response: z.boolean(),
  legal_hold_active: z.boolean(),
  legal_hold_reason: z.string().trim().min(1).max(500).nullable(),
  created_at: absoluteTimestampSchema,
  updated_at: absoluteTimestampSchema,
});

export const dataLifecyclePolicyUpdateSchema = z.strictObject({
  product_retention_days: z.number().int().positive().max(3650).optional(),
  artifact_retention_days: z.number().int().positive().max(3650).optional(),
  task_retention_days: z.number().int().positive().max(3650).optional(),
  run_retention_days: z.number().int().positive().max(3650).optional(),
  decision_retention_days: z.number().int().positive().max(3650).optional(),
  usage_retention_days: z.number().int().positive().max(3650).optional(),
  completed_checkpoint_retention_days: z.number().int().positive().max(3650).optional(),
  technical_projection_retention_days: z.number().int().positive().max(3650).optional(),
  log_retention_days: z.number().int().positive().max(3650).optional(),
  backup_retention_days: z.number().int().positive().max(3650).optional(),
  retain_raw_prompt: z.boolean().optional(),
  retain_raw_response: z.boolean().optional(),
  legal_hold_active: z.boolean().optional(),
  legal_hold_reason: z.string().trim().min(1).max(500).nullable().optional(),
});

export const dataExportSchema = z.strictObject({
  id: z.string().uuid(),
  tenant_id: z.string().uuid(),
  workspace_id: z.string().uuid(),
  owner_user_id: z.string().uuid(),
  scope: z.literal("user_data"),
  idempotency_key: z.string().trim().min(1).max(255),
  status: z.enum(["queued", "running", "succeeded", "failed"]),
  attempt: z.number().int().nonnegative(),
  lease_expires_at: absoluteTimestampSchema.nullable(),
  requested_at: absoluteTimestampSchema,
  completed_at: absoluteTimestampSchema.nullable(),
  expired_at: absoluteTimestampSchema.nullable(),
  manifest_version: z.number().int().positive().nullable(),
  manifest_hash: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
  last_error: z.string().trim().min(1).max(500).nullable(),
  created_at: absoluteTimestampSchema,
  updated_at: absoluteTimestampSchema,
});

export const dataExportManifestSchema = z.strictObject({
  export_id: z.string().uuid(),
  status: dataExportSchema.shape.status,
  manifest_version: z.number().int().positive().nullable(),
  manifest_hash: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
  manifest: z.record(z.string(), z.unknown()).nullable(),
});

export const dataExportBundleSchema = z.strictObject({
  export_id: z.string().uuid(),
  status: dataExportSchema.shape.status,
  manifest_version: z.number().int().positive().nullable(),
  manifest_hash: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
  bundle: z.record(z.string(), z.unknown()).nullable(),
});

export const dataDeletionSchema = z.strictObject({
  id: z.string().uuid(),
  tenant_id: z.string().uuid(),
  workspace_id: z.string().uuid(),
  owner_user_id: z.string().uuid(),
  scope: z.literal("user_data"),
  idempotency_key: z.string().trim().min(1).max(255),
  status: z.enum([
    "queued",
    "running",
    "pending_external",
    "succeeded",
    "blocked_legal_hold",
    "failed",
  ]),
  attempt: z.number().int().nonnegative(),
  lease_expires_at: absoluteTimestampSchema.nullable(),
  requested_at: absoluteTimestampSchema,
  completed_at: absoluteTimestampSchema.nullable(),
  expired_at: absoluteTimestampSchema.nullable(),
  legal_hold_active: z.boolean(),
  legal_hold_reason: z.string().trim().min(1).max(500).nullable(),
  system_status: z.record(z.string(), z.string().trim().min(1)),
  external_deletion_reference: z.record(z.string(), z.unknown()),
  last_error: z.string().trim().min(1).max(500).nullable(),
  created_at: absoluteTimestampSchema,
  updated_at: absoluteTimestampSchema,
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

const artifactProvenanceSchema = z.strictObject({
  market_provider: z.string().trim().min(1).max(64),
  search_provider: z.string().trim().min(1).max(128),
  search_parser_version: z.string().trim().min(1).max(128),
  model_provider: z.string().trim().min(1).max(64),
  model_name: z.string().trim().min(1).max(128),
  model_endpoint_host: z.string().trim().min(1).max(255).nullable().default(null),
  model_audits: z.array(
    z.strictObject({
      prompt_version: z.string().trim().min(1).max(128),
      call_count: z.number().int().nonnegative(),
      input_tokens: z.number().int().nonnegative().nullable().default(null),
      output_tokens: z.number().int().nonnegative().nullable().default(null),
      total_tokens: z.number().int().nonnegative().nullable().default(null),
      latency_ms: z.number().finite().nonnegative(),
      observation_ids: z.array(z.string().trim().min(1)).max(32).default([]),
    }),
  ).default([]),
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
  provenance: artifactProvenanceSchema.nullable().optional(),
});

const modelExecutionAuditSchema = z.strictObject({
  prompt_version: z.string().trim().min(1).max(128),
  call_count: z.number().int().nonnegative(),
  input_tokens: z.number().int().nonnegative().nullable().default(null),
  output_tokens: z.number().int().nonnegative().nullable().default(null),
  total_tokens: z.number().int().nonnegative().nullable().default(null),
  latency_ms: z.number().finite().nonnegative(),
  observation_ids: z.array(z.string().trim().min(1)).max(32).default([]),
});

const sourceIndexSchema = z.number().int().min(1).max(8);

const citedResearchFindingSchema = z
  .strictObject({
    claim: z.string().trim().min(1).max(2000),
    source_indexes: z.array(sourceIndexSchema).min(1).max(8),
  })
  .superRefine((finding, context) => {
    if (new Set(finding.source_indexes).size !== finding.source_indexes.length) {
      context.addIssue({
        code: "custom",
        message: "Finding source indexes must be unique",
        path: ["source_indexes"],
      });
    }
  });

export const deepResearchReportSchema = z.strictObject({
  executive_summary: z.string().trim().min(1).max(6000),
  sections: z.array(z.strictObject({
    title: z.string().trim().min(1).max(200),
    summary: z.string().trim().min(1).max(4000),
    findings: z.array(citedResearchFindingSchema).min(1).max(12),
  })).min(1).max(8),
  risk_notes: z.array(z.string().trim().min(1)).max(12).default([]),
  evidence_gaps: z.array(z.string().trim().min(1)).max(12).default([]),
});

const deepResearchSearchFailureSchema = z.strictObject({
  query_index: z.number().int().min(1).max(3),
  provider: z.enum([
    "builtin_web_search",
    "tavily",
    "ddgs_metasearch",
    "deep_research_search",
    "search",
  ]),
  error_kind: z.enum([
    "timeout",
    "server_error",
    "rate_limited",
    "connection_error",
    "unverified_server_tool_call",
    "missing_provider_citation",
    "missing_verified_evidence",
    "invalid_provider_response",
    "provider_error",
  ]),
  retryable: z.boolean(),
  attempt: z.number().int().min(1).max(3).nullable().default(null),
});

const deepResearchSearchCoverageSchema = z
  .strictObject({
    status: z.enum(["complete", "partial"]),
    attempted_queries: z.number().int().min(1).max(3),
    successful_queries: z.number().int().min(1).max(3),
    failed_queries: z.array(deepResearchSearchFailureSchema).max(2).default([]),
  })
  .superRefine((coverage, context) => {
    const failedIndexes = coverage.failed_queries.map((failure) => failure.query_index);
    const orderedIndexes = [...new Set(failedIndexes)].sort((left, right) => left - right);
    if (
      failedIndexes.length !== orderedIndexes.length
      || failedIndexes.some((value, index) => value !== orderedIndexes[index])
    ) {
      context.addIssue({
        code: "custom",
        message: "Failed search query indexes must be unique and ordered",
        path: ["failed_queries"],
      });
    }
    if (failedIndexes.some((index) => index > coverage.attempted_queries)) {
      context.addIssue({
        code: "custom",
        message: "Failed search query index exceeds attempted query count",
        path: ["failed_queries"],
      });
    }
    if (
      coverage.successful_queries + coverage.failed_queries.length
      !== coverage.attempted_queries
    ) {
      context.addIssue({
        code: "custom",
        message: "Search coverage must account for every attempted query",
        path: ["successful_queries"],
      });
    }
    const expectedStatus = coverage.failed_queries.length === 0 ? "complete" : "partial";
    if (coverage.status !== expectedStatus) {
      context.addIssue({
        code: "custom",
        message: "Search coverage status does not match failed queries",
        path: ["status"],
      });
    }
  });

export const deepResearchArtifactSchema = z
  .strictObject({
    artifact_type: z.literal("deep_research_report"),
    schema_version: z.literal("1.0"),
    status: z.enum(["draft", "committed"]),
    harness_mode: z.enum(["deepagents", "langchain"]),
    search_coverage: deepResearchSearchCoverageSchema,
    report: deepResearchReportSchema,
    sources: z.array(z.strictObject({
      index: sourceIndexSchema,
      evidence: webEvidenceSchema,
    })).min(1).max(8),
    model_audits: z.array(modelExecutionAuditSchema).default([]),
  })
  .superRefine((artifact, context) => {
    const catalogIndexes = artifact.sources.map((source) => source.index);
    const expectedIndexes = artifact.sources.map((_, index) => index + 1);
    if (catalogIndexes.some((index, offset) => index !== expectedIndexes[offset])) {
      context.addIssue({
        code: "custom",
        message: "Research source catalog must be contiguous and ordered",
        path: ["sources"],
      });
    }
    const availableIndexes = new Set(catalogIndexes);
    for (const [sectionIndex, section] of artifact.report.sections.entries()) {
      for (const [findingIndex, finding] of section.findings.entries()) {
        for (const sourceIndex of finding.source_indexes) {
          if (!availableIndexes.has(sourceIndex)) {
            context.addIssue({
              code: "custom",
              message: "Research finding references an unknown source index",
              path: [
                "report",
                "sections",
                sectionIndex,
                "findings",
                findingIndex,
                "source_indexes",
              ],
            });
          }
        }
      }
    }
  });

const artifactVersionSummarySchema = z.strictObject({
  artifact_version_id: z.string().uuid(),
  artifact_id: z.string().uuid(),
  version_number: z.number().int().positive(),
  schema_version: z.string().trim().min(1).max(32),
  status: z.enum(["draft", "streaming", "committed", "failed"]),
  task_id: z.string().uuid(),
  run_id: z.string().uuid(),
  created_at: timestampSchema,
});

const artifactDecisionSchema = z.strictObject({
  decision_id: z.string().uuid(),
  decision_version: z.number().int().positive(),
  decision: z.record(z.string(), z.unknown()),
  evidence_verdict: evidenceVerdictSchema,
  risk_verdict: riskVerdictSchema,
  created_at: timestampSchema,
});

export const artifactDetailSchema = z.strictObject({
  artifact_id: z.string().uuid(),
  artifact_type: z.string().trim().min(1).max(64),
  task_id: z.string().uuid(),
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  latest_version_number: z.number().int().nonnegative(),
  versions: z.array(artifactVersionSummarySchema),
  selected_version: artifactVersionSummarySchema.extend({
    content: z.union([analysisArtifactSchema, deepResearchArtifactSchema]),
    decision: artifactDecisionSchema.nullable(),
    market_snapshots: z.array(marketSnapshotSchema),
    web_evidence: z.array(webEvidenceSchema),
  }).nullable(),
});

export const productErrorSchema = z.strictObject({
  code: z.string().trim().min(1),
  message: z.string().trim().min(1),
  retryable: z.boolean().default(false),
  correlation_id: z.string().uuid(),
  provider: z.string().regex(/^[A-Za-z0-9._-]+$/).max(64).nullable().optional().default(null),
  error_type: z.string().regex(/^[A-Za-z0-9._-]+$/).max(128).nullable().optional().default(null),
  attempt: z.number().int().min(1).max(100).nullable().optional().default(null),
  endpoint: z.string().regex(/^[A-Za-z0-9._-]+$/).max(128).nullable().optional().default(null),
  fallback_from: z.string().regex(/^[A-Za-z0-9._-]+$/).max(64).nullable().optional().default(null),
  primary_attempt: z.number().int().min(1).max(100).nullable().optional().default(null),
});

export const observabilityCompletionStatusSchema = z.enum([
  "not_enabled",
  "pending",
  "degraded",
  "complete",
]);

export const taskCompletionScopeSchema = z.strictObject({
  analysis: z.enum(["pending", "complete", "blocked", "failed", "cancelled"]),
  notification: z.enum([
    "not_requested",
    "not_started",
    "pending",
    "retrying",
    "complete",
    "failed",
    "unknown",
  ]),
  observability: observabilityCompletionStatusSchema.optional().default("not_enabled"),
});

export const agentStreamBindingSchema = z.strictObject({
  protocol: z.literal("langgraph-v2"),
  assistant_id: z.string().trim().min(1).max(255),
  thread_id: z.string().trim().min(1).max(255),
  run_id: z.string().trim().min(1).max(255),
});

export const taskStageSchema = z.strictObject({
  sequence: z.number().int().min(1),
  stage: z.enum([
    "market_snapshot",
    "web_evidence",
    "analysis",
    "evidence_verdict",
    "risk_verdict",
    "artifact",
    "notification",
    "run",
  ]),
  status: z.enum([
    "committed",
    "planned",
    "succeeded",
    "blocked",
    "failed",
    "cancelled",
  ]),
  recorded_at: absoluteTimestampSchema,
  source: z.enum(["official_stream", "product_projection"]),
});

export const taskStageHistorySchema = z
  .strictObject({
    run_id: z.string().uuid(),
    stages: z.array(taskStageSchema).default([]),
    product_event_cursor: z.number().int().min(1).nullable().default(null),
    official_stream_cursor: z.string().trim().min(1).max(255).nullable().default(null),
    official_stream_cursor_at: absoluteTimestampSchema.nullable().default(null),
  })
  .superRefine((history, context) => {
    const sequences = history.stages.map((stage) => stage.sequence);
    const expectedSequences = [...new Set(sequences)].sort((left, right) => left - right);
    if (
      sequences.length !== expectedSequences.length
      || sequences.some((sequence, index) => sequence !== expectedSequences[index])
    ) {
      context.addIssue({
        code: "custom",
        message: "Stage history sequences must be unique and ascending",
        path: ["stages"],
      });
    }

    const expectedProductCursor = sequences.at(-1) ?? null;
    if (history.product_event_cursor !== expectedProductCursor) {
      context.addIssue({
        code: "custom",
        message: "Product event cursor must identify the last projected stage",
        path: ["product_event_cursor"],
      });
    }

    if (
      (history.official_stream_cursor === null)
      !== (history.official_stream_cursor_at === null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Official stream cursor and timestamp must be paired",
        path: ["official_stream_cursor"],
      });
    }
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

export const deepResearchReportEditSchema = z.strictObject({
  report: deepResearchReportSchema,
});

const reviewResponseBase = {
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
    edits: z.union([artifactReviewEditsSchema, deepResearchReportEditSchema]),
  }),
]);

const respondAllInterruptMemberSchema = z.strictObject({
  interrupt_id: z.string().trim().min(1).max(255),
  response_version: z.number().int().min(1),
  response: interruptResponseSchema,
});

export const respondAllInterruptsSchema = z
  .strictObject({
    pause_id: z.string().uuid(),
    pause_version: z.number().int().min(1),
    responses: z.array(respondAllInterruptMemberSchema).min(1).max(64),
  })
  .superRefine((submission, context) => {
    const interruptIds = new Set<string>();
    for (const [index, response] of submission.responses.entries()) {
      if (interruptIds.has(response.interrupt_id)) {
        context.addIssue({
          code: "custom",
          message: "Aggregate interrupt responses must have unique interrupt IDs",
          path: ["responses", index, "interrupt_id"],
        });
      }
      interruptIds.add(response.interrupt_id);
    }
  });

export const inboxReviewSubmissionSchema = z.strictObject({
  pause_version: z.number().int().min(1),
  response: interruptResponseSchema,
});

export const artifactReviewPayloadSchema = z.strictObject({
  kind: z.literal("artifact_review"),
  schema_version: z.literal("1.0"),
  allowed_actions: z.tuple([
    z.literal("approve"),
    z.literal("reject"),
    z.literal("edit"),
  ]),
  review_iteration: z.number().int().min(1),
  artifact: analysisArtifactSchema,
}).superRefine((payload, context) => {
  if (payload.artifact.status !== "draft") {
    context.addIssue({
      code: "custom",
      message: "Analysis review payload requires a draft artifact",
      path: ["artifact", "status"],
    });
  }
});

export const deepResearchReviewPayloadSchema = z.strictObject({
  kind: z.literal("deep_research_review"),
  schema_version: z.literal("1.0"),
  allowed_actions: z.tuple([
    z.literal("approve"),
    z.literal("reject"),
    z.literal("edit"),
  ]),
  symbol: productSymbolSchema,
  horizon: z.string().trim().min(1).max(32),
  review_iteration: z.number().int().min(1),
  artifact: deepResearchArtifactSchema,
}).superRefine((payload, context) => {
  if (payload.artifact.status !== "draft") {
    context.addIssue({
      code: "custom",
      message: "Deep research review payload requires a draft artifact",
      path: ["artifact", "status"],
    });
  }
});

export const officialReviewPayloadSchema = z.discriminatedUnion("kind", [
  artifactReviewPayloadSchema,
  deepResearchReviewPayloadSchema,
]);

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
    edits: z.union([
      persistedArtifactReviewEditsSchema,
      deepResearchReportEditSchema,
    ]),
  }),
]);

type ReviewPayloadInput = z.input<typeof officialReviewPayloadSchema>;
type InterruptResponseInput = z.input<typeof interruptResponseSchema>;
type PersistedInterruptResponseInput = z.input<typeof persistedInterruptResponseSchema>;

export function validateInterruptResponseForPayload(
  payloadInput: ReviewPayloadInput,
  responseInput: InterruptResponseInput | PersistedInterruptResponseInput,
) {
  const payload = officialReviewPayloadSchema.parse(payloadInput);
  const response = interruptResponseSchema.parse(responseInput);
  if (response.action !== "edit") return response;

  if (payload.kind === "artifact_review") {
    return {
      ...response,
      edits: artifactReviewEditsSchema.parse(response.edits),
    };
  }

  const edits = deepResearchReportEditSchema.parse(response.edits);
  if (stableFingerprint(edits.report) === stableFingerprint(payload.artifact.report)) {
    throw new Error("Deep research edits must change the report");
  }
  deepResearchArtifactSchema.parse({
    ...payload.artifact,
    report: edits.report,
  });
  return { ...response, edits };
}

function persistedInterruptResponseMatchesPayload(
  payload: z.infer<typeof officialReviewPayloadSchema>,
  response: z.infer<typeof persistedInterruptResponseSchema>,
): boolean {
  if (response.action !== "edit") return true;
  if (payload.kind === "artifact_review") {
    return deepResearchReportEditSchema.safeParse(response.edits).success === false;
  }
  const result = deepResearchReportEditSchema.safeParse(response.edits);
  if (!result.success) return false;
  if (stableFingerprint(result.data.report) === stableFingerprint(payload.artifact.report)) {
    return false;
  }
  return deepResearchArtifactSchema.safeParse({
    ...payload.artifact,
    report: result.data.report,
  }).success;
}

export const inboxQueryStatusSchema = z.enum([
  "active",
  "pending",
  "responding",
  "resolved",
  "expired",
  "resume_failed",
  "all",
]);

export const inboxItemStatusSchema = z.enum([
  "pending",
  "responding",
  "resolved",
  "expired",
  "resume_failed",
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
    pause_id: z.string().uuid(),
    pause_version: z.number().int().min(1),
    status: inboxItemStatusSchema,
    member_count: z.number().int().min(1).max(64),
    payload: officialReviewPayloadSchema,
    expires_at: absoluteTimestampSchema.nullable().optional().default(null),
    responded_at: absoluteTimestampSchema.nullable().optional().default(null),
    created_at: absoluteTimestampSchema,
    updated_at: absoluteTimestampSchema,
    symbol: productSymbolSchema,
    horizon: z.string().trim().min(1).max(32),
    query_text: z.string().trim().min(1).max(4000).nullable().optional().default(null),
  })
  .superRefine((item, context) => {
    const payloadSymbol = item.payload.kind === "artifact_review"
      ? item.payload.artifact.analysis.instrument
      : item.payload.symbol;
    const payloadHorizon = item.payload.kind === "artifact_review"
      ? item.payload.artifact.analysis.horizon
      : item.payload.horizon;
    if (payloadSymbol !== item.symbol) {
      context.addIssue({
        code: "custom",
        message: "Inbox review symbol must match its task symbol",
        path: ["payload", item.payload.kind === "artifact_review" ? "artifact" : "symbol"],
      });
    }
    if (payloadHorizon !== item.horizon) {
      context.addIssue({
        code: "custom",
        message: "Inbox review horizon must match its task horizon",
        path: ["payload", item.payload.kind === "artifact_review" ? "artifact" : "horizon"],
      });
    }
    if (item.status === "pending" && item.responded_at !== null) {
      context.addIssue({
        code: "custom",
        message: "A pending Inbox aggregate cannot have a response timestamp",
        path: ["responded_at"],
      });
    }
    if (
      (item.status === "responding"
        || item.status === "resolved"
        || item.status === "resume_failed")
      && item.responded_at === null
    ) {
      context.addIssue({
        code: "custom",
        message: `A ${item.status} Inbox aggregate requires a response timestamp`,
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

export const inboxReviewReceiptSchema = z.strictObject({
  task_id: z.string().trim().min(1).max(255),
  pause_id: z.string().uuid(),
  pause_version: z.number().int().min(1),
  status: z.enum(["responding", "resolved", "expired", "resume_failed", "cancelled"]),
  responded_at: absoluteTimestampSchema,
});

export const pendingInterruptSchema = z
  .strictObject({
    interrupt_id: z.string().trim().min(1).max(255),
    response_version: z.number().int().min(1),
    status: z.enum(["pending", "responding"]),
    payload: officialReviewPayloadSchema,
    response: persistedInterruptResponseSchema.nullable().optional().default(null),
    responded_at: absoluteTimestampSchema.nullable().optional().default(null),
  })
  .superRefine((interrupt, context) => {
    if (interrupt.response === null) return;
    if (!persistedInterruptResponseMatchesPayload(interrupt.payload, interrupt.response)) {
      context.addIssue({
        code: "custom",
        message: "Persisted interrupt response does not match its review payload",
        path: ["response", "edits"],
      });
    }
  });

export const pendingInterruptPauseSchema = z
  .strictObject({
    pause_id: z.string().uuid(),
    pause_version: z.number().int().min(1),
    status: z.enum(["pending", "responding"]),
    expires_at: absoluteTimestampSchema.nullable().optional().default(null),
    members: z.array(pendingInterruptSchema).min(1).max(64),
  })
  .superRefine((pause, context) => {
    const interruptIds = new Set<string>();
    for (const [index, member] of pause.members.entries()) {
      if (interruptIds.has(member.interrupt_id)) {
        context.addIssue({
          code: "custom",
          message: "Pending pause members must have unique interrupt IDs",
          path: ["members", index, "interrupt_id"],
        });
      }
      interruptIds.add(member.interrupt_id);
      if (member.status !== pause.status) {
        context.addIssue({
          code: "custom",
          message: "Pending pause member status must match its aggregate pause",
          path: ["members", index, "status"],
        });
      }
      if (member.status === "pending" && (member.response !== null || member.responded_at !== null)) {
        context.addIssue({
          code: "custom",
          message: "A pending interrupt cannot already contain a response",
          path: ["members", index, "response"],
        });
      }
      if (
        member.status === "responding"
        && (member.response === null || member.responded_at === null)
      ) {
        context.addIssue({
          code: "custom",
          message: "A responding interrupt requires its accepted response",
          path: ["members", index, "response"],
        });
      }
    }
  });

export const productTaskSchema = z
  .strictObject({
    task_id: z.string().trim().min(1),
    task_type: taskTypeSchema.default("market_analysis"),
    correlation_id: z.string().uuid(),
    status: runStatusSchema,
    symbol: productSymbolSchema,
    horizon: z.string().trim().min(1),
    query_text: z.string().trim().min(1).max(4000).nullable().default(null),
    created_at: timestampSchema,
    completed_at: timestampSchema.nullable().default(null),
    cancel_requested_at: timestampSchema.nullable().default(null),
    artifact: analysisArtifactSchema.nullable().default(null),
    deep_research_artifact: deepResearchArtifactSchema.nullable().default(null),
    errors: z.array(productErrorSchema).default([]),
    completion_scope: taskCompletionScopeSchema.optional().default({
      analysis: "pending",
      notification: "not_requested",
      observability: "not_enabled",
    }),
    warnings: z.array(z.string().trim().min(1)).default([]),
    agent_stream: agentStreamBindingSchema.nullable().default(null),
    stage_history: taskStageHistorySchema.nullable().optional().default(null),
    market_snapshot: marketSnapshotSchema.nullable().default(null),
    web_evidence: z.array(webEvidenceSchema).default([]),
    pending_interrupts: pendingInterruptPauseSchema.nullable().optional().default(null),
    projection_scope: taskProjectionScopeSchema.optional().default({
      mode: "latest",
      selected_run_id: null,
    }),
  })
  .superRefine((task, context) => {
    const artifact = task.artifact;
    const researchArtifact = task.deep_research_artifact;
    const pendingPause = task.pending_interrupts;

    for (const [index, error] of task.errors.entries()) {
      if (error.correlation_id !== task.correlation_id) {
        context.addIssue({
          code: "custom",
          message: "Error correlation ID must match its Task",
          path: ["errors", index, "correlation_id"],
        });
      }
    }

    if (task.task_type === "market_analysis") {
      if (researchArtifact !== null) {
        context.addIssue({
          code: "custom",
          message: "Market analysis Task cannot expose a research artifact",
          path: ["deep_research_artifact"],
        });
      }
      if (task.status === "succeeded" && artifact?.status !== "committed") {
        context.addIssue({
          code: "custom",
          message: "A succeeded analysis requires a committed artifact",
          path: ["artifact"],
        });
      }
    } else {
      if (artifact !== null) {
        context.addIssue({
          code: "custom",
          message: "Deep research Task cannot expose an analysis artifact",
          path: ["artifact"],
        });
      }
      if (task.status === "succeeded" && researchArtifact?.status !== "committed") {
        context.addIssue({
          code: "custom",
          message: "A succeeded deep research Task requires a committed report",
          path: ["deep_research_artifact"],
        });
      }
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
    if (
      task.status === "waiting_human"
      && pendingPause === null
      && task.projection_scope.mode !== "selected_run"
    ) {
      context.addIssue({
        code: "custom",
        message: "A current waiting_human Task requires an active interrupt pause",
        path: ["pending_interrupts"],
      });
    }
    if (task.status !== "waiting_human" && pendingPause !== null) {
      context.addIssue({
        code: "custom",
        message: "Only a waiting_human task may expose an active interrupt pause",
        path: ["pending_interrupts"],
      });
    }
    for (const [index, member] of (pendingPause?.members ?? []).entries()) {
      const expectedKind = task.task_type === "market_analysis"
        ? "artifact_review"
        : "deep_research_review";
      if (member.payload.kind !== expectedKind) {
        context.addIssue({
          code: "custom",
          message: "Pending review kind must match its task type",
          path: ["pending_interrupts", "members", index, "payload", "kind"],
        });
        continue;
      }
      const payloadSymbol = member.payload.kind === "artifact_review"
        ? member.payload.artifact.analysis.instrument
        : member.payload.symbol;
      const payloadHorizon = member.payload.kind === "artifact_review"
        ? member.payload.artifact.analysis.horizon
        : member.payload.horizon;
      if (payloadSymbol !== task.symbol) {
        context.addIssue({
          code: "custom",
          message: "Pending review symbol must match its task symbol",
          path: ["pending_interrupts", "members", index, "payload"],
        });
      }
      if (payloadHorizon !== task.horizon) {
        context.addIssue({
          code: "custom",
          message: "Pending review horizon must match its task horizon",
          path: ["pending_interrupts", "members", index, "payload"],
        });
      }
    }
  });

export type AnalysisSubmission = z.infer<typeof analysisSubmissionSchema>;
export type DeepResearchSubmission = z.infer<typeof deepResearchSubmissionSchema>;
export type DeepResearchArtifact = z.infer<typeof deepResearchArtifactSchema>;
export type DeepResearchReport = z.infer<typeof deepResearchReportSchema>;
export type DeepResearchReportEdit = z.infer<typeof deepResearchReportEditSchema>;
export type DeepResearchReviewPayload = z.infer<typeof deepResearchReviewPayloadSchema>;
export type AgentStreamBinding = z.infer<typeof agentStreamBindingSchema>;
export type TaskStage = z.infer<typeof taskStageSchema>;
export type TaskStageHistory = z.infer<typeof taskStageHistorySchema>;
export type ArtifactReviewEdits = z.infer<typeof artifactReviewEditsSchema>;
export type ForkSubmission = z.infer<typeof forkSubmissionSchema>;
export type InboxItem = z.infer<typeof inboxItemSchema>;
export type InboxItemStatus = z.infer<typeof inboxItemStatusSchema>;
export type InboxQueryStatus = z.infer<typeof inboxQueryStatusSchema>;
export type InboxView = z.infer<typeof inboxViewSchema>;
export type InterruptResponse = z.infer<typeof interruptResponseSchema>;
export type InboxReviewSubmission = z.infer<typeof inboxReviewSubmissionSchema>;
export type InboxReviewReceipt = z.infer<typeof inboxReviewReceiptSchema>;
export type MarketSnapshot = z.infer<typeof marketSnapshotSchema>;
export type Notification = z.infer<typeof notificationSchema>;
export type NotificationList = z.infer<typeof notificationListSchema>;
export type NotificationResendSubmission = z.infer<typeof notificationResendSubmissionSchema>;
export type NotificationSettings = z.infer<typeof notificationSettingsSchema>;
export type NotificationSettingsUpdate = z.infer<typeof notificationSettingsUpdateSchema>;
export type DataLifecyclePolicy = z.infer<typeof dataLifecyclePolicySchema>;
export type DataLifecyclePolicyUpdate = z.infer<typeof dataLifecyclePolicyUpdateSchema>;
export type DataExport = z.infer<typeof dataExportSchema>;
export type DataExportManifest = z.infer<typeof dataExportManifestSchema>;
export type DataExportBundle = z.infer<typeof dataExportBundleSchema>;
export type DataDeletion = z.infer<typeof dataDeletionSchema>;
export type OfficialReviewPayload = z.infer<typeof officialReviewPayloadSchema>;
export type ArtifactReviewPayload = z.infer<typeof artifactReviewPayloadSchema>;
export type PendingInterrupt = z.infer<typeof pendingInterruptSchema>;
export type AnalysisPendingInterrupt = Omit<PendingInterrupt, "payload"> & {
  payload: ArtifactReviewPayload;
};
export type DeepResearchPendingInterrupt = Omit<PendingInterrupt, "payload"> & {
  payload: DeepResearchReviewPayload;
};

export function isAnalysisPendingInterrupt(
  interrupt: PendingInterrupt,
): interrupt is AnalysisPendingInterrupt {
  return interrupt.payload.kind === "artifact_review";
}

export function isDeepResearchPendingInterrupt(
  interrupt: PendingInterrupt,
): interrupt is DeepResearchPendingInterrupt {
  return interrupt.payload.kind === "deep_research_review";
}
export type PendingInterruptPause = z.infer<typeof pendingInterruptPauseSchema>;
export type ProductError = z.infer<typeof productErrorSchema>;
export type ObservabilityCompletionStatus = z.infer<typeof observabilityCompletionStatusSchema>;
type ParsedTaskCompletionScope = z.infer<typeof taskCompletionScopeSchema>;
export type TaskCompletionScope = Omit<ParsedTaskCompletionScope, "observability"> & {
  observability?: ObservabilityCompletionStatus;
};
export type ArtifactLibrary = z.infer<typeof artifactLibrarySchema>;
export type ArtifactLibraryItem = z.infer<typeof artifactLibraryItemSchema>;
export type ArtifactDetail = z.infer<typeof artifactDetailSchema>;
export type HomeView = z.infer<typeof homeViewSchema>;
export type Feedback = z.infer<typeof feedbackSchema>;
export type FeedbackSubmission = z.infer<typeof feedbackSubmissionSchema>;
export type RunDetail = z.infer<typeof runDetailSchema>;
export type ProductRunList = z.infer<typeof productRunListSchema>;
export type ProductRunSummary = z.infer<typeof productRunSummarySchema>;
export type ProductSymbol = z.infer<typeof productSymbolSchema>;
export type TaskProjectionScope = z.infer<typeof taskProjectionScopeSchema>;
export type TaskType = z.infer<typeof taskTypeSchema>;
type ParsedProductTask = z.infer<typeof productTaskSchema>;
export type ProductTask = Omit<
  ParsedProductTask,
  "completion_scope" | "projection_scope" | "stage_history"
> & {
  completion_scope: TaskCompletionScope;
  projection_scope?: TaskProjectionScope;
  stage_history?: TaskStageHistory | null;
};
export type RespondAllInterrupts = z.infer<typeof respondAllInterruptsSchema>;
export type RunStatus = z.infer<typeof runStatusSchema>;
export type WebEvidence = z.infer<typeof webEvidenceSchema>;
