import type { AgentAuditView } from "@/lib/schemas/runs";
import { CandidateComparison } from "./candidate-comparison";
import { ConflictMatrix } from "./conflict-matrix";
import { SourceFreshnessPanel } from "./source-freshness-panel";
import { ToolCallGraph } from "./tool-call-graph";
import { WorkerMatrix } from "./worker-matrix";

type AgentAuditPanelProps = {
  agentAudit: AgentAuditView | undefined;
};

type RiskSummaryItem = {
  label: string;
  status: string;
  detail: string;
  severity: "ok" | "warning" | "critical";
};

function fieldText(record: Record<string, unknown> | undefined, key: string) {
  if (!record) {
    return "-";
  }
  const value = record[key];
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function listText(items: string[] | undefined, max = 4) {
  if (!items || items.length === 0) {
    return "-";
  }
  const visible = items.slice(0, max).join(", ");
  return items.length > max ? `${visible} +${items.length - max}` : visible;
}

function shortHash(value: string | undefined) {
  if (!value) {
    return "-";
  }
  return value.length > 16 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

function symbolConsistencyLabel(agentAudit: AgentAuditView) {
  const consistency = agentAudit.symbol_consistency;
  if (consistency?.consistent === true) {
    return "consistent";
  }
  if (consistency?.consistent === false) {
    return "mismatch";
  }
  return "unknown";
}

function buildRiskSummaryItems(agentAudit: AgentAuditView): RiskSummaryItem[] {
  const candidate = agentAudit.candidate_final_comparison;
  const candidateError = candidate.candidate?.error as { type?: unknown } | undefined;
  const candidateReasons = candidate.candidate?.diagnosis as { blocking_reasons?: unknown } | undefined;
  const financialStatus = fieldText(agentAudit.release_eval_gate.financial_quality_gate, "status");
  const productionMode = agentAudit.input_lineage.production_final_input_mode ?? "-";
  const productionInput = candidate.production_final_input === true;
  const toolCallsMissing = agentAudit.tool_calls.length === 0;
  const candidateGateFailed = candidateError?.type === "input_gate_failed" || candidate.candidate?.allowed === false;
  const financialMissing = financialStatus === "not_configured" || financialStatus === "-";

  return [
    {
      label: "Tool Calls Missing",
      status: toolCallsMissing ? "risk" : "ok",
      detail: toolCallsMissing ? "没有记录 Skill 调用，不能证明 worker 经过工具证据链。" : `${agentAudit.tool_calls.length} 个 Skill 调用已投影。`,
      severity: toolCallsMissing ? "warning" : "ok",
    },
    {
      label: "Candidate Gate Failed",
      status: candidateGateFailed ? "blocked" : "ok",
      detail: candidateGateFailed
        ? listText(
            Array.isArray(candidateReasons?.blocking_reasons)
              ? candidateReasons.blocking_reasons.map(String)
              : [fieldText(candidate.candidate?.error as Record<string, unknown>, "type")],
            4,
          )
        : "candidate sidecar 未报告阻断。",
      severity: candidateGateFailed ? "critical" : "ok",
    },
    {
      label: "Financial Quality Missing",
      status: financialMissing ? "missing" : financialStatus,
      detail: financialMissing ? "金融质量 gate 尚未配置或没有足够样本，只能作为发布前缺口。" : `financial quality: ${financialStatus}`,
      severity: financialMissing ? "warning" : "ok",
    },
    {
      label: "Production Final Input",
      status: productionInput ? "unsafe" : "safe",
      detail: productionInput ? "candidate 被标记为生产输入，需要立即审查。" : `生产最终输入仍是 ${productionMode}。`,
      severity: productionInput ? "critical" : "ok",
    },
  ];
}

function riskClassName(severity: RiskSummaryItem["severity"]) {
  if (severity === "critical") {
    return "risk-summary-item risk-critical";
  }
  if (severity === "warning") {
    return "risk-summary-item risk-warning";
  }
  return "risk-summary-item risk-ok";
}

export function AgentAuditPanel({ agentAudit }: AgentAuditPanelProps) {
  return (
    <section className="panel section-gap agent-audit-section" aria-labelledby="agent-audit-title">
      <div className="section-heading-row">
        <div>
          <h2 id="agent-audit-title">Agent Swarm Audit</h2>
          <p className="muted">Traceable LeadAgent, WorkerAgent, Skill, evidence, gate, and input lineage view.</p>
        </div>
        <span className={agentAudit?.available ? "badge badge-success" : "badge badge-pending"}>
          {agentAudit?.available ? "observable" : "missing"}
        </span>
      </div>

      {agentAudit?.available ? (
        <>
          <dl className="audit-summary-strip">
            <div>
              <dt>Mode</dt>
              <dd>{agentAudit.mode ?? "-"}</dd>
            </div>
            <div>
              <dt>Decision Effect</dt>
              <dd>{agentAudit.decision_effect ?? "-"}</dd>
            </div>
            <div>
              <dt>LeadPlan</dt>
              <dd>{agentAudit.lead_plan.plan_id ?? "-"}</dd>
            </div>
            <div>
              <dt>Workers</dt>
              <dd>
                {agentAudit.workers.length} total /{" "}
                {agentAudit.workers.filter((worker) => worker.hard_block).length} hard block
              </dd>
            </div>
            <div>
              <dt>Tool Calls</dt>
              <dd>{agentAudit.tool_calls.length}</dd>
            </div>
            <div>
              <dt>Final Input</dt>
              <dd>{agentAudit.input_lineage.production_final_input_mode ?? "-"}</dd>
            </div>
            <div>
              <dt>Candidate Status</dt>
              <dd>{agentAudit.candidate_final_comparison.status ?? "-"}</dd>
            </div>
            <div>
              <dt>Blocked Reason</dt>
              <dd>{fieldText(agentAudit.controlled_shadow, "reason")}</dd>
            </div>
            <div>
              <dt>Symbol Check</dt>
              <dd>
                <span
                  className={
                    agentAudit.symbol_consistency.consistent === false
                      ? "badge badge-failed"
                      : agentAudit.symbol_consistency.consistent === true
                        ? "badge badge-success"
                        : "badge badge-pending"
                  }
                >
                  {symbolConsistencyLabel(agentAudit)}
                </span>
              </dd>
            </div>
            <div>
              <dt>Financial Gate</dt>
              <dd>{fieldText(agentAudit.release_eval_gate.financial_quality_gate, "status")}</dd>
            </div>
          </dl>

          <section className="risk-summary-strip" aria-labelledby="risk-summary-title">
            <h3 id="risk-summary-title">Risk Summary</h3>
            <div className="risk-summary-grid">
              {buildRiskSummaryItems(agentAudit).map((item) => (
                <article className={riskClassName(item.severity)} key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.status}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </section>

          <div className="audit-grid section-gap">
            <section className="audit-block" aria-labelledby="lead-plan-title">
              <h3 id="lead-plan-title">LeadPlan</h3>
              <div className="table-wrap audit-table-wrap">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>Agent</th>
                      <th>Role</th>
                      <th>Required</th>
                      <th>Skills</th>
                      <th>Trace Ref</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentAudit.lead_plan.tasks.map((task) => (
                      <tr key={task.task_id ?? task.agent_name}>
                        <td>{task.agent_name ?? "-"}</td>
                        <td>{task.role ?? "-"}</td>
                        <td>{task.required ? "yes" : "no"}</td>
                        <td>{listText(task.requested_tools, 3)}</td>
                        <td className="mono-cell">{shortHash(task.trace_ref)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="audit-block" aria-labelledby="decision-input-title">
              <h3 id="decision-input-title">DecisionInput</h3>
              <dl className="detail-list compact-list">
                <div>
                  <dt>Mode</dt>
                  <dd>{agentAudit.decision_input.mode ?? "-"}</dd>
                </div>
                <div>
                  <dt>Input Ref</dt>
                  <dd className="mono-cell">{agentAudit.decision_input.input_ref ?? "-"}</dd>
                </div>
                <div>
                  <dt>Input Hash</dt>
                  <dd className="mono-cell">{shortHash(agentAudit.decision_input.input_hash)}</dd>
                </div>
                <div>
                  <dt>Allowed Actions</dt>
                  <dd>{listText(agentAudit.decision_input.effective_allowed_actions, 6)}</dd>
                </div>
                <div>
                  <dt>Missing Facts</dt>
                  <dd>{listText(agentAudit.decision_input.missing_facts, 8)}</dd>
                </div>
                <div>
                  <dt>Query</dt>
                  <dd>{fieldText(agentAudit.query_semantics, "query_text")}</dd>
                </div>
                <div>
                  <dt>Query Mode</dt>
                  <dd>{fieldText(agentAudit.query_semantics, "mode")}</dd>
                </div>
                <div>
                  <dt>Request Symbol</dt>
                  <dd>{agentAudit.symbol_consistency.request_symbol ?? "-"}</dd>
                </div>
                <div>
                  <dt>Snapshot Symbol</dt>
                  <dd>{agentAudit.symbol_consistency.snapshot_symbol ?? "-"}</dd>
                </div>
                <div>
                  <dt>Plan Instrument</dt>
                  <dd>{agentAudit.symbol_consistency.plan_instrument ?? "-"}</dd>
                </div>
              </dl>
            </section>
          </div>

          <WorkerMatrix workers={agentAudit.workers} />
          <ToolCallGraph toolCalls={agentAudit.tool_calls} rootCauseGraph={agentAudit.root_cause_graph} />
          <SourceFreshnessPanel
            evidenceSources={agentAudit.evidence_sources}
            sourceFreshness={agentAudit.source_freshness}
          />

          <div className="audit-grid section-gap">
            <ConflictMatrix
              conflictEdges={agentAudit.conflict_edges}
              strongestCounterThesisRef={agentAudit.strongest_counter_thesis_ref}
            />
            <CandidateComparison comparison={agentAudit.candidate_final_comparison} />
          </div>

          <div className="audit-grid section-gap">
            <section className="audit-block" aria-labelledby="lineage-title">
              <h3 id="lineage-title">Input Lineage</h3>
              <dl className="detail-list compact-list">
                <div>
                  <dt>Production Mode</dt>
                  <dd>{agentAudit.input_lineage.production_final_input_mode ?? "-"}</dd>
                </div>
                <div>
                  <dt>Production Source</dt>
                  <dd className="mono-cell">{agentAudit.input_lineage.production_final_input_source_ref ?? "-"}</dd>
                </div>
                <div>
                  <dt>DecisionInput Selected</dt>
                  <dd>{fieldText(agentAudit.input_lineage.decision_input, "selected_as_final_input")}</dd>
                </div>
                <div>
                  <dt>Audit Payloads</dt>
                  <dd>{listText(agentAudit.input_lineage.audit_only_payloads, 8)}</dd>
                </div>
              </dl>
            </section>

            <section className="audit-block" aria-labelledby="gate-title">
              <h3 id="gate-title">Release And Gates</h3>
              <dl className="detail-list compact-list">
                <div>
                  <dt>Structural Ready</dt>
                  <dd>{fieldText(agentAudit.release_eval_gate.structural_gate, "ready")}</dd>
                </div>
                <div>
                  <dt>Production Allowed</dt>
                  <dd>{fieldText(agentAudit.release_eval_gate.production_control_gate, "allowed")}</dd>
                </div>
                <div>
                  <dt>Financial Quality</dt>
                  <dd>{fieldText(agentAudit.release_eval_gate.financial_quality_gate, "status")}</dd>
                </div>
                <div>
                  <dt>Facts Gate</dt>
                  <dd>
                    {fieldText(agentAudit.facts_gate, "severity")} / {fieldText(agentAudit.facts_gate, "passed")}
                  </dd>
                </div>
                <div>
                  <dt>Harness</dt>
                  <dd>{fieldText(agentAudit.harness_validation, "passed")}</dd>
                </div>
              </dl>
            </section>
          </div>

          <section className="audit-block section-gap" aria-labelledby="runtime-flow-title">
            <h3 id="runtime-flow-title">Runtime Flow</h3>
            <ol className="runtime-flow-list">
              {agentAudit.runtime_flow.map((step, index) => (
                <li key={`${fieldText(step, "name")}-${index}`}>
                  <strong>{fieldText(step, "name")}</strong>
                  <span>{fieldText(step, "owner")}</span>
                  <span>
                    {fieldText(step, "status")} / {fieldText(step, "duration_ms")} ms / {fieldText(step, "source")}
                  </span>
                  <span>
                    in {shortHash(fieldText(step, "span_input_hash"))} / out{" "}
                    {shortHash(fieldText(step, "span_output_hash"))}
                  </span>
                  <p>{fieldText(step, "effect")}</p>
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : (
        <p className="muted">
          This plan run has no projected Agent Swarm audit payload. New manual runs should expose LeadPlan,
          WorkerAgents, DecisionInput, and production_control_gate.
        </p>
      )}
    </section>
  );
}
