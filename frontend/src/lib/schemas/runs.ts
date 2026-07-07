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
    parent_span_id: z.string().nullable().optional(),
    span_name: z.string(),
    span_type: z.string(),
    status: z.string(),
    started_at: z.string(),
    ended_at: z.string(),
    duration_ms: z.number(),
    input_summary: z.unknown().optional(),
    output_summary: z.unknown().optional(),
    error_type: z.string().nullable().optional(),
    error_message: z.string().nullable().optional(),
    metadata: z.unknown().optional()
  })
  .passthrough();

export const llmInteractionSchema = z
  .object({
    id: z.number(),
    trace_id: z.string().optional(),
    span_id: z.string().nullable().optional(),
    created_at: z.string().optional(),
    component: z.string(),
    provider: z.string(),
    model: z.string(),
    endpoint: z.string().nullable().optional(),
    status: z.string(),
    duration_ms: z.number().nullable().optional(),
    prompt_tokens: z.number().nullable().optional(),
    completion_tokens: z.number().nullable().optional(),
    total_tokens: z.number().nullable().optional(),
    cost_usd: z.number().nullable().optional(),
    finish_reason: z.string().nullable().optional(),
    retry_count: z.number().default(0),
    input_hash: z.string(),
    output_hash: z.string(),
    input_summary: z.unknown().optional(),
    output_summary: z.unknown().optional(),
    request_json: z.string().optional(),
    response_json: z.string().optional(),
    error_type: z.string().nullable().optional(),
    metadata: z.unknown().optional(),
    error_message: z.string().nullable().optional()
  })
  .passthrough();

const auditRecordSchema = z.record(z.unknown());
const sourceTierSchema = z.union([z.string(), z.number()]).nullable().optional();

export const toolCallArtifactRefSchema = z
  .object({
    tool_call_id: z.string().optional(),
    skill_name: z.string().optional(),
    status: z.string().optional(),
    source_type: z.string().optional(),
    source_tier: sourceTierSchema,
    retrieved_at: z.string().optional(),
    freshness_status: z.string().optional(),
    result_ref: z.string().optional(),
    output_hash: z.string().optional(),
    can_satisfy_execution_fact: z.boolean().optional(),
    fact_refs: z.record(z.string()).optional(),
    result_count: z.number().optional(),
    error_type: z.string().optional(),
    error_hash: z.string().optional()
  })
  .passthrough();

export const agentAuditToolCallSchema = toolCallArtifactRefSchema
  .extend({
    worker: z.string().optional(),
    task_id: z.string().optional()
  })
  .passthrough();

export const agentAuditEvidenceSourceSchema = z
  .object({
    evidence_ref: z.string(),
    claim_ref: z.string().nullable().optional(),
    source_url: z.string().nullable().optional(),
    source_type: z.string().nullable().optional(),
    source_tier: sourceTierSchema,
    observed_at: z.string().nullable().optional(),
    retrieved_at: z.string().nullable().optional(),
    freshness_status: z.string().nullable().optional(),
    can_satisfy_execution_fact: z.boolean().nullable().optional()
  })
  .passthrough();

export const agentAuditSourceFreshnessSchema = z
  .object({
    source_type: z.string(),
    source_tier: sourceTierSchema,
    freshness_status: z.string(),
    count: z.number(),
    can_satisfy_execution_fact_count: z.number().default(0),
    missing_execution_facts: z.array(z.string()).default([])
  })
  .passthrough();

export const rootCauseGraphSchema = z
  .object({
    nodes: z
      .array(
        z
          .object({
            node_id: z.string(),
            worker: z.string().optional(),
            layer: z.number().default(0),
            factor_type: z.string().optional(),
            query: z.string().optional(),
            evidence_refs: z.array(z.string()).default([]),
            confidence: z.string().optional(),
            fact_type: z.string().optional()
          })
          .passthrough()
      )
      .default([]),
    edges: z
      .array(
        z
          .object({
            from: z.string(),
            to: z.string(),
            worker: z.string().optional()
          })
          .passthrough()
      )
      .default([])
  })
  .passthrough()
  .default({ nodes: [], edges: [] });

