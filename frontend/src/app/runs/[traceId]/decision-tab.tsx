import { DecisionSummaryCard } from "./decision-summary-card";
import { CockpitStatusBar } from "./cockpit-status-bar";
import { NotificationHistory } from "./notification-history";
import { ResultReviewCard } from "./result-review";
import { asNumber, asString } from "@/app/shared/coerce";
import type { AgentAuditView, NotificationAttempt, PlanRun, ResultReview, RunSummary } from "@/lib/schemas/runs";

type DecisionTabProps = {
  parsedPlan: Record<string, unknown>;
  verdict: Record<string, unknown>;
  agentAudit: AgentAuditView | undefined;
  analysis: Record<string, unknown>;
  trace: RunSummary;
  planRun: PlanRun | null;
  notificationHistory?: NotificationAttempt[];
  resultReview: ResultReview;
  notificationStatus?: string;
};

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : undefined;
}

function auditQueryText(agentAudit: AgentAuditView | undefined): string | undefined {
  const semantics = asRecord(agentAudit?.query_semantics);
  const value = semantics?.query_text;
  return typeof value === "string" && value.trim() ? value : undefined;
}

export function DecisionTab({
  parsedPlan,
  verdict,
  agentAudit,
  analysis,
  trace,
  planRun,
  notificationHistory = [],
  resultReview,
  notificationStatus
}: DecisionTabProps) {
  return (
    <>
      <DecisionSummaryCard
        mainAction={asString(parsedPlan.main_action)}
        probability={asNumber(parsedPlan.probability)}
        referencePrice={asNumber(parsedPlan.reference_price)}
        entryTrigger={asNumber(parsedPlan.entry_trigger)}
        stopPrice={asNumber(parsedPlan.stop_price)}
        target1={asNumber(parsedPlan.target_1)}
        target2={asNumber(parsedPlan.target_2)}
        allowed={trace.allowed}
        symbol={trace.symbol}
        horizon={asString(parsedPlan.horizon)}
        executionMode={agentAudit?.mode}
        productionFinalInputMode={agentAudit?.input_lineage?.production_final_input_mode}
        analysis={analysis}
        verdictReasons={verdict.reasons}
        factsGate={asRecord(planRun?.facts_gate) ?? asRecord(agentAudit?.facts_gate)}
        productionControlGate={asRecord(planRun?.production_control_gate) ?? asRecord(agentAudit?.gates?.production_control_gate)}
        runContext={asRecord(planRun?.run_context)}
        finalInputSelection={asRecord(planRun?.final_input_selection) ?? asRecord(agentAudit?.final_input_selection)}
        notificationStatus={notificationStatus ?? "未启用或未记录"}
        businessSummary={planRun?.business_summary}
        focusText={auditQueryText(agentAudit)}
        evidenceSources={agentAudit?.evidence_sources}
        sourceFreshness={agentAudit?.source_freshness}
      />

      <ResultReviewCard review={resultReview} />

      <NotificationHistory
        items={notificationHistory}
        latestStatus={planRun?.business_summary?.notification?.status}
      />

      <CockpitStatusBar agentAudit={agentAudit} verdict={verdict} />
    </>
  );
}
