import Link from "next/link";
import { listRuns } from "@/lib/api/runs";
import { StatusBadge } from "@/app/shared/status-badge";
import { Icon } from "@/app/shared/icons";

export const dynamic = "force-dynamic";

type RunsPageProps = {
  searchParams: Promise<{ view?: string }>;
};

export default async function RunsPage({ searchParams }: RunsPageProps) {
  const viewParam = (await searchParams).view;
  const view: "alerts" | "observe" = viewParam === "observe" ? "observe" : "alerts";
  const result = await listRuns();
  const items = result.ok ? result.data.items : [];

  const isAlerts = view === "alerts";
  const title = isAlerts ? "提醒业务" : "Agent 可观测";
  const desc = isAlerts
    ? "业务视角：每条提醒的决策动作、风控结论与 Bark 送达。"
    : "可观测视角：每条 trace 的 span、LLM 调用与执行规模，下钻 Agent 执行检查器。";
  const defaultTab = isAlerts ? "decision" : "agent";

  return (
    <>
      <header className="page-header">
        <div>
          <h1>{title}</h1>
          <p className="muted">{desc}</p>
        </div>
        {isAlerts ? (
          <Link className="button" href="/manual-run">
            <Icon name="plus" size={16} /> 新建提醒
          </Link>
        ) : null}
      </header>

      <nav className="tabs" aria-label="视图切换">
        <Link href="/runs?view=alerts" className={`tab ${isAlerts ? "active" : ""}`}>
          <Icon name="bell" size={15} /> 提醒业务
        </Link>
        <Link href="/runs?view=observe" className={`tab ${!isAlerts ? "active" : ""}`}>
          <Icon name="activity" size={15} /> Agent 可观测
        </Link>
      </nav>

      {!result.ok ? (
        <div className="error-state">{result.error.message}</div>
      ) : items.length === 0 ? (
        <div className="empty-state">暂无运行记录。{isAlerts ? "新建一次手动提醒以生成 trace。" : ""}</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              {isAlerts ? (
                <tr>
                  <th>交易对</th>
                  <th>状态</th>
                  <th>最终动作</th>
                  <th>风险</th>
                  <th>创建时间</th>
                  <th></th>
                </tr>
              ) : (
                <tr>
                  <th>Trace ID</th>
                  <th>交易对</th>
                  <th>状态</th>
                  <th>Spans</th>
                  <th>LLM</th>
                  <th>创建时间</th>
                  <th></th>
                </tr>
              )}
            </thead>
            <tbody>
              {items.map((run) => (
                <tr key={run.trace_id}>
                  {isAlerts ? (
                    <>
                      <td className="mono-cell">{run.symbol}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td>{run.final_action ?? "-"}</td>
                      <td>
                        <span className={`badge ${run.allowed ? "badge-success" : "badge-failed"}`}>
                          {run.allowed == null ? "-" : run.allowed ? "allowed" : "blocked"}
                        </span>
                      </td>
                      <td className="mono-cell">{run.created_at}</td>
                    </>
                  ) : (
                    <>
                      <td className="mono-cell">{run.trace_id}</td>
                      <td className="mono-cell">{run.symbol}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td className="mono-cell">{run.span_count}</td>
                      <td className="mono-cell">{run.llm_interaction_count}</td>
                      <td className="mono-cell">{run.created_at}</td>
                    </>
                  )}
                  <td>
                    <Link className="button-ghost button" href={`/runs/${encodeURIComponent(run.trace_id)}?tab=${defaultTab}`}>
                      <Icon name="chevron-right" size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