export const conflictEdgeSchema = z
  .object({
    worker_a: z.string().optional(),
    worker_b: z.string().optional(),
    claim_ref: z.string().optional(),
    conflict_type: z.string().optional(),
    severity: z.string().optional()
  })
  .passthrough();

export const candidateFinalComparisonSchema = z
  .object({
    status: z.string().optional(),
    decision_effect: z.string().optional(),
    production_final_input: z.boolean().optional(),
    legacy: auditRecordSchema.default({}),
    candidate: auditRecordSchema.default({}),
    diff: auditRecordSchema.default({}),
    production_control_gate: auditRecordSchema.default({}),
    final_input_selection: auditRecordSchema.default({})
  })
  .passthrough()
  .default({});

export const inputLineageSchema = z
  .object({
    production_final_input_mode: z.string().optional(),
    production_final_input_source_ref: z.string().nullable().optional(),
    production_decision_effect: z.string().nullable().optional(),
    decision_input: auditRecordSchema.default({}),
    candidate_final: auditRecordSchema.default({}),
    audit_only_payloads: z.array(z.string()).default([])
  })
  .passthrough()
  .default({ audit_only_payloads: [] });

export const releaseEvalGateSchema = z
  .object({
    structural_gate: auditRecordSchema.default({}),
    production_control_gate: auditRecordSchema.default({}),
    financial_quality_gate: auditRecordSchema.default({})
  })
  .passthrough()
  .default({});

const querySemanticsSchema = z
  .object({
    mode: z.literal("audit_note").default("audit_note"),
    drives_final_input: z.boolean().optional()
  })
  .passthrough();

export const symbolConsistencySchema = z
  .object({
    request_symbol: z.string().nullable().optional(),
    snapshot_symbol: z.string().nullable().optional(),
    plan_instrument: z.string().nullable().optional(),
    consistent: z.boolean().optional()
  })
  .passthrough()
  .default({});

export const agentAuditLeadTaskSchema = z
  .object({
    task_id: z.string().optional(),
    agent_name: z.string().optional(),
    role: z.string().optional(),
    required: z.boolean().optional(),
    timeout_seconds: z.number().optional(),
    requested_tools: z.array(z.string()).default([]),
    input_ref: z.string().optional(),
    trace_ref: z.string().optional(),
    failure_policy: z.string().optional()
  })
  .passthrough();

export const agentAuditWorkerSchema = z
  .object({
    agent_name: z.string().optional(),
    task_id: z.string().optional(),
    status: z.string().optional(),
    required: z.boolean().optional(),
    trace_ref: z.string().optional(),
    input_ref: z.string().optional(),
    output_hash: z.string().optional(),
    failure_policy_applied: z.string().optional(),
    summary: z.string().optional(),
    claim_count: z.number().default(0),
    conflict_count: z.number().default(0),
    conflicts: z.array(z.string()).default([]),
    missing_facts: z.array(z.string()).default([]),
    evidence_ids: z.array(z.string()).default([]),
    confidence_cap: z.number().nullable().optional(),
    confidence_cap_reasons: z.array(z.string()).default([]),
    hard_block: z.boolean().default(false),
    hard_block_reasons: z.array(z.string()).default([]),
    blocked_actions: z.array(z.string()).default([]),
    blocked_action_classes: z.array(z.string()).default([]),
    manual_review_reminders: z.array(z.string()).default([]),
    required_confirmations: z.array(z.string()).default([]),
    requested_tools: z.array(z.string()).default([]),
    tool_call_artifact_count: z.number().default(0),
    tool_call_artifact_refs: z.array(toolCallArtifactRefSchema).default([])
  })
  .passthrough();

