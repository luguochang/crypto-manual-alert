import Link from "next/link";
import { getRunDetail } from "@/lib/api/runs";
import { DecisionTab } from "./decision-tab";
import { AgentTab } from "./agent-tab";
import { EvalTab } from "./eval-tab";
import { RawTab } from "./raw-tab";
import { StatusBadge } from "@/app/shared/status-badge";
import { Icon, type IconName } from "@/app/shared/icons";

export const dynamic = "force-dynamic";

type TraceDetailPageProps = {
  params: Promise<{ traceId: string }>;
  searchParams: Promise<{ tab?: string }>;
};

// Cockpit 三屏：第一屏业务驾驶舱（管理者）、第二屏业务矩阵（工程师）、第三屏 raw 辅助。
// 兼容旧 tab id（decision/agent/eval）以避免外链失效。
type TabId = "cockpit" | "matrix" | "raw";

const TABS: { id: TabId; label: string; icon: IconName }[] = [
  { id: "cockpit", label: "驾驶舱", icon: "bell" },
  { id: "matrix", label: "业务矩阵", icon: "activity" },
  { id: "raw", label: "原始数据", icon: "database" }
];

function resolveTab(raw: string | undefined): TabId {
  if (raw === "matrix" || raw === "agent" || raw === "eval") return "matrix";
  if (raw === "raw") return "raw";
  return "cockpit";
}

export default async function TraceDetailPage({ params, searchParams }: TraceDetailPageProps) {
  const { traceId } = await params;
  const tab = resolveTab((await searchParams).tab);
  const result = await getRunDetail(traceId, { includePayloads: true });

  if (!result.ok) {
    return (
      <>
        <header className="page-header">
          <div>
            <h1>Trace Detail</h1>
            <p className="mono">Trace ID: {traceId}</p>
          </div>
          <Link className="button button-secondary" href="/runs">
            <Icon name="chevron-right" size={14} /> 返回
          </Link>
        </header>
        <div className="error-state">{result.error.message}</div>
      </>
    );
  }

  const detail = result.data;
  const trace = detail.trace;
  const planRun = detail.plan_run;
  const parsedPlan = planRun?.parsed_plan ?? {};
  const verdict = planRun?.verdict ?? {};
  const agentAudit = planRun?.agent_audit_view;
  const analysis = detail.analysis ?? {};
  const spans = detail.spans ?? [];
  const llmInteractions = detail.llm_interactions ?? [];
  const badcases = detail.badcases ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Trace Detail</h1>
          <p className="mono">Trace ID: {trace.trace_id}</p>
        </div>
        <Link className="button button-secondary" href="/runs">
          <Icon name="chevron-right" size={14} /> 返回列表
        </Link>
      </header>

      <div className="status-bar">
        <span className="status-item"><StatusBadge status={trace.status} /></span>
        <span className="status-item">交易对 <strong>{trace.symbol}</strong></span>
        <span className="status-item">动作 <strong>{trace.final_action ?? "-"}</strong></span>
        <span className="status-item">风险 <strong style={{ color: trace.allowed ? "var(--success)" : "var(--danger)" }}>{trace.allowed == null ? "-" : trace.allowed ? "allowed" : "blocked"}</strong></span>
        <span className="status-item">Spans <strong>{spans.length}</strong></span>
        <span className="status-item">LLM <strong>{llmInteractions.length}</strong></span>
        <span className="status-item">创建 <strong className="mono">{trace.created_at}</strong></span>
      </div>

      <nav className="tabs" aria-label="Run detail tabs">
        {TABS.map((t) => (
          <Link key={t.id} href={`/runs/${encodeURIComponent(trace.trace_id)}?tab=${t.id}`} className={`tab ${tab === t.id ? "active" : ""}`}>
            <Icon name={t.icon} size={15} />
            {t.label}
            {t.id === "matrix" && spans.length + llmInteractions.length > 0 ? (
              <span className="tab-count">{spans.length + llmInteractions.length}</span>
            ) : null}
          </Link>
        ))}
      </nav>

      {tab === "cockpit" ? (
        <DecisionTab parsedPlan={parsedPlan} verdict={verdict} agentAudit={agentAudit} analysis={analysis} trace={trace} planRun={planRun} />
      ) : null}
      {tab === "matrix" ? (
        <>
          <AgentTab agentAudit={agentAudit} spans={spans} llmInteractions={llmInteractions} />
          <EvalTab agentAudit={agentAudit} badcases={badcases} />
        </>
      ) : null}
      {tab === "raw" ? (
        <RawTab parsedPlan={parsedPlan} verdict={verdict} planRun={planRun} analysis={analysis} />
      ) : null}
    </>
  );
}
