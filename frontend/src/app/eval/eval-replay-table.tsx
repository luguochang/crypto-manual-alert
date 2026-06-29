import Link from "next/link";
import type { EvalCase } from "@/lib/schemas/eval";
import { observedText, replayClass, shortId } from "@/app/eval/eval-format";

export function EvalReplayTable({
  cases,
  errorMessage,
  hasRun
}: {
  cases: EvalCase[];
  errorMessage?: string;
  hasRun: boolean;
}) {
  if (!hasRun) {
    return <p className="muted">暂无 replay 明细。</p>;
  }
  if (errorMessage) {
    return <div className="error-state">{errorMessage}</div>;
  }
  if (cases.length === 0) {
    return <p className="muted">该 eval run 暂无 case。</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Case</th>
            <th>Frozen hash</th>
            <th>Trace</th>
            <th>Observed</th>
            <th>Replay</th>
            <th>Result</th>
            <th>耗时</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((item) => (
            <tr key={item.case_id}>
              <td>{item.case_id}</td>
              <td title={item.frozen_input_hash}>{shortId(item.frozen_input_hash)}</td>
              <td>
                <Link href={`/runs/${encodeURIComponent(item.source_trace_id)}`}>
                  {shortId(item.source_trace_id)}
                </Link>
              </td>
              <td>{observedText(item)}</td>
              <td>
                <span className={`badge ${replayClass(item.replay_result?.status)}`}>
                  {item.replay_result?.status ?? "not_run"}
                </span>
              </td>
              <td>
                {item.replay_result?.final_action ?? "-"} /{" "}
                {typeof item.replay_result?.allowed === "boolean" ? String(item.replay_result.allowed) : "-"}
                {item.replay_result?.output_hash ? ` / ${shortId(item.replay_result.output_hash)}` : ""}
              </td>
              <td>{typeof item.replay_result?.duration_ms === "number" ? `${item.replay_result.duration_ms}ms` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
