"use client";

import { ArrowLeft, BookOpen, CircleAlert, ExternalLink, Radar, RefreshCw, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AnalysisResult } from "@/features/analysis/analysis-result";
import { ResearchEvidence } from "@/features/analysis/research-evidence";
import { toAnalysisViewModel } from "@/features/analysis/analysis-view-model";
import { DeepResearchProjection } from "@/features/research/deep-research-projection";
import monitorEntryStyles from "@/features/monitors/monitor-entry.module.css";
import {
  directRunCommandAvailability,
  RunCommandActions,
} from "@/features/runs/run-command-actions";
import { getArtifact, getRun, ProductApiError } from "@/lib/api/product-client";
import type { ArtifactDetail, ProductTask, RunDetail } from "@/lib/schemas/product-api";

const statusLabels: Record<NonNullable<ArtifactDetail["selected_version"]>["status"], string> = {
  draft: "草稿",
  streaming: "生成中",
  committed: "已提交",
  failed: "生成失败",
};

export function ArtifactDetailSurface({
  artifactId,
  initialVersionNumber,
}: {
  artifactId: string;
  initialVersionNumber?: number;
}) {
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceRun, setSourceRun] = useState<{ runId: string; detail: RunDetail } | null>(null);
  const [sourceRunLoading, setSourceRunLoading] = useState<string | null>(null);
  const [sourceRunError, setSourceRunError] = useState<{ runId: string; message: string } | null>(null);
  const [sourceRunReload, setSourceRunReload] = useState(0);

  async function reload(versionNumber?: number) {
    setLoading(true);
    setError(null);
    try {
      setDetail(await getArtifact(artifactId, versionNumber));
    } catch (reason) {
      setError(
        reason instanceof ProductApiError
          ? reason.message
          : "无法读取持久化报告，请稍后重试。",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void getArtifact(artifactId, initialVersionNumber)
      .then((response) => {
        if (active) setDetail(response);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof ProductApiError
            ? reason.message
            : "无法读取持久化报告，请稍后重试。",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [artifactId, initialVersionNumber]);

  const commandCoordinates = artifactCommandCoordinates(detail);
  useEffect(() => {
    const runId = commandCoordinates?.runId;
    if (!runId) return;
    let active = true;
    const timer = window.setTimeout(() => {
      if (!active) return;
      setSourceRun(null);
      setSourceRunLoading(runId);
      setSourceRunError(null);
      void getRun(runId)
        .then((response) => {
          if (active) setSourceRun({ runId, detail: response });
        })
        .catch((reason: unknown) => {
          if (!active) return;
          setSourceRunError({
            runId,
            message: reason instanceof ProductApiError
              ? reason.message
              : "无法读取对应运行的可用操作，请稍后重试。",
          });
        })
        .finally(() => {
          if (active) setSourceRunLoading(null);
        });
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [commandCoordinates?.runId, sourceRunReload]);

  const viewModel = useMemo(() => {
    if (!detail?.selected_version) return null;
    const selected = detail.selected_version;
    if (selected.content.artifact_type !== "analysis_report") return null;
    const task = {
      task_id: detail.task_id,
      task_type: "market_analysis",
      correlation_id: detail.task_id,
      status: "blocked",
      symbol: detail.symbol,
      horizon: detail.horizon,
      query_text: "历史持久化报告",
      created_at: selected.created_at,
      completed_at: selected.created_at,
      cancel_requested_at: null,
      completion_scope: {
        analysis: "blocked",
        notification: "not_requested",
      },
      warnings: [],
      artifact: selected.content,
      deep_research_artifact: null,
      errors: [],
      agent_stream: null,
      market_snapshot: selected.market_snapshots[0] ?? null,
      web_evidence: selected.web_evidence,
      pending_interrupts: null,
    } satisfies ProductTask;
    return toAnalysisViewModel(task);
  }, [detail]);

  const researchTask = useMemo(() => {
    const selected = detail?.selected_version;
    if (!detail || !selected || selected.content.artifact_type !== "deep_research_report") {
      return null;
    }
    return {
      task_id: detail.task_id,
      task_type: "deep_research",
      correlation_id: detail.task_id,
      status: "succeeded",
      symbol: detail.symbol,
      horizon: detail.horizon,
      query_text: "历史持久化研究报告",
      created_at: selected.created_at,
      completed_at: selected.created_at,
      cancel_requested_at: null,
      completion_scope: {
        analysis: "complete",
        notification: "not_requested",
      },
      warnings: [],
      artifact: null,
      deep_research_artifact: selected.content,
      errors: [],
      agent_stream: null,
      market_snapshot: null,
      web_evidence: selected.web_evidence,
      pending_interrupts: null,
    } satisfies ProductTask;
  }, [detail]);

  const monitorCreateHref = useMemo(() => {
    const selected = detail?.selected_version;
    if (!detail || !selected || selected.status !== "committed") return null;
    const query = new URLSearchParams({
      artifact_id: detail.artifact_id,
      artifact_version_id: selected.artifact_version_id,
      version_number: String(selected.version_number),
    });
    return `/monitors/new?${query.toString()}`;
  }, [detail]);

  return (
    <div className="work-page runs-page">
      <header className="work-header">
        <div>
          <Link className="back-link" href="/library" prefetch={false}>
            <ArrowLeft size={17} aria-hidden="true" />
            返回报告资料库
          </Link>
          <p className="section-kicker">报告资料库 / 版本详情</p>
          <h1>{detail
            ? `${detail.symbol.replace("-USDT-SWAP", "")} ${detail.artifact_type === "deep_research_report" ? "深度研究报告" : "分析报告"}`
            : "报告详情"}</h1>
          <p>查看持久化报告、版本历史、可验证来源与对应运行。</p>
        </div>
        <div className={monitorEntryStyles.headerActions}>
          {monitorCreateHref ? (
            <Link className={monitorEntryStyles.createLink} href={monitorCreateHref} prefetch={false}>
              <Radar size={17} aria-hidden="true" />
              持续关注
            </Link>
          ) : null}
          <span className="boundary-label list-meta-label">
            <BookOpen size={17} aria-hidden="true" />
            {detail ? `${detail.versions.length} 个版本` : "历史报告"}
          </span>
        </div>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>正在读取报告</h2><p>正在恢复选定版本及其持久化证据。</p></div>
        </section>
      ) : null}

      {error ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><h2>报告读取失败</h2><p>{error}</p></div>
          <button className="submit-button" type="button" onClick={() => void reload(initialVersionNumber)}>
            <RefreshCw size={17} aria-hidden="true" />
            重新读取
          </button>
        </section>
      ) : null}

      {!loading && !error && detail ? (
        <>
          <section
            className={`status-panel ${artifactStatusTone(detail.selected_version?.status)}`}
            data-status={detail.selected_version?.status ?? "empty"}
            aria-label="报告元数据"
          >
            <span className="status-icon"><BookOpen size={20} aria-hidden="true" /></span>
            <div>
              <div className="status-title-row">
                <h2>{detail.horizon} · {detail.selected_version ? statusLabels[detail.selected_version.status] : "暂无版本"}</h2>
                <span>最新版本 v{detail.latest_version_number || "-"}</span>
              </div>
              <p>
                当前查看 v{detail.selected_version?.version_number ?? "-"} · 生成于 {detail.selected_version ? formatDateTime(detail.selected_version.created_at) : "未提供"}
              </p>
              {commandCoordinates ? (
                <div className="run-detail-actions">
                  {sourceRun?.runId === commandCoordinates.runId ? (
                    <RunCommandActions
                      key={`${commandCoordinates.runId}:${sourceRun.detail.task.status}`}
                      taskId={commandCoordinates.taskId}
                      sourceRunId={commandCoordinates.runId}
                      availability={directRunCommandAvailability(sourceRun.detail)}
                    />
                  ) : null}
                  <Link
                    className="run-work-link"
                    href={`/runs/${encodeURIComponent(commandCoordinates.runId)}`}
                    prefetch={false}
                  >
                    打开对应运行
                    <ExternalLink size={15} aria-hidden="true" />
                  </Link>
                  {sourceRunLoading === commandCoordinates.runId ? (
                    <span className="run-refresh-state" role="status">正在确认可用操作</span>
                  ) : null}
                  {sourceRunError?.runId === commandCoordinates.runId ? (
                    <button
                      className="secondary-action"
                      type="button"
                      onClick={() => setSourceRunReload((value) => value + 1)}
                    >
                      <RefreshCw size={16} aria-hidden="true" />
                      重新读取操作
                    </button>
                  ) : null}
                </div>
              ) : null}
              {sourceRunError && sourceRunError.runId === commandCoordinates?.runId ? (
                <p className="run-history-disclosure" role="alert">{sourceRunError.message}</p>
              ) : null}
            </div>
          </section>

          <div className="artifact-detail-layout">
            <aside className="artifact-version-selector" aria-labelledby="artifact-versions-title">
              <div className="result-section-heading">
                <div>
                  <p className="section-kicker">Version history</p>
                  <h2 id="artifact-versions-title">版本历史</h2>
                </div>
                <span>{detail.versions.length} 个版本</span>
              </div>
              <nav className="artifact-version-list" aria-label="报告版本">
                {detail.versions.map((version) => {
                  const isActive = version.version_number === detail.selected_version?.version_number;
                  return (
                    <Link
                      key={version.artifact_version_id}
                      className={isActive ? "artifact-version is-active" : "artifact-version"}
                      href={`/artifacts/${detail.artifact_id}?version_number=${version.version_number}`}
                      prefetch={false}
                      aria-current={isActive ? "page" : undefined}
                    >
                      <span>v{version.version_number}</span>
                      <strong>{statusLabels[version.status]}</strong>
                      <small>{formatDateTime(version.created_at)}</small>
                    </Link>
                  );
                })}
              </nav>
            </aside>

            <div className="artifact-detail-main">
              {detail.selected_version && researchTask ? (
                <DeepResearchProjection task={researchTask} />
              ) : detail.selected_version && viewModel ? (
                <>
                  {viewModel.result ? <AnalysisResult result={viewModel.result} /> : <DraftArtifactNotice detail={detail} />}
                  <ResearchEvidence research={viewModel.research} />
                  <DecisionLineage detail={detail} />
                </>
              ) : (
                <section className="empty-work-state" aria-label="没有报告版本">
                  <ShieldAlert size={20} aria-hidden="true" />
                  <div><h2>暂无可展示版本</h2><p>该报告尚未提交可回看的版本。</p></div>
                </section>
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function artifactCommandCoordinates(
  detail: ArtifactDetail | null,
): { taskId: string; runId: string } | null {
  if (!detail?.selected_version) return null;
  return {
    taskId: detail.task_id,
    runId: detail.selected_version.run_id,
  };
}

function DraftArtifactNotice({ detail }: { detail: ArtifactDetail }) {
  const selected = detail.selected_version;
  if (!selected || selected.content.artifact_type !== "analysis_report") return null;
  const reasons = [
    ...selected.content.risk_verdict.blocked_reasons,
    ...selected.content.evidence_verdict.missing_required,
  ];
  return (
    <section className="incomplete-panel" role="status">
      <ShieldAlert size={20} aria-hidden="true" />
      <div>
        <strong>该版本不是可执行建议</strong>
        <p>{reasons.length ? `门禁原因：${[...new Set(reasons)].join("；")}` : "该版本尚未形成提交后的交易建议。"}</p>
      </div>
    </section>
  );
}

function DecisionLineage({ detail }: { detail: ArtifactDetail }) {
  const decision = detail.selected_version?.decision;
  if (!decision) return null;
  return (
    <section className="artifact-decision-lineage" aria-labelledby="decision-lineage-title">
      <div className="result-section-heading">
        <div><p className="section-kicker">Decision record</p><h2 id="decision-lineage-title">决策持久化记录</h2></div>
        <span>决策版本 v{decision.decision_version}</span>
      </div>
      <div className="detail-grid">
        <div className="detail-item"><span>报告版本</span><strong>v{detail.selected_version?.version_number}</strong></div>
        <div className="detail-item"><span>证据判定</span><strong>{decision.evidence_verdict.sufficient ? "充分" : "不足"}</strong></div>
        <div className="detail-item"><span>风险判定</span><strong>{decision.risk_verdict.allowed ? "允许" : "阻断"}</strong></div>
        <div className="detail-item"><span>版本状态</span><strong>{statusLabels[detail.selected_version?.status ?? "failed"]}</strong></div>
      </div>
      <p className="muted-copy">该决策与当前报告版本、对应运行和来源记录保持一致，可从版本历史继续复核。</p>
      <a className="back-link" href={`/runs/${detail.selected_version?.run_id}`}>
        打开对应运行 <ExternalLink size={15} aria-hidden="true" />
      </a>
    </section>
  );
}

function artifactStatusTone(
  status: NonNullable<ArtifactDetail["selected_version"]>["status"] | undefined,
): string {
  if (status === "streaming") return "tone-active";
  if (status === "committed") return "tone-success";
  if (status === "failed") return "tone-danger";
  if (status === "draft") return "tone-warning";
  return "tone-neutral";
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
