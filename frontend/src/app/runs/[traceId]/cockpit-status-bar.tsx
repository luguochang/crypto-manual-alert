import { Icon, type IconName } from "@/app/shared/icons";
import { productDisplayItems, productFactLabel } from "@/app/shared/product-copy";
import { safeReasonBullets } from "@/lib/schemas/manual-run";
import type { AgentAuditView } from "@/lib/schemas/runs";

// 默认详情的复核状态条：只保留用户能理解的检查结论，工程字段留在诊断视图。

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
  return safeReasonBullets(reasons).slice(0, 3);
}

function qualityStatusText(status: string): string {
  if (status === "not_configured") return "未配置";
  if (status === "not_enough_samples") return "样本不足";
  if (status === "passed") return "通过";
  if (status === "failed") return "未通过";
  return status ? "状态已记录" : "未知";
}

export function CockpitStatusBar({ agentAudit, verdict }: CockpitStatusBarProps) {
  const available = agentAudit?.available === true;
  const candidatePromoted = agentAudit?.candidate_final_comparison?.production_final_input === true;
  const blockingReasons = productDisplayItems(collectBlockingReasons(agentAudit, verdict));

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

  const auditConclusion = candidatePromoted
    ? "不可直接采信：候选输入已提升，需立即复核发布门禁"
    : !available
      ? "复核证据不足：请核对详细复核记录"
      : factsPassed && symbolConsistent
        ? "可人工复核：证据链未发现硬阻断"
        : "已阻断：禁止作为操作依据";
  const auditConclusionTone: StatusCell["tone"] = candidatePromoted || !symbolConsistent ? "danger" : factsPassed && available ? "ok" : "warn";

  const cells: StatusCell[] = [
    {
      label: "生成路径",
      value: candidatePromoted ? "需复核" : "稳定",
      tone: productionTone,
      icon: "shield",
      hint: candidatePromoted ? "生成路径发生切换，需要复核详细记录" : "当前使用已验证的默认生成路径"
    },
    {
      label: "事实检查",
      value: available ? (factsPassed ? "通过" : "缺少信息") : "证据不足",
      tone: factsTone,
      icon: "check",
      hint: missingExecutionFacts.length > 0 ? `缺 ${missingExecutionFacts.length} 项执行事实` : undefined
    },
    {
      label: "证据补充",
      value: toolHealthCount === 0 ? "未记录" : `${toolHealthCount} 条`,
      tone: toolTone,
      icon: "search",
      hint: toolHealthCount === 0 ? "暂无补充证据" : toolCanSatisfy ? "含可满足执行事实的证据" : "无可满足执行事实的证据"
    },
    {
      label: "质量检查",
      value: qualityStatusText(financialStatus),
      tone: financialTone,
      icon: "flask",
      hint: financialStatus === "not_enough_samples" ? "样本不足，暂不构成发布阻断" : undefined
    },
    {
      label: "交易对一致",
      value: symbolConsistent ? "一致" : "不一致",
      tone: symbolConsistent ? "ok" : "danger",
      icon: "alert",
      hint: symbolConsistent ? undefined : "请求、行情快照与提醒计划的交易对不一致"
    }
  ];

  return (
    <section className="panel section-gap review-status-bar" aria-label="复核状态摘要">
      <div className={`review-status-conclusion tone-${auditConclusionTone}`}>
        <strong>{auditConclusion}</strong>
        <span>本页展示提醒建议与审计证据，不是交易委托；任何执行都需要人工核对价格、仓位和风险。</span>
      </div>

      <div className="review-status-grid">
        {cells.map((cell) => (
          <article key={cell.label} className={`review-status-cell tone-${cell.tone}`}>
            <span className="review-status-cell-label">
              <Icon name={cell.icon} size={14} /> {cell.label}
            </span>
            <strong className="review-status-cell-value">{cell.value}</strong>
            {cell.hint ? <span className="review-status-cell-hint">{cell.hint}</span> : null}
          </article>
        ))}
      </div>

      {blockingReasons.length > 0 ? (
        <div className="review-status-blocking">
          <h3>主要阻断原因</h3>
          <ul>
            {blockingReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {missingExecutionFacts.length > 0 ? (
        <div className="review-status-missing">
          <h3>缺失执行事实</h3>
          <div className="pill-row">
            {missingExecutionFacts.map((fact) => (
              <span key={fact} className="config-pill">{productFactLabel(fact)}</span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
