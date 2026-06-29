import Link from "next/link";
import { listRuns } from "@/lib/api/runs";
import { StatusBadge } from "@/app/shared/status-badge";

export const dynamic = "force-dynamic";

export default async function RunsPage() {
  const result = await listRuns();

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Runs</h1>
          <p>查看所有运行记录与 trace 入口。</p>
        </div>
        <Link className="button" href="/manual-run">
          新建运行
        </Link>
      </header>

      {!result.ok ? (
        <div className="error-state">{result.error.message}</div>
      ) : result.data.items.length === 0 ? (
        <div className="empty-state">暂无运行记录。</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Trace ID</th>
                <th>状态</th>
                <th>类型</th>
                <th>交易对</th>
                <th>最终动作</th>
                <th>Span</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.map((run) => (
                <tr key={run.trace_id}>
                  <td>{run.trace_id}</td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{run.run_type}</td>
                  <td>{run.symbol}</td>
                  <td>{run.final_action ?? "-"}</td>
                  <td>{run.span_count}</td>
                  <td>{run.created_at}</td>
                  <td>
                    <Link href={`/runs/${encodeURIComponent(run.trace_id)}`}>详情</Link>
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
