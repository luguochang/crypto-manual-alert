"use client";

import { ArrowLeft, ArrowUpRight, CircleAlert, History, RefreshCw, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AnalysisProjection } from "@/features/analysis/analysis-projection";
import { DeepResearchProjection } from "@/features/research/deep-research-projection";
import {
  directRunCommandAvailability,
  RunCommandActions,
} from "@/features/runs/run-command-actions";
import { CompletionScopeStatus } from "@/features/status/completion-scope-status";
import { cancelRun, getRun, ProductApiError, submitFeedback } from "@/lib/api/product-client";
import type { RunDetail } from "@/lib/schemas/product-api";

const statusLabels: Record<RunDetail["run"]["status"], string> = {
  queued: "已排队",
  running: "分析中",
  waiting_human: "等待人工确认",
  succeeded: "分析完成",
  blocked: "门禁阻断",
  failed: "分析失败",
  cancelled: "已取消",
};

const activeRunStatuses = new Set<RunDetail["run"]["status"]>([
  "queued",
  "running",
  "waiting_human",
]);
const RUN_REVALIDATION_INTERVAL_MS = 5_000;

type LoadMode = "manual" | "background";

export function RunDetailSurface({ runId }: { runId: string }) {
  return <RunDetailContent key={runId} runId={runId} />;
}

