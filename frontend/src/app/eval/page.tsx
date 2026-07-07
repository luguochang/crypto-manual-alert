import Link from "next/link";
import { getEvalRunDetail, listEvalCandidates, listEvalOutcomes, listEvalRuns } from "@/lib/api/eval";
import { EvalCandidatesTable } from "@/app/eval/eval-candidates-table";
import { EvalJudgeScoresTable } from "@/app/eval/eval-judge-scores-table";
import { EvalReplayTable } from "@/app/eval/eval-replay-table";
import { shortId } from "@/app/eval/eval-format";
import { FinancialQualityPanel } from "@/app/eval/financial-quality-panel";
import { RunEvalForm } from "@/app/eval/run-eval-form";

export const dynamic = "force-dynamic";

function passRate(passCount: number, caseCount: number) {
  return caseCount ? `${Math.round((passCount / caseCount) * 100)}%` : "0%";
}

function metadataText(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" && value ? value : "-";
}

export default async function EvalPage() {
  const [candidatesResult, runsResult, outcomesResult] = await Promise.all([
    listEvalCandidates({ limit: 50 }),
    listEvalRuns({ limit: 10 }),
    listEvalOutcomes()
  ]);

  const runs = runsResult.ok ? runsResult.data.items : [];
  const latestRunId = runs.length > 0 ? runs[0].eval_run_id : null;
  const latestDetail = latestRunId ? await getEvalRunDetail(latestRunId) : null;
  const candidates = candidatesResult.ok ? candidatesResult.data.items : [];
  const outcomes = outcomesResult.ok ? outcomesResult.data.items : [];
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
          <p>查看 badcase、FrozenInput、Replay、Judge 分数和生产副作用守卫。</p>
        </div>
        <Link className="button button-secondary" href="/runs">
          查看 Trace
        </Link>
      </header>

      <section className="toolbar">
        <div>
          <strong>旁路测评</strong>
          <p className="muted">cheap 只跑规则；fixture 跑本地 LLMJudge 替身；judge_openai 会调用真实 OpenAI-compatible 模型。</p>
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
            <p className="muted">暂无 eval run。先记录 badcase，再运行测评。</p>
          ) : (
            <div className="table-wrap">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>状态</th>
                    <th>Mode</th>
                    <th>Dataset</th>
                    <th>通过率</th>
                    <th>失败</th>
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
                      <td>{run.mode}</td>
                      <td>{run.dataset_name}</td>
                      <td>{passRate(run.pass_count, run.case_count)}</td>
                      <td>{run.fail_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>最新摘要</h2>
          {!latestRun ? (
            <p className="muted">暂无测评结果。</p>
          ) : (
            <dl className="detail-list">
              <div>
                <dt>Run ID</dt>
                <dd>{latestRun.eval_run_id}</dd>
              </div>
              <div>
                <dt>Pass / Fail</dt>
                <dd>{latestRun.pass_count} / {latestRun.fail_count}</dd>
              </div>
              <div>
                <dt>Replay</dt>
                <dd>{JSON.stringify(latestRun.metadata.replay ?? {})}</dd>
              </div>
              <div>
                <dt>副作用 delta</dt>
                <dd>{JSON.stringify(latestRun.metadata.side_effect_deltas ?? {})}</dd>
              </div>
              <div>
                <dt>JSON 报告</dt>
                <dd>{metadataText(latestRun.metadata, "report_json_ref")}</dd>
              </div>
              <div>
                <dt>Markdown 报告</dt>
                <dd>{metadataText(latestRun.metadata, "report_markdown_ref")}</dd>
              </div>
            </dl>
          )}
        </section>
      </div>

      <FinancialQualityPanel
        gate={latestRun?.metadata.financial_quality_gate}
        outcomes={outcomes}
        outcomesError={outcomesResult.ok ? undefined : outcomesResult.error.message}
      />

      <section className="panel section-gap">
        <h2>候选 Case</h2>
        <EvalCandidatesTable
          candidates={candidates}
          errorMessage={candidatesResult.ok ? undefined : candidatesResult.error.message}
        />
      </section>

      <section className="panel section-gap">
        <h2>最新 Frozen / Replay</h2>
        <EvalReplayTable
          cases={latestDetail?.ok ? latestDetail.data.cases : []}
          errorMessage={latestDetail && !latestDetail.ok ? latestDetail.error.message : undefined}
          hasRun={Boolean(latestDetail)}
        />
      </section>

      <section className="panel section-gap">
        <h2>最新 Judge 明细</h2>
        <EvalJudgeScoresTable
          scores={latestDetail?.ok ? latestDetail.data.scores : []}
          errorMessage={latestDetail && !latestDetail.ok ? latestDetail.error.message : undefined}
          hasRun={Boolean(latestDetail)}
        />
        {failedScores.length > 0 ? (
          <p className="muted section-gap">
            当前最新 run 有 {failedScores.length} 条失败评分；优先复核 high/critical case，再决定是否加入 golden set。
          </p>
        ) : null}
      </section>
    </>
  );
}
