import Link from "next/link";
import type { EvalScore } from "@/lib/schemas/eval";
import { evidenceText, metadataNumber, resultClass, safeEvalLabel, safeEvalText, shortId } from "@/app/eval/eval-format";
import { safeDisplayError } from "@/app/shared/safe-error";

export function evalJudgeScoresErrorMessage(error: unknown) {
  return safeDisplayError(error, "评分明细暂时无法加载，请稍后重试。");
}

export function evalJudgeReasonText(value: string | null | undefined) {
  return safeEvalText(value);
}

export function evalJudgeEvidenceText(score: Pick<EvalScore, "evidence_refs">) {
  return evidenceText(score);
}

export function evalJudgeNameText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function evalJudgeTypeText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function evalJudgeSeverityText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function evalJudgeFailureCategoryText(value: string | null | undefined) {
  return safeEvalLabel(value);
}

export function EvalJudgeScoresTable({
  scores,
  errorMessage,
  hasRun
}: {
  scores: EvalScore[];
  errorMessage?: string;
  hasRun: boolean;
}) {
  if (!hasRun) {
    return <p className="muted">暂无 judge 明细。</p>;
  }
  if (errorMessage) {
    return <div className="error-state" role="alert">{evalJudgeScoresErrorMessage(errorMessage)}</div>;
  }
  if (scores.length === 0) {
    return <p className="muted">该 eval run 暂无 score。</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>结果</th>
            <th>Case</th>
            <th>Trace</th>
            <th>Judge</th>
            <th>类型</th>
            <th>Score</th>
            <th>严重度</th>
            <th>分类</th>
            <th>原因</th>
            <th>Evidence refs</th>
            <th>耗时 / Token</th>
            <th>人工复核</th>
          </tr>
        </thead>
        <tbody>
          {scores.map((score) => (
            <tr key={score.score_id}>
              <td>
                <span className={`badge ${resultClass(score.passed)}`}>{score.passed ? "pass" : "fail"}</span>
              </td>
              <td>{score.case_id} / badcase {score.source_badcase_id || "-"}</td>
              <td>
                {score.source_trace_id ? (
                  <Link href={`/runs/${encodeURIComponent(score.source_trace_id)}`} prefetch={false}>
                    {shortId(score.source_trace_id)}
                  </Link>
                ) : (
                  "-"
                )}
              </td>
              <td>{evalJudgeNameText(score.judge_name)}</td>
              <td>{evalJudgeTypeText(score.judge_type)}</td>
              <td>{typeof score.score === "number" ? score.score.toFixed(2) : "-"}</td>
              <td>{evalJudgeSeverityText(score.severity)}</td>
              <td>{evalJudgeFailureCategoryText(score.failure_category)}</td>
              <td>{evalJudgeReasonText(score.reason_summary)}</td>
              <td>{evalJudgeEvidenceText(score)}</td>
              <td>{metadataNumber(score.metadata, "duration_ms")}ms / {metadataNumber(score.metadata, "total_tokens")}</td>
              <td>{score.needs_human_review ? "需要" : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