function RunDetailContent({ runId }: { runId: string }) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const requestGeneration = useRef(0);
  const revalidates = detail === null ? false : shouldRevalidateRun(detail);

  const loadRun = useCallback(async (mode: LoadMode): Promise<RunDetail | null> => {
    const generation = ++requestGeneration.current;
    if (mode === "background") {
      setRefreshing(true);
      setRefreshError(null);
    } else {
      setLoading(true);
      setError(null);
    }
    try {
      const response = await getRun(runId);
      if (generation !== requestGeneration.current) return null;
      setDetail(response);
      setError(null);
      setRefreshError(null);
      return response;
    } catch (reason) {
      if (generation !== requestGeneration.current) return null;
      const message = reason instanceof ProductApiError
        ? reason.message
        : "无法读取这次分析运行，请稍后重试。";
      if (mode === "background") {
        setRefreshError(message);
      } else {
        setError(message);
      }
      return null;
    } finally {
      if (generation === requestGeneration.current) {
        if (mode === "background") {
          setRefreshing(false);
        } else {
          setLoading(false);
        }
      }
    }
  }, [runId]);

  function reload() {
    void loadRun("manual");
  }

  useEffect(() => {
    const generation = ++requestGeneration.current;
    void getRun(runId)
      .then((response) => {
        if (generation !== requestGeneration.current) return;
        setDetail(response);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (generation !== requestGeneration.current) return;
        setError(
          reason instanceof ProductApiError
            ? reason.message
            : "无法读取这次分析运行，请稍后重试。",
        );
      })
      .finally(() => {
        if (generation === requestGeneration.current) setLoading(false);
      });
    return () => {
      requestGeneration.current += 1;
    };
  }, [runId]);

  useEffect(() => {
    if (!revalidates) return;
    let disposed = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const clearTimer = () => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    };
    const schedule = () => {
      clearTimer();
      if (!disposed && !document.hidden) {
        timer = setTimeout(() => void poll(), RUN_REVALIDATION_INTERVAL_MS);
      }
    };
    const poll = async () => {
      if (disposed || document.hidden || inFlight) return;
      inFlight = true;
      const response = await loadRun("background");
      inFlight = false;
      if (!disposed && (response === null || shouldRevalidateRun(response))) {
        schedule();
      }
    };
    const handleVisibilityChange = () => {
      clearTimer();
      if (!document.hidden) void poll();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    schedule();
    return () => {
      disposed = true;
      clearTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [revalidates, loadRun]);

  async function cancelSelectedRun() {
    if (detail === null || cancelling || !shouldOfferRunCancellation(detail)) return;
    setCancelling(true);
    setError(null);
    try {
      await cancelRun(detail.run.run_id);
      await loadRun("background");
    } catch (reason) {
      setError(
        reason instanceof ProductApiError
          ? reason.message
          : "无法取消这次分析运行，请稍后重试。",
      );
    } finally {
      setCancelling(false);
    }
  }

  async function submitRunFeedback(rating: "positive" | "negative") {
    if (detail === null || detail.feedback !== null || feedbackSubmitting) return;
    setFeedbackSubmitting(true);
    setFeedbackError(null);
    try {
      const feedback = await submitFeedback(detail.run.run_id, {
        rating,
        comment: feedbackComment.trim() || null,
      });
      setDetail((current) => current ? { ...current, feedback } : current);
      setFeedbackComment("");
    } catch (reason) {
      setFeedbackError(
        reason instanceof ProductApiError
          ? reason.message
          : "反馈未能保存，请稍后重试。",
      );
    } finally {
      setFeedbackSubmitting(false);
    }
  }

  return (
    <div className="work-page runs-page">
      <header className="work-header">
        <div>
          <Link className="back-link" href="/runs" prefetch={false}>
            <ArrowLeft size={17} aria-hidden="true" />
            返回分析记录
          </Link>
          <p className="section-kicker">分析记录 / 运行详情</p>
          <h1>{detail
            ? `${detail.run.symbol.replace("-USDT-SWAP", "")} ${detail.run.task_type === "deep_research" ? "深度研究" : "市场分析"} · ${detail.run.horizon}`
            : "运行详情"}</h1>
          <p>查看这次分析的执行状态、证据、风险与最终报告。</p>
        </div>
        <span className="boundary-label list-meta-label">
          <History size={17} aria-hidden="true" />
          {detail ? `第 ${detail.run.attempt} 次运行` : "历史运行"}
        </span>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>正在读取运行</h2><p>正在恢复这次历史分析及其报告。</p></div>
        </section>
      ) : null}

      {error ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><h2>运行读取失败</h2><p>{error}</p></div>
          <button className="submit-button" type="button" onClick={reload}>
            <RefreshCw size={17} aria-hidden="true" />
            重新读取
          </button>
        </section>
      ) : null}

      {!loading && !error && detail ? (
        <>
          <section
            className={`status-panel ${runStatusTone(detail.run.status)}`}
            data-status={detail.run.status}
            aria-label="运行元数据"
          >
            <span className="status-icon"><History size={20} aria-hidden="true" /></span>
            <div>
              <div className="status-title-row">
                <h2>{statusLabels[detail.run.status]}</h2>
                <span>{detail.run.symbol.replace("-USDT-SWAP", "")} · {detail.run.horizon}</span>
              </div>
              <p>创建于 {formatDateTime(detail.run.created_at)}</p>
              <dl className="run-detail-facts">
                <div><dt>运行 ID</dt><dd>{formatIdentifier(detail.run.run_id)}</dd></div>
                <div><dt>任务类型</dt><dd>{detail.run.task_type === "deep_research" ? "深度研究" : "市场分析"}</dd></div>
                <div><dt>尝试次数</dt><dd>第 {detail.run.attempt} 次</dd></div>
                <div><dt>结束时间</dt><dd>{detail.run.finished_at ? formatDateTime(detail.run.finished_at) : "进行中"}</dd></div>
              </dl>
              {isResolvedHistoricalReview(detail) ? (
                <p className="run-history-disclosure">该次人工确认已由后续运行处理。</p>
              ) : null}
              <div className="run-detail-actions">
                <RunCommandActions
                  key={`${detail.run.run_id}:${detail.task.status}`}
                  taskId={detail.run.task_id}
                  sourceRunId={detail.run.run_id}
                  availability={directRunCommandAvailability(detail)}
                />
                {shouldOfferRunCancellation(detail) ? (
                  <button
                    className="cancel-task-button"
                    type="button"
                    onClick={() => void cancelSelectedRun()}
                    disabled={cancelling}
                  >
                    <CircleAlert size={16} aria-hidden="true" />
                    {cancelling ? "正在取消" : "取消本次运行"}
                  </button>
                ) : null}
                <Link className="run-work-link" href={runWorkHref(detail)} prefetch={false}>
                  {runWorkActionLabel(detail)}
                  <ArrowUpRight size={16} aria-hidden="true" />
                </Link>
                {refreshing ? <span className="run-refresh-state" role="status">正在更新状态</span> : null}
              </div>
            </div>
          </section>
          {refreshError ? (
            <section className="inline-status-note" role="status">
              <CircleAlert size={18} aria-hidden="true" />
              <p>状态更新暂时中断，页面会继续保留上一次已保存内容。</p>
              <button type="button" className="secondary-action" onClick={() => void loadRun("background")}>
                <RefreshCw size={16} aria-hidden="true" />
                立即重试
              </button>
            </section>
          ) : null}
          {detail.run_projection.task_type === "deep_research"
            ? <DeepResearchProjection task={detail.run_projection} />
            : <AnalysisProjection task={detail.run_projection} />}
          <CompletionScopeStatus status={detail.run_projection.completion_scope.observability ?? "not_enabled"} />
          {shouldShowRunFeedback(detail) ? (
            <section className="feedback-panel" aria-labelledby="feedback-title">
              <div className="feedback-heading">
                <div>
                  <p className="section-kicker">结果反馈</p>
                  <h2 id="feedback-title">这次结果对你有帮助吗？</h2>
                </div>
                {detail.feedback ? <span className="feedback-recorded">已记录</span> : null}
              </div>
              {detail.feedback ? (
                <p className="feedback-recorded-copy">
                  你标记为{detail.feedback.rating === "positive" ? "有帮助" : "需要改进"}，反馈已关联到本次分析和对应报告版本。
                </p>
              ) : (
                <>
                  <label className="feedback-comment-label" htmlFor="run-feedback-comment">
                    补充说明（可选）
                  </label>
                  <textarea
                    id="run-feedback-comment"
                    className="feedback-comment"
                    value={feedbackComment}
                    onChange={(event) => setFeedbackComment(event.target.value)}
                    maxLength={2000}
                    placeholder="例如：证据清晰，但宏观判断还需要更多来源。"
                  />
                  <div className="feedback-actions">
                    <button type="button" className="feedback-button is-positive" onClick={() => void submitRunFeedback("positive")} disabled={feedbackSubmitting}>
                      <ThumbsUp size={16} aria-hidden="true" />
                      有帮助
                    </button>
                    <button type="button" className="feedback-button is-negative" onClick={() => void submitRunFeedback("negative")} disabled={feedbackSubmitting}>
                      <ThumbsDown size={16} aria-hidden="true" />
                      需要改进
                    </button>
                    {feedbackSubmitting ? <span className="feedback-submit-status" role="status"><Send size={15} aria-hidden="true" />正在保存</span> : null}
                  </div>
                  {feedbackError ? <p className="feedback-error" role="alert">{feedbackError}</p> : null}
                </>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function shouldRevalidateRun(detail: RunDetail): boolean {
  if (detail.is_current_run) return activeRunStatuses.has(detail.run.status);
  return detail.run.status === "waiting_human"
    && activeRunStatuses.has(detail.task.status);
}

export function shouldOfferRunCancellation(detail: RunDetail): boolean {
  return detail.is_current_run && activeRunStatuses.has(detail.run.status);
}

export function isResolvedHistoricalReview(detail: RunDetail): boolean {
  return detail.run.status === "waiting_human"
    && !detail.is_current_run
    && detail.task.pending_interrupts === null;
}

export function shouldShowRunFeedback(detail: RunDetail): boolean {
  return detail.feedback !== null || (
    (
      detail.run_projection.artifact !== null
      || detail.run_projection.deep_research_artifact !== null
    )
    && ["succeeded", "blocked"].includes(detail.run.status)
  );
}

export function runWorkHref(detail: RunDetail): string {
  if (detail.run.status === "waiting_human") {
    return `/work?task=${encodeURIComponent(detail.run.task_id)}`;
  }
  return `/work?task=${encodeURIComponent(detail.run.task_id)}&run=${encodeURIComponent(detail.run.run_id)}`;
}

export function runWorkActionLabel(detail: RunDetail): string {
  if (detail.run.status === "waiting_human") {
    if (detail.task.pending_interrupts?.status === "pending") return "前往人工确认";
    if (detail.task.pending_interrupts?.status === "responding") return "查看确认进度";
    return "查看任务最新状态";
  }
  if (detail.run.status === "failed" || detail.run.status === "blocked") {
    return "在工作台查看";
  }
  return "在工作台打开";
}

function runStatusTone(status: RunDetail["run"]["status"]): string {
  if (status === "queued") return "tone-pending";
  if (status === "running") return "tone-active";
  if (status === "waiting_human") return "tone-warning";
  if (status === "succeeded") return "tone-success";
  if (status === "blocked") return "tone-blocked";
  return "tone-danger";
}

function formatIdentifier(value: string): string {
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
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
