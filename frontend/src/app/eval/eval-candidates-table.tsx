import Link from "next/link";
import type { EvalCandidate } from "@/lib/schemas/eval";
import { safeEvalLabel, severityClass, shortId, truncate } from "@/app/eval/eval-format";
import { safeDisplayContent, safeDisplayError } from "@/app/shared/safe-error";

export function evalCandidatesErrorMessage(error: unknown) {
  return safeDisplayError(error, "问题样本暂时无法加载，请稍后重试。");
}

export function evalCandidateExpectedBehaviorText(value: string | null | undefined) {
  return truncate(safeDisplayContent(value));
}

export function evalCandidateActualBehaviorText(value: string | null | undefined) {
  return truncate(safeDisplayContent(value));
}

export function evalCandidateCategoryText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function evalCandidateDatasetText(value: string | null | undefined) {
  return safeEvalLabel(value || "default");
}

export function evalCandidateSeverityText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function evalCandidateStatusText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function EvalCandidatesTable({
  candidates,
  errorMessage,
  selectedStatus,
  selectedSeverity
}: {
  candidates: EvalCandidate[];
  errorMessage?: string;
  selectedStatus?: string;
  selectedSeverity?: string;
}) {
  if (errorMessage) {
    return <div className="error-state" role="alert">{evalCandidatesErrorMessage(errorMessage)}</div>;
  }
  if (candidates.length === 0) {
    return <p className="muted">暂无 badcase 候选。先在 trace 复盘中记录 badcase。</p>;
  }
  return (
    <>
      <div className="section-heading-row">
        <div>
          <h2>候选 Case</h2>
          <p className="muted">按状态和严重度筛选进入 eval 的 badcase 候选。</p>
        </div>
        <div className="tabs compact-tabs" aria-label="Case filters">
          {[
            { href: "/eval?tab=cases", label: "全部" },
            { href: "/eval?tab=cases&status=open", label: "Open" },
            { href: "/eval?tab=cases&severity=high", label: "High" },
            { href: "/eval?tab=cases&severity=critical", label: "Critical" }
          ].map((item) => {
            const active =
              (item.label === "全部" && !selectedStatus && !selectedSeverity) ||
              item.href.includes(`status=${selectedStatus}`) ||
              item.href.includes(`severity=${selectedSeverity}`);
            return (
              <Link key={item.href} className={`tab ${active ? "active" : ""}`} href={item.href} prefetch={false}>
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>严重度</th>
              <th>类别</th>
              <th>Dataset</th>
              <th>交易对</th>
              <th>Trace</th>
              <th>Badcase</th>
              <th>期望行为</th>
              <th>实际行为</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((item) => (
              <tr key={item.id}>
                <td>
                  <span className={`badge ${severityClass(item.severity)}`}>{evalCandidateSeverityText(item.severity)}</span>
                </td>
                <td>{evalCandidateCategoryText(item.category)}</td>
                <td>{evalCandidateDatasetText(item.eval_dataset_name)}</td>
                <td>{item.trace.symbol}</td>
                <td>
                  <Link href={`/runs/${encodeURIComponent(item.trace_id)}`} prefetch={false}>{shortId(item.trace_id)}</Link>
                </td>
                <td className="mono-cell">{item.id}</td>
                <td>{evalCandidateExpectedBehaviorText(item.expected_behavior)}</td>
                <td>{evalCandidateActualBehaviorText(item.actual_behavior)}</td>
                <td>{evalCandidateStatusText(item.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
