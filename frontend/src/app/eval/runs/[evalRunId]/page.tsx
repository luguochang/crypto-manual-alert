import Link from "next/link";
import {
  getEvalFrozenInput,
  getEvalPromotionArtifacts,
  getEvalRunDetail
} from "@/lib/api/eval";
import { EvalJudgeScoresTable } from "@/app/eval/eval-judge-scores-table";
import { EvalReplayTable } from "@/app/eval/eval-replay-table";
import { EvalRunEvidenceSummary } from "@/app/eval/eval-run-evidence-summary";
import { shortId } from "@/app/eval/eval-format";
import { Icon } from "@/app/shared/icons";
import { safeDisplayError } from "@/app/shared/safe-error";
import { DiagnosticDisabledNotice, diagnosticRoutesEnabled } from "@/app/shared/diagnostic-access";
import { getSystemConfig } from "@/lib/api/system";
import type { EvalCase, EvalFrozenInputSummary } from "@/lib/schemas/eval";

export const dynamic = "force-dynamic";

type EvalRunDetailPageProps = {
  params: Promise<{ evalRunId: string }>;
};

function passRate(passCount: number, caseCount: number) {
  return caseCount ? `${Math.round((passCount / caseCount) * 100)}%` : "0%";
}

function statusLabel(value: string | null | undefined) {
  if (!value) return "未记录";
  const labels: Record<string, string> = {
    passed: "通过",
    completed: "已完成",
    failed: "未通过",
    error: "执行异常",
    running: "运行中",
    present: "已记录",
    clean: "无异常",
    missing: "未生成"
  };
  return labels[value] ?? "已记录";
}

function modeLabel(value: string | null | undefined) {
  if (!value) return "未记录";
  const labels: Record<string, string> = {
    cheap: "规则快速复盘",
    judge_only_fixture: "本地替身评审",
    judge_openai: "真实模型评审"
  };
  return labels[value] ?? "自定义复盘";
}

function artifactTypeLabel(value: string) {
  const labels: Record<string, string> = {
    no_production_side_effect_proof: "生产副作用守卫",
    shadow_candidate_comparison: "候选建议对照",
    manual_approval: "人工审批记录",
    rollback_plan: "回滚方案",
    impact_scope: "影响范围",
    manual_release_decision: "人工发布决策",
    config_change_review_request: "配置变更复核请求",
    config_change_review_approval: "配置变更复核批准"
  };
  return labels[value] ?? "其他发布证据";
}

function decisionEffectLabel(value: string | null | undefined) {
  if (!value) return "未记录";
  const labels: Record<string, string> = {
    none: "不影响生产",
    advisory: "仅供人工参考",
    release_blocking: "阻断发布"
  };
  return labels[value] ?? "已记录";
}

function artifactStatus(artifact: Record<string, unknown> | undefined) {
  if (!artifact) return "missing";
  const status = artifact.status;
  if (typeof status === "string") return status;
  const passed = artifact.passed;
  if (typeof passed === "boolean") return passed ? "passed" : "failed";
  return "present";
}

function artifactClass(status: string) {
  if (status === "passed" || status === "present" || status === "clean") return "badge-success";
  if (status === "failed" || status === "missing") return "badge-failed";
  return "badge-pending";
}

type FrozenInputLoadResult = {
  frozen: EvalFrozenInputSummary | null;
  error: string | null;
  hashMismatch: boolean;
};

function summaryValue(summary: Record<string, unknown>, key: string) {
  const value = summary[key];
  if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (value && typeof value === "object") return "已记录";
  return "-";
}

async function loadFrozenInputs(cases: EvalCase[]) {
  const pairs = await Promise.all(
    cases.map(async (item) => {
      const result = await getEvalFrozenInput(item.frozen_input_hash);
      const frozen = result.ok ? result.data.frozen_input : null;
      return [
        item.case_id,
        {
          frozen,
          error: result.ok ? null : result.error.message,
          hashMismatch: frozen ? frozen.frozen_input_hash !== item.frozen_input_hash : false
        }
      ] as const;
    })
  );
  return new Map<string, FrozenInputLoadResult>(pairs);
}

function frozenInputErrorText(value: string | null | undefined) {
  if (!value) {
    return "未读取";
  }
  return safeDisplayError(value, "摘要暂时无法读取");
}