export const agentAuditDecisionInputSchema = z
  .object({
    mode: z.string().optional(),
    schema_version: z.number().optional(),
    decision_effect: z.string().optional(),
    execution_mode: z.string().optional(),
    symbol: z.string().optional(),
    trace_id: z.string().optional(),
    input_ref: z.string().optional(),
    input_hash: z.string().optional(),
    validation: auditRecordSchema.default({}),
    missing_facts: z.array(z.string()).default([]),
    conflicts: z.array(z.string()).default([]),
    effective_allowed_actions: z.array(z.string()).default([]),
    blocked_actions: z.array(z.string()).default([]),
    confidence_policy: auditRecordSchema.default({}),
    contribution_refs: z.array(auditRecordSchema).default([]),
    evidence_refs: z.array(z.string()).default([])
  })
  .passthrough();

export const agentAuditViewSchema = z
  .object({
    available: z.boolean().default(false),
    reason: z.string().optional(),
    schema_version: z.number().optional(),
    mode: z.string().optional(),
    decision_effect: z.string().optional(),
    lead_plan: z
      .object({
        plan_id: z.string().optional(),
        mode: z.string().optional(),
        decision_effect: z.string().optional(),
        resource_limits: auditRecordSchema.default({}),
        tasks: z.array(agentAuditLeadTaskSchema).default([])
      })
      .passthrough()
      .default({ tasks: [] }),
    query_semantics: querySemanticsSchema.default({ mode: "audit_note" }),
    symbol_consistency: symbolConsistencySchema,
    controlled_shadow: auditRecordSchema.default({}),
    workers: z.array(agentAuditWorkerSchema).default([]),
    lead_synthesis: auditRecordSchema.default({}),
    harness_validation: auditRecordSchema.default({}),
    facts_gate: auditRecordSchema.default({}),
    evidence_packets: auditRecordSchema.default({}),
    tool_calls: z.array(agentAuditToolCallSchema).default([]),
    evidence_sources: z.array(agentAuditEvidenceSourceSchema).default([]),
    source_freshness: z.array(agentAuditSourceFreshnessSchema).default([]),
    root_cause_graph: rootCauseGraphSchema,
    conflict_edges: z.array(conflictEdgeSchema).default([]),
    strongest_counter_thesis_ref: z.string().nullable().optional(),
    decision_input: agentAuditDecisionInputSchema.default({}),
    decision_input_candidate: agentAuditDecisionInputSchema.default({}),
    candidate_final_comparison: candidateFinalComparisonSchema,
    input_lineage: inputLineageSchema,
    release_eval_gate: releaseEvalGateSchema,
    gates: z
      .object({
        gate_candidate: auditRecordSchema.optional(),
        plan_semantic_candidate: auditRecordSchema.optional(),
        final_decision_switch_readiness: auditRecordSchema.optional(),
        production_control_gate: auditRecordSchema.optional()
      })
      .passthrough()
      .default({}),
    final_input_selection: auditRecordSchema.default({}),
    legacy_prompt_lifecycle: auditRecordSchema.default({}),
    replay_refs: auditRecordSchema.default({}),
    runtime_flow: z.array(auditRecordSchema).default([]),
    source_payload_keys: z.array(z.string()).default([])
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
    agent_audit_view: agentAuditViewSchema.optional(),
    payload_keys: z.array(z.string()).default([])
  })
  .passthrough()
  .nullable();

export const runDetailSchema = z
  .object({
    trace: runSummarySchema,
    plan_run: planRunSchema,
    analysis: z.record(z.unknown()).default({}),
    spans: z.array(traceSpanSchema).default([]),
    llm_interactions: z.array(llmInteractionSchema).default([]),
    badcases: z.array(z.record(z.unknown())).default([])
  })
  .passthrough();

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
export type AgentAuditView = z.output<typeof agentAuditViewSchema>;
