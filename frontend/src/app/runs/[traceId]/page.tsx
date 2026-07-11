import Link from "next/link";
import { notFound } from "next/navigation";
import { getRunDetail } from "@/lib/api/runs";
import { DecisionTab } from "./decision-tab";
import { AgentTab } from "./agent-tab";
import { EvalTab } from "./eval-tab";
import { RawTab } from "./raw-tab";
import { StatusBadge } from "@/app/shared/status-badge";
import { Icon, type IconName } from "@/app/shared/icons";
import { productDisplayText } from "@/app/shared/product-copy";
import { DiagnosticDisabledNotice, diagnosticRoutesEnabled } from "@/app/shared/diagnostic-access";
import { getSystemConfig } from "@/lib/api/system";

export const dynamic = "force-dynamic";

type TraceDetailPageProps = {
  params: Promise<{ traceId: string }>;
  searchParams: Promise<{ tab?: string; columns?: string }>;
};

// 三屏：第一屏提醒摘要，第二屏工程诊断，第三屏原始数据。
// 兼容旧 tab id（decision/agent/eval）以避免外链失效。
type TabId = "summary" | "matrix" | "raw";

const TABS: { id: TabId; label: string; icon: IconName }[] = [
  { id: "summary", label: "建议摘要", icon: "bell" },
  { id: "matrix", label: "工程诊断", icon: "activity" },
  { id: "raw", label: "原始数据", icon: "database" }
];

function resolveTab(raw: string | undefined): TabId {
  if (raw === "matrix" || raw === "agent" || raw === "eval") return "matrix";
  if (raw === "raw") return "raw";
  return "summary";
}

export default async function TraceDetailPage({ params, searchParams }: TraceDetailPageProps) {
  const { traceId } = await params;
  const query = await searchParams;
  const fromObservability = query.columns === "observability";
  const tab = fromObservability ? resolveTab(query.tab) : "summary";
  const diagnosticMode = fromObservability;
  if (diagnosticMode) {
    const config = await getSystemConfig();
    if (!diagnosticRoutesEnabled(config)) {
      return (
        <DiagnosticDisabledNotice
          backHref={`/runs/${encodeURIComponent(traceId)}`}
          backLabel="返回提醒详情"
        />
      );
    }
  }
  const result = await getRunDetail(traceId, { includePayloads: diagnosticMode && tab === "raw" });

  if (!result.ok) {
    if (result.error.code === "trace_not_found") {
      notFound();
    }

    return (
      <>
        <header className="page-header">
          <div>
            <h1>提醒详情</h1>
            <p className="muted">提醒详情暂时无法加载。</p>
          </div>
          <Link className="button button-secondary" href="/runs" prefetch={false}>
            <Icon name="chevron-right" size={14} /> 返回
          </Link>
        </header>
        <div className="error-state" role="alert">提醒详情暂时无法加载，请稍后重试。无法确认本次请求是否写入，请返回提醒记录核对。</div>
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
  const notificationHistory = detail.notification_history ?? [];
  const resultReview = detail.result_review;
  const passthroughNotification = (detail as { notification?: { status?: unknown } }).notification;
  const notificationStatus =
    planRun?.business_summary?.notification?.status ??
    (typeof passthroughNotification?.status === "string" ? passthroughNotification.status : undefined);
  const displayNotificationMessage = notificationStatusLabel(notificationStatus);

  return (
    <>
      <header className="page-header">
        <div>
          <h1>提醒详情</h1>
          <p className="muted">查看建议动作、价位、风险缺口与通知记录。</p>
        </div>
        <Link className="button button-secondary" href="/runs" prefetch={false}>
          <Icon name="chevron-right" size={14} /> 返回列表
        </Link>
      </header>

      <div className="status-bar">
        <span className="status-item"><StatusBadge status={trace.status} /></span>
        <span className="status-item">交易对 <strong>{trace.symbol}</strong></span>
        <span className="status-item">动作 <strong>{productDisplayText(trace.final_action) || "-"}</strong></span>
        <span className="status-item">人工复核 <strong style={{ color: trace.allowed ? "var(--success)" : "var(--danger)" }}>{trace.allowed == null ? "未知" : trace.allowed ? "可进入复核" : "已阻断"}</strong></span>
        <span className="status-item">通知 <strong>{displayNotificationMessage}</strong></span>
        <span className="status-item">创建 <strong>{formatRunTime(trace.created_at)}</strong></span>
      </div>

      <nav className="tabs" aria-label="提醒详情视图">
        {(diagnosticMode ? TABS : TABS.filter((item) => item.id === "summary")).map((t) => (
          <Link
            key={t.id}
            href={`/runs/${encodeURIComponent(trace.trace_id)}?tab=${t.id}${fromObservability ? "&columns=observability" : ""}`}
            prefetch={false}
            className={`tab ${tab === t.id ? "active" : ""}`}
            aria-current={tab === t.id ? "page" : undefined}
          >
            <Icon name={t.icon} size={15} />
            {t.label}
            {t.id === "matrix" && spans.length + llmInteractions.length > 0 ? (
              <span className="tab-count">{spans.length + llmInteractions.length}</span>
            ) : null}
          </Link>
        ))}
      </nav>

      {diagnosticMode ? (
        <section className="mode-notice" aria-label="工程诊断说明">
          <strong>工程诊断</strong>
          <span>这是工程诊断视图，不是普通提醒详情；用于核对主链、旁路审计、模型调用和脱敏原始数据，业务复核请回到建议摘要。</span>
        </section>
      ) : null}

      {tab === "summary" ? (
        <DecisionTab
          parsedPlan={parsedPlan}
          verdict={verdict}
          agentAudit={agentAudit}
          analysis={analysis}
          trace={trace}
          planRun={planRun}
          notificationHistory={notificationHistory}
          resultReview={resultReview}
          notificationStatus={displayNotificationMessage}
        />
      ) : null}
      {tab === "matrix" ? (
        <>
          <AgentTab agentAudit={agentAudit} spans={spans} llmInteractions={llmInteractions} />
          <EvalTab agentAudit={agentAudit} badcases={badcases} />
        </>
      ) : null}
      {tab === "raw" ? (
        <RawTab
          parsedPlan={parsedPlan}
          verdict={verdict}
          planRun={planRun}
          analysis={analysis}
          spans={spans}
          llmInteractions={llmInteractions}
        />
      ) : null}
    </>
  );
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}

function notificationStatusLabel(status: string | undefined): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  if (status === "disabled") return "通知未启用";
  return "未记录";
}