export default async function EvalRunDetailPage({ params }: EvalRunDetailPageProps) {
  const { evalRunId } = await params;
  const config = await getSystemConfig();
  if (!diagnosticRoutesEnabled(config)) {
    return <DiagnosticDisabledNotice backHref="/eval?tab=quality" backLabel="返回质量复盘" />;
  }
  const detailResult = await getEvalRunDetail(evalRunId);

  if (!detailResult.ok) {
    return (
      <>
        <header className="page-header">
          <div>
            <h1>工程复盘诊断</h1>
            <p>复盘批次读取失败。该页面仅用于工程排查，不代表生产提醒已通过。</p>
          </div>
          <Link className="button button-secondary" href="/eval?tab=runs" prefetch={false}>
            <Icon name="chevron-right" size={14} /> 返回诊断列表
          </Link>
        </header>
        <div className="error-state" role="alert">{safeDisplayError(detailResult.error, "复盘批次暂时无法加载，请稍后重试。")}</div>
      </>
    );
  }

  const detail = detailResult.data;
  const artifactsResult = await getEvalPromotionArtifacts(evalRunId);
  const frozenInputsByCase = await loadFrozenInputs(detail.cases);
  const artifacts = artifactsResult.ok ? artifactsResult.data.artifacts : {};
  const failedScores = detail.scores.filter((score) => !score.passed);
  const humanReviewScores = detail.scores.filter((score) => score.needs_human_review);
  const run = detail.run;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>工程复盘诊断</h1>
          <p>显式查看复盘批次详情、回放输入摘要和评审结果；这些诊断信息不代表生产提醒已经通过。</p>
        </div>
        <Link className="button button-secondary" href="/eval?tab=runs" prefetch={false}>
          <Icon name="chevron-right" size={14} /> 返回诊断列表
        </Link>
      </header>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>复盘批次详情</h2>
            <p className="muted">批次编号仅用于工程排查；生产可交付性仍以真实 prod-actionable 和交易所原生结果样本为准。</p>
          </div>
          <span className={`badge ${artifactClass(run.status)}`}>{statusLabel(run.status)}</span>
        </div>
      </section>

      <section className="stats-grid section-gap" aria-label="复盘批次摘要">
        <div className="stat-card">
          <span>状态</span>
          <strong>{statusLabel(run.status)}</strong>
          <span className="stat-trend">{modeLabel(run.mode)}</span>
        </div>
        <div className="stat-card">
          <span>通过率</span>
          <strong>{passRate(run.pass_count, run.case_count)}</strong>
          <span className="stat-trend">{run.pass_count} / {run.case_count}</span>
        </div>
        <div className="stat-card">
          <span>失败评分</span>
          <strong>{failedScores.length}</strong>
          <span className="stat-trend">未通过 {run.fail_count}</span>
        </div>
        <div className="stat-card">
          <span>人工复核</span>
          <strong>{humanReviewScores.length}</strong>
          <span className="stat-trend">样本集已记录</span>
        </div>
      </section>

      <div className="grid-2 section-gap">
        <section className="panel">
          <h2>批次摘要</h2>
          <EvalRunEvidenceSummary latestRun={run} compact />
        </section>

        <section className="panel">
          <h2>发布证据</h2>
          {!artifactsResult.ok ? (
            <div className="error-state" role="alert">{safeDisplayError(artifactsResult.error, "发布证据暂时无法加载，请稍后重试。")}</div>
          ) : Object.keys(artifacts).length === 0 ? (
            <p className="muted">暂无发布证据。缺少发布证据时不能把复盘结果提升为生产发布结论。</p>
          ) : (
            <div className="table-wrap">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>证据类型</th>
                    <th>状态</th>
                    <th>生产影响</th>
                    <th>证据摘要</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(artifacts).map(([type, artifact]) => {
                    const status = artifactStatus(artifact);
                    const effect = typeof artifact.decision_effect === "string" ? artifact.decision_effect : "-";
                    return (
                      <tr key={type}>
                        <td>{artifactTypeLabel(type)}</td>
                        <td><span className={`badge ${artifactClass(status)}`}>{statusLabel(status)}</span></td>
                        <td>{decisionEffectLabel(effect)}</td>
                        <td>已记录</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section className="panel section-gap">
        <h2>回放输入摘要</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>样本</th>
                <th>输入摘要</th>
                <th>来源提醒</th>
                <th>交易对</th>
                <th>字段概览</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {detail.cases.map((item, index) => {
                const frozenResult = frozenInputsByCase.get(item.case_id);
                const frozen = frozenResult?.frozen ?? null;
                const mismatch = frozenResult?.hashMismatch ?? false;
                return (
                  <tr key={item.case_id}>
                    <td>{`样本 ${index + 1}`}</td>
                    <td className="mono-cell">
                      已冻结
                      {mismatch ? <span className="table-subtext tone-warning">摘要不一致</span> : null}
                    </td>
                    <td>
                      <Link href={`/runs/${encodeURIComponent(item.source_trace_id)}`} prefetch={false}>
                        {shortId(item.source_trace_id)}
                      </Link>
                    </td>
                    <td>{frozen ? summaryValue(frozen.public_summary, "symbol") : "-"}</td>
                    <td>{frozen ? summaryValue(frozen.public_summary, "top_level_keys") : frozenInputErrorText(frozenResult?.error)}</td>
                    <td>{frozen ? summaryValue(frozen.metadata, "source") : frozenInputErrorText(frozenResult?.error)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel section-gap">
        <h2>Replay 明细</h2>
        <EvalReplayTable cases={detail.cases} hasRun />
      </section>

      <section className="panel section-gap">
        <h2>Judge 评分</h2>
        <EvalJudgeScoresTable scores={detail.scores} hasRun />
      </section>
    </>
  );
}
