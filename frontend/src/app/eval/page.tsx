import Link from "next/link";
import { getEvalRunDetail, listEvalCandidates, listEvalOutcomes, listEvalRuns } from "@/lib/api/eval";
import { EvalCandidatesTable } from "@/app/eval/eval-candidates-table";
import { EvalJudgeScoresTable } from "@/app/eval/eval-judge-scores-table";
import { EvalReplayTable } from "@/app/eval/eval-replay-table";
import { shortId } from "@/app/eval/eval-format";
import { EvalRunEvidenceSummary } from "@/app/eval/eval-run-evidence-summary";
import { FinancialQualityPanel } from "@/app/eval/financial-quality-panel";
import { RunEvalForm } from "@/app/eval/run-eval-form";
import { Icon, type IconName } from "@/app/shared/icons";
import { safeDisplayError } from "@/app/shared/safe-error";
import { DiagnosticDisabledNotice, diagnosticRoutesEnabled } from "@/app/shared/diagnostic-access";
import { getSystemConfig } from "@/lib/api/system";

export const dynamic = "force-dynamic";

type EvalPageProps = {
  searchParams: Promise<{ tab?: string; status?: string; severity?: string }>;
};

type EvalTab = "runs" | "cases" | "outcomes" | "quality";
type EvalTabItem = { id: EvalTab; label: string; icon: IconName };

const EVAL_TABS: EvalTabItem[] = [
  { id: "runs", label: "复盘批次", icon: "activity" },
  { id: "cases", label: "问题样本", icon: "database" },
  { id: "outcomes", label: "结果样本", icon: "shield" },
  { id: "quality", label: "质量指标", icon: "flask" }
];

function passRate(passCount: number, caseCount: number) {
  return caseCount ? `${Math.round((passCount / caseCount) * 100)}%` : "0%";
}

function resolveTab(raw: string | undefined): EvalTab {
  if (raw === "runs" || raw === "cases" || raw === "outcomes" || raw === "quality") return raw;
  return "quality";
}

export default async function EvalPage({ searchParams }: EvalPageProps) {
  const params = await searchParams;
  const tab = resolveTab(params.tab);
  const diagnosticMode = tab !== "quality";
  const visibleTabs = diagnosticMode ? EVAL_TABS : EVAL_TABS.filter((item) => item.id === "quality");
  if (diagnosticMode) {
    const config = await getSystemConfig();
    if (!diagnosticRoutesEnabled(config)) {
      return <DiagnosticDisabledNotice backHref="/eval?tab=quality" backLabel="返回质量复盘" />;
    }
  }
  const [candidatesResult, runsResult, outcomesResult] = await Promise.all([
    listEvalCandidates({ limit: 50, status: params.status, severity: params.severity }),
    listEvalRuns({ limit: 10 }),
    listEvalOutcomes()
  ]);

  const runs = runsResult.ok ? runsResult.data.items : [];
  const latestRunId = runs.length > 0 ? runs[0].eval_run_id : null;
  const latestDetail = tab === "runs" && latestRunId ? await getEvalRunDetail(latestRunId) : null;
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
          <h1>{diagnosticMode ? "工程复盘诊断" : "质量复盘"}</h1>
          <p>
            {diagnosticMode
              ? "显式查看复盘批次、问题样本和回放评分细节；这些诊断信息不代表生产提醒已经通过。"
              : "查看提醒后的结果样本和金融质量状态；本地展示样本不会计入真实金融质量。"}
          </p>
        </div>
        <Link className="button button-secondary" href="/runs" prefetch={false}>
          查看提醒记录
        </Link>
      </header>

      {diagnosticMode ? <section className="toolbar">
        <div>
          <strong>发起复盘</strong>
          <p className="muted">默认使用本地规则检查；启用真实模型评审前需要确认成本和外部依赖。</p>
        </div>
        <RunEvalForm />
      </section> : null}

      <nav className="tabs" aria-label="质量复盘视图">
        {visibleTabs.map((item) => (
          <Link
            key={item.id}
            href={`/eval?tab=${item.id}`}
            prefetch={false}
            className={`tab ${tab === item.id ? "active" : ""}`}
            aria-current={tab === item.id ? "page" : undefined}
          >
            <Icon name={item.icon} size={15} />
            {item.label}
          </Link>
        ))}
      </nav>

      {tab === "runs" ? <section className="stats-grid" aria-label="Eval 统计">
        <div className="stat-card">
          <span>候选样本</span>
          <strong>{candidates.length}</strong>
        </div>
        <div className="stat-card">
          <span>待处理</span>
          <strong>{openCases}</strong>
        </div>
        <div className="stat-card">
          <span>高风险</span>
          <strong>{highRiskCases}</strong>
        </div>
        <div className="stat-card">
          <span>数据集</span>
          <strong>{datasets}</strong>
        </div>
      </section> : null}

      {tab === "runs" ? <div className="grid-2 section-gap">
        <section className="panel">
          <h2>最近复盘批次</h2>
          {!runsResult.ok ? (
            <div className="error-state" role="alert">{safeDisplayError(runsResult.error, "复盘批次暂时无法加载，请稍后重试。")}</div>
          ) : runs.length === 0 ? (
            <p className="muted">暂无复盘批次。先记录问题样本，再运行复盘。</p>
          ) : (
            <div className="table-wrap">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>批次</th>
                    <th>状态</th>
                    <th>模式</th>
                    <th>数据集</th>
                    <th>通过率</th>
                    <th>失败</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.eval_run_id}>
                      <td>
                        <Link href={`/eval/runs/${encodeURIComponent(run.eval_run_id)}`} prefetch={false}>
                          {shortId(run.eval_run_id)}
                        </Link>
                      </td>
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
            <EvalRunEvidenceSummary latestRun={latestRun} compact />
          )}
        </section>
      </div> : null}

      {tab === "cases" ? <section className="panel section-gap">
        <EvalCandidatesTable
          candidates={candidates}
          errorMessage={candidatesResult.ok ? undefined : candidatesResult.error.message}
          selectedStatus={params.status}
          selectedSeverity={params.severity}
        />
      </section> : null}

      {tab === "runs" ? <section className="panel section-gap">
        <h2>最新回放明细</h2>
        <EvalReplayTable
          cases={latestDetail?.ok ? latestDetail.data.cases : []}
          errorMessage={latestDetail && !latestDetail.ok ? latestDetail.error.message : undefined}
          hasRun={Boolean(latestDetail)}
        />
      </section> : null}

      {tab === "runs" ? <section className="panel section-gap">
        <h2>最新评分明细</h2>
        <EvalJudgeScoresTable
          scores={latestDetail?.ok ? latestDetail.data.scores : []}
          errorMessage={latestDetail && !latestDetail.ok ? latestDetail.error.message : undefined}
          hasRun={Boolean(latestDetail)}
        />
        {failedScores.length > 0 ? (
          <p className="muted section-gap">
            当前最新复盘有 {failedScores.length} 条失败评分；优先复核高风险样本，再决定是否纳入固定回归集。
          </p>
        ) : null}
      </section> : null}

      {tab === "outcomes" || tab === "quality" ? (
        <FinancialQualityPanel
          gate={latestRun?.metadata.financial_quality_gate}
          outcomes={outcomes}
          outcomesError={outcomesResult.ok ? undefined : outcomesResult.error.message}
        />
      ) : null}
    </>
  );
}
