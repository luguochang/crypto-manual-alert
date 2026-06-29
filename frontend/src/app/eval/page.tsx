import Link from "next/link";
import { getEvalRunDetail, listEvalCandidates, listEvalRuns } from "@/lib/api/eval";
import { RunEvalForm } from "@/app/eval/run-eval-form";
import type { EvalCandidate, EvalScore } from "@/lib/schemas/eval";

export const dynamic = "force-dynamic";

function shortId(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

function passRate(passCount: number, caseCount: number) {
  if (!caseCount) {
    return "0%";
  }
  return `${Math.round((passCount / caseCount) * 100)}%`;
}

function severityClass(severity: string) {
  if (severity === "critical" || severity === "high") {
    return "badge-failed";
  }
  if (severity === "medium") {
    return "badge-pending";
  }
  return "badge-running";
}

function resultClass(passed: boolean) {
  return passed ? "badge-success" : "badge-failed";
}

function truncate(value: string | null | undefined, max = 96) {
  const text = value?.trim();
  if (!text) {
    return "-";
  }
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

export default async function EvalPage() {
  const [candidatesResult, runsResult] = await Promise.all([
    listEvalCandidates({ limit: 50 }),
    listEvalRuns({ limit: 10 })
  ]);

  const latestRunId = runsResult.ok && runsResult.data.items.length > 0 ? runsResult.data.items[0].eval_run_id : null;
  const latestDetail = latestRunId ? await getEvalRunDetail(latestRunId) : null;

  const candidates = candidatesResult.ok ? candidatesResult.data.items : [];
  const runs = runsResult.ok ? runsResult.data.items : [];
  const openCases = candidates.filter((item) => item.status === "open").length;
  const highRiskCases = candidates.filter((item) => ["critical", "high"].includes(item.severity)).length;
  const datasets = new Set(candidates.map((item) => item.eval_dataset_name || "default")).size;
  const latestRun = runs[0];
  const failedScores = latestDetail?.ok ? latestDetail.data.scores.filter((score) => !score.passed) : [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Eval 工作台</h1>
          <p>查看 badcase 候选、旁路测评结果、judge 评分和生产副作用守卫。</p>
        </div>
        <Link className="button button-secondary" href="/runs">
          查看 Trace
        </Link>
      </header>

      <section className="toolbar">
        <div>
          <strong>旁路测评</strong>
          <p className="muted">只运行 fixture judge，不调用真实 LLM，不发送 Bark，不写生产 plan_runs。</p>
        </div>
        <RunEvalForm />
      </section>

      <section className="stats-grid" aria-label="Eval 统计">
        <div className="stat-card">
          <span>候选 case</span>
          <strong>{candidates.length}</strong>
        </div>
        <div className="stat-card">
          <span>Open</span>
          <strong>{openCases}</strong>
        </div>
        <div className="stat-card">
          <span>High / Critical</span>
          <strong>{highRiskCases}</strong>
        </div>
        <div className="stat-card">
          <span>数据集</span>
          <strong>{datasets}</strong>
        </div>
      </section>

      <div className="grid-2 section-gap">
        <section className="panel">
          <h2>最近 Eval Run</h2>
          {!runsResult.ok ? (
            <div className="error-state">{runsResult.error.message}</div>
          ) : runs.length === 0 ? (
            <p className="muted">暂无 eval run。可通过 POST /api/eval/runs 或后续页面按钮触发 fixture judge 测评。</p>
          ) : (
            <div className="table-wrap">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>状态</th>
                    <th>Dataset</th>
                    <th>通过率</th>
                    <th>失败</th>
                    <th>开始时间</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.eval_run_id}>
                      <td>{shortId(run.eval_run_id)}</td>
                      <td>
                        <span className={`badge ${run.status === "passed" ? "badge-success" : "badge-failed"}`}>
                          {run.status}
                        </span>
                      </td>
                      <td>{run.dataset_name}</td>
                      <td>{passRate(run.pass_count, run.case_count)}</td>
                      <td>{run.fail_count}</td>
                      <td>{run.started_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>最新测评摘要</h2>
          {!latestRun ? (
            <p className="muted">暂无测评结果。</p>
          ) : (
            <dl className="detail-list">
              <div>
                <dt>Run ID</dt>
                <dd>{latestRun.eval_run_id}</dd>
              </div>
              <div>
                <dt>模式</dt>
                <dd>{latestRun.mode}</dd>
              </div>
              <div>
                <dt>Case</dt>
                <dd>{latestRun.case_count}</dd>
              </div>
              <div>
                <dt>Pass / Fail</dt>
                <dd>{latestRun.pass_count} / {latestRun.fail_count}</dd>
              </div>
              <div>
                <dt>副作用 delta</dt>
                <dd>{JSON.stringify(latestRun.metadata.side_effect_deltas ?? {})}</dd>
              </div>
            </dl>
          )}
        </section>
      </div>

      <section className="panel section-gap">
        <h2>候选 Case</h2>
        {!candidatesResult.ok ? (
          <div className="error-state">{candidatesResult.error.message}</div>
        ) : candidates.length === 0 ? (
          <p className="muted">暂无 badcase 候选。先从 trace 复盘中记录 badcase，再进入 eval 回归。</p>
        ) : (
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
                {candidates.map((item: EvalCandidate) => (
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
        )}
      </section>

      <section className="panel section-gap">
        <h2>最新 Judge 明细</h2>
        {!latestDetail ? (
          <p className="muted">暂无 judge 明细。</p>
        ) : !latestDetail.ok ? (
          <div className="error-state">{latestDetail.error.message}</div>
        ) : latestDetail.data.scores.length === 0 ? (
          <p className="muted">该 eval run 暂无 score。</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>结果</th>
                  <th>Case</th>
                  <th>Trace</th>
                  <th>Judge</th>
                  <th>类型</th>
                  <th>严重度</th>
                  <th>分类</th>
                  <th>原因</th>
                  <th>人工复核</th>
                </tr>
              </thead>
              <tbody>
                {latestDetail.data.scores.map((score: EvalScore) => (
                  <tr key={score.score_id}>
                    <td>
                      <span className={`badge ${resultClass(score.passed)}`}>{score.passed ? "pass" : "fail"}</span>
                    </td>
                    <td>{score.case_id} / badcase {score.source_badcase_id || "-"}</td>
                    <td>
                      {score.source_trace_id ? (
                        <Link href={`/runs/${encodeURIComponent(score.source_trace_id)}`}>
                          {shortId(score.source_trace_id)}
                        </Link>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>{score.judge_name}</td>
                    <td>{score.judge_type}</td>
                    <td>{score.severity}</td>
                    <td>{score.failure_category}</td>
                    <td>{score.reason_summary}</td>
                    <td>{score.needs_human_review ? "需要" : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {failedScores.length > 0 ? (
          <p className="muted section-gap">
            当前最新 run 有 {failedScores.length} 条失败评分；先按 high/critical case 复核，再决定是否把样本加入 golden set。
          </p>
        ) : null}
      </section>
    </>
  );
}
