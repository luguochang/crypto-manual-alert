import { Icon, type IconName } from "@/app/shared/icons";
import type { AgentAuditView } from "@/lib/schemas/runs";

// 第一屏·业务驾驶舱的状态条：让管理者 5 秒看懂"能不能信 / 为什么不能执行 / 缺什么"。
// 所有字段从 agent_audit_view（默认 run 即 available=true）+ verdict 兜底提取，不再 JSON dump。

type CockpitStatusBarProps = {
  agentAudit: AgentAuditView | undefined;
  verdict: Record<string, unknown>;
};

type StatusCell = {
  label: string;
  value: string;
  tone: "ok" | "warn" | "danger" | "neutral";
  icon: IconName;
  hint?: string;
};

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

function collectBlockingReasons(agentAudit: AgentAuditView | undefined, verdict: Record<string, unknown>): string[] {
  const reasons: string[] = [];
  if (agentAudit?.available) {
    reasons.push(...asStringArray((agentAudit.facts_gate as Record<string, unknown>)?.reasons));
    const pcg = agentAudit.gates.production_control_gate as Record<string, unknown> | undefined;
    reasons.push(...asStringArray(pcg?.reasons));
    const candidate = agentAudit.candidate_final_comparison.candidate as Record<string, unknown> | undefined;
    const diagnosis = candidate?.diagnosis as Record<string, unknown> | undefined;
    reasons.push(...asStringArray(diagnosis?.blocking_reasons));
  }
  reasons.push(...asStringArray(verdict.reasons));
  // 去重保序，取前 3
  return Array.from(new Set(reasons.filter(Boolean))).slice(0, 3);
}

export function CockpitStatusBar({ agentAudit, verdict }: CockpitStatusBarProps) {
  const available = agentAudit?.available === true;
  const productionMode = agentAudit?.input_lineage?.production_final_input_mode ?? "legacy_prompt";
  const candidatePromoted = agentAudit?.candidate_final_comparison?.production_final_input === true;
  const blockingReasons = collectBlockingReasons(agentAudit, verdict);

  const factsGate = (agentAudit?.facts_gate as Record<string, unknown> | undefined) ?? {};
  const missingExecutionFacts = asStringArray(factsGate.missing_execution_facts);
  const factsPassed = factsGate.passed === true;

  const toolCalls = agentAudit?.tool_calls ?? [];
  const toolHealthCount = toolCalls.length;
  const toolCanSatisfy = toolCalls.some((call) => call.can_satisfy_execution_fact === true);

  const financialStatus = asString(
    (agentAudit?.release_eval_gate?.financial_quality_gate as Record<string, unknown> | undefined)?.status
  ) ?? "unknown";

  const symbolConsistent = agentAudit?.symbol_consistency?.consistent !== false;

  const productionTone: StatusCell["tone"] = candidatePromoted ? "danger" : "ok";
  const factsTone: StatusCell["tone"] = factsPassed ? "ok" : missingExecutionFacts.length > 0 ? "danger" : "warn";
  const toolTone: StatusCell["tone"] = toolHealthCount === 0 ? "warn" : toolCanSatisfy ? "ok" : "warn";
  const financialTone: StatusCell["tone"] =
    financialStatus === "not_configured" || financialStatus === "not_enough_samples" ? "warn" : "ok";

  const cells: StatusCell[] = [
    {
      label: "生产最终输入",
      value: candidatePromoted ? "decision_input（候选已提升）" : productionMode,
      tone: productionTone,
      icon: "shield",
      hint: candidatePromoted ? "candidate 已成为生产输入，需立即审查" : "仍是 legacy_prompt，候选未切换"
    },
    {
      label: "事实门禁",
      value: available ? (factsPassed ? "passed" : "blocked") : "无 swarm 审计",
      tone: factsTone,
      icon: "check",
      hint: missingExecutionFacts.length > 0 ? `缺 ${missingExecutionFacts.length} 项执行事实` : undefined
    },
    {
      label: "工具证据",
      value: `${toolHealthCount} 次调用`,
      tone: toolTone,
      icon: "search",
      hint: toolHealthCount === 0 ? "无 Skill 调用记录" : toolCanSatisfy ? "含可满足执行事实的证据" : "无可满足执行事实的证据"
    },
    {
      label: "金融质量",
      value: financialStatus,
      tone: financialTone,
      icon: "flask",
      hint: financialStatus === "not_enough_samples" ? "样本不足，暂不构成发布阻断" : undefined
    },
    {
      label: "Symbol 一致",
      value: symbolConsistent ? "consistent" : "mismatch",
      tone: symbolConsistent ? "ok" : "danger",
      icon: "alert",
      hint: symbolConsistent ? undefined : "请求/快照/计划 instrument 不一致"
    }
  ];

  return (
    <section className="panel section-gap cockpit-bar" aria-label="Cockpit 状态摘要">
      <div className="cockpit-grid">
        {cells.map((cell) => (
          <article key={cell.label} className={`cockpit-cell tone-${cell.tone}`}>
            <span className="cockpit-cell-label">
              <Icon name={cell.icon} size={14} /> {cell.label}
            </span>
            <strong className="cockpit-cell-value">{cell.value}</strong>
            {cell.hint ? <span className="cockpit-cell-hint">{cell.hint}</span> : null}
          </article>
        ))}
      </div>

      {blockingReasons.length > 0 ? (
        <div className="cockpit-blocking">
          <h3>阻断原因（top {blockingReasons.length}）</h3>
          <ul>
            {blockingReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {missingExecutionFacts.length > 0 ? (
        <div className="cockpit-missing">
          <h3>缺失执行事实</h3>
          <div className="pill-row">
            {missingExecutionFacts.map((fact) => (
              <span key={fact} className="config-pill">{fact}</span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
