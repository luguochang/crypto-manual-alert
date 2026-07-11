import Link from "next/link";
import type { EvalCase } from "@/lib/schemas/eval";
import { observedText, replayClass, safeEvalText, shortId } from "@/app/eval/eval-format";
import { productDisplayText } from "@/app/shared/product-copy";
import { safeDisplayError } from "@/app/shared/safe-error";

export function evalReplayErrorMessage(error: unknown) {
  return safeDisplayError(error, "回放明细暂时无法加载，请稍后重试。");
}

export function evalReplayResultText(replayResult: EvalCase["replay_result"]) {
  if (!replayResult) {
    return "- / -";
  }
  const action = replayResult.final_action ? productDisplayText(safeEvalText(replayResult.final_action)) : "-";
  const allowed = typeof replayResult.allowed === "boolean" ? (replayResult.allowed ? "可人工复核" : "已阻断") : "-";
  const output = replayResult.output_hash ? ` / ${shortId(replayResult.output_hash)}` : "";
  return `${action} / ${allowed}${output}`;
}

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
    return <div className="error-state" role="alert">{evalReplayErrorMessage(errorMessage)}</div>;
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
                <Link href={`/runs/${encodeURIComponent(item.source_trace_id)}`} prefetch={false}>
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
                {evalReplayResultText(item.replay_result)}
              </td>
              <td>{typeof item.replay_result?.duration_ms === "number" ? `${item.replay_result.duration_ms}ms` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
