import Link from "next/link";
import type { EvalCandidate } from "@/lib/schemas/eval";
import { severityClass, shortId, truncate } from "@/app/eval/eval-format";

export function EvalCandidatesTable({
  candidates,
  errorMessage
}: {
  candidates: EvalCandidate[];
  errorMessage?: string;
}) {
  if (errorMessage) {
    return <div className="error-state">{errorMessage}</div>;
  }
  if (candidates.length === 0) {
    return <p className="muted">暂无 badcase 候选。先在 trace 复盘中记录 badcase。</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>严重度</th>
            <th>类别</th>
            <th>Dataset</th>
            <th>交易对</th>
            <th>Trace</th>
            <th>期望行为</th>
            <th>实际行为</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((item) => (
            <tr key={item.id}>
              <td>
                <span className={`badge ${severityClass(item.severity)}`}>{item.severity}</span>
              </td>
              <td>{item.category}</td>
              <td>{item.eval_dataset_name ?? "default"}</td>
              <td>{item.trace.symbol}</td>
              <td>
                <Link href={`/runs/${encodeURIComponent(item.trace_id)}`}>{shortId(item.trace_id)}</Link>
              </td>
              <td>{truncate(item.expected_behavior)}</td>
              <td>{truncate(item.actual_behavior)}</td>
              <td>{item.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
