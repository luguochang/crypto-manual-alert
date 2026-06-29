import Link from "next/link";
import { listRuns } from "@/lib/api/runs";
import { StatusBadge } from "@/app/shared/status-badge";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const result = await listRuns();

  if (!result.ok) {
    return (
      <>
        <header className="page-header">
          <div>
            <h1>Dashboard</h1>
            <p>运行概览和最近任务。</p>
          </div>
          <Link className="button" href="/manual-run">
            新建运行
          </Link>
        </header>
        <div className="error-state">{result.error.message}</div>
      </>
    );
  }

  const recentRuns = result.data.items ?? [];
  const statCards = [
    { label: "最近运行", value: recentRuns.length },
    { label: "允许提醒", value: recentRuns.filter((run) => run.status === "allowed").length },
    { label: "风控阻断", value: recentRuns.filter((run) => run.status === "blocked").length },
    { label: "LLM 交互", value: recentRuns.reduce((sum, run) => sum + (run.llm_interaction_count ?? 0), 0) }
  ];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>运行概览和最近任务。</p>
        </div>
        <Link className="button" href="/manual-run">
          新建运行
        </Link>
      </header>

      <section className="stats-grid" aria-label="运行统计">
        {statCards.map((card) => (
          <div className="stat-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </section>

      <section className="panel">
        <h2>最近运行</h2>
        {recentRuns.length === 0 ? (
          <p className="muted">暂无运行记录。</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Trace ID</th>
                  <th>状态</th>
                  <th>交易对</th>
                  <th>最终动作</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => (
                  <tr key={run.trace_id}>
                    <td>{run.trace_id}</td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td>{run.symbol}</td>
                    <td>{run.final_action ?? "-"}</td>
                    <td>{run.created_at}</td>
                    <td>
                      <Link href={`/runs/${encodeURIComponent(run.trace_id)}`}>
                        查看详情
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
