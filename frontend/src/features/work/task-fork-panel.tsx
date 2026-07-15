"use client";

import {
  CircleAlert,
  GitFork,
  History,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import {
  classifyForkSubmissionFailure,
  forkContextKey,
  forkSourceOptions,
  resolveForkRequestIdentity,
  type ForkContext,
  type ForkFailurePhase,
  type ForkRequestIdentity,
} from "@/features/work/fork-control";
import {
  forkTask,
  listRuns,
  ProductApiError,
} from "@/lib/api/product-client";
import type {
  ProductRunSummary,
  ProductTask,
  RunStatus,
} from "@/lib/schemas/product-api";

type SourceLoadPhase = "loading" | "ready" | "empty" | "error" | "permission_error";
type ForkPanelPhase = "idle" | "submitting" | "accepted" | ForkFailurePhase;

type TaskForkPanelProps = {
  task: ProductTask;
  selectedRunId: string | null;
  disabled: boolean;
  onAccepted: (context: ForkContext, task: ProductTask) => void;
  onRefreshContext: (context: ForkContext) => void;
};

const statusLabels: Record<RunStatus, string> = {
  queued: "已排队",
  running: "分析中",
  waiting_human: "等待人工确认",
  succeeded: "分析完成",
  blocked: "门禁阻断",
  failed: "分析失败",
  cancelled: "已取消",
};

export function TaskForkPanel({
  task,
  selectedRunId,
  disabled,
  onAccepted,
  onRefreshContext,
}: TaskForkPanelProps) {
  const context: ForkContext = { taskId: task.task_id, selectedRunId };
  const contextKey = forkContextKey(context);
  const mountedRef = useRef(false);
  const contextKeyRef = useRef(contextKey);
  const operationVersionRef = useRef(0);
  const submitLockRef = useRef(false);
  const [sourceLoadPhase, setSourceLoadPhase] = useState<SourceLoadPhase>("loading");
  const [sourceLoadMessage, setSourceLoadMessage] = useState("");
  const [sources, setSources] = useState<ProductRunSummary[]>([]);
  const [sourceRunId, setSourceRunId] = useState("");
  const [phase, setPhase] = useState<ForkPanelPhase>("idle");
  const [failureMessage, setFailureMessage] = useState("");
  const [retryRequest, setRetryRequest] = useState<ForkRequestIdentity | null>(null);
  const [refreshContextAfterFailure, setRefreshContextAfterFailure] = useState(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      operationVersionRef.current += 1;
      submitLockRef.current = false;
    };
  }, []);

  useEffect(() => {
    contextKeyRef.current = contextKey;
    operationVersionRef.current += 1;
    submitLockRef.current = false;
  }, [contextKey]);

  const loadSources = useCallback(async () => {
    const requestedContextKey = contextKey;
    const operationVersion = operationVersionRef.current + 1;
    operationVersionRef.current = operationVersion;
    submitLockRef.current = false;
    setSourceLoadPhase("loading");
    setSourceLoadMessage("");
    setSources([]);
    setSourceRunId("");
    setPhase("idle");
    setFailureMessage("");
    setRetryRequest(null);
    setRefreshContextAfterFailure(false);

    try {
      const response = await listRuns(100);
      if (!isCurrentOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        requestedContextKey,
        operationVersion,
      )) return;

      const nextSources = forkSourceOptions(
        response.items,
        task.task_id,
        selectedRunId,
      );
      if (nextSources.length === 0) {
        setSourceLoadPhase("empty");
        setSourceLoadMessage(selectedRunId
          ? "当前运行不在这个工作区的可用记录中。"
          : "当前任务还没有可用于创建分支的运行记录。");
        return;
      }
      setSources(nextSources);
      setSourceRunId(nextSources[0]?.run_id ?? "");
      setSourceLoadPhase("ready");
    } catch (error) {
      if (!isCurrentOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        requestedContextKey,
        operationVersion,
      )) return;
      const permissionError = error instanceof ProductApiError
        && (error.status === 401 || error.status === 403);
      setSourceLoadPhase(permissionError ? "permission_error" : "error");
      setSourceLoadMessage(permissionError
        ? "当前会话无权读取这个工作区的运行记录。"
        : "运行记录暂时无法读取，请稍后重试。");
    }
  }, [contextKey, selectedRunId, task.task_id]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSources(), 0);
    return () => window.clearTimeout(timer);
  }, [loadSources]);

  async function submitFork(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      submitLockRef.current
      || disabled
      || sourceLoadPhase !== "ready"
      || !sourceRunId
    ) return;

    const requestedContext = context;
    const requestedContextKey = contextKey;
    const operationVersion = operationVersionRef.current + 1;
    operationVersionRef.current = operationVersion;
    const submission = { source_run_id: sourceRunId };
    const request = resolveForkRequestIdentity(submission, retryRequest);
    submitLockRef.current = true;
    setPhase("submitting");
    setFailureMessage("");
    setRetryRequest(request);
    setRefreshContextAfterFailure(false);

    try {
      const forkedTask = await forkTask(
        task.task_id,
        submission,
        undefined,
        request.idempotencyKey,
      );
      if (!isCurrentOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        requestedContextKey,
        operationVersion,
      )) return;
      setPhase("accepted");
      setRetryRequest(null);
      onAccepted(requestedContext, forkedTask);
    } catch (error) {
      if (!isCurrentOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        requestedContextKey,
        operationVersion,
      )) return;
      const failure = classifyForkSubmissionFailure(error);
      setPhase(failure.phase);
      setFailureMessage(failure.message);
      setRetryRequest(failure.preserveRequestIdentity ? request : null);
      setRefreshContextAfterFailure(failure.refreshContext);
    } finally {
      submitLockRef.current = false;
    }
  }

  function selectSource(nextSourceRunId: string) {
    setSourceRunId(nextSourceRunId);
    setPhase("idle");
    setFailureMessage("");
    setRetryRequest(null);
    setRefreshContextAfterFailure(false);
  }

  function refreshAfterFailure() {
    if (refreshContextAfterFailure) onRefreshContext(context);
    void loadSources();
  }

  const selectedSource = sources.find((run) => run.run_id === sourceRunId) ?? null;
  const submitting = phase === "submitting";
  const permissionError = sourceLoadPhase === "permission_error"
    || phase === "permission_error";

  return (
    <section className="fork-panel" aria-labelledby="fork-panel-title" data-state={phase}>
      <div className="fork-panel-heading">
        <span className="fork-panel-icon" aria-hidden="true"><GitFork size={19} /></span>
        <div>
          <h2 id="fork-panel-title">创建分析分支</h2>
          <p>{selectedRunId ? "当前历史运行" : "任务运行记录"}</p>
        </div>
        <span className="fork-panel-scope">
          <History size={14} aria-hidden="true" />
          Product history
        </span>
      </div>

      {sourceLoadPhase === "loading" ? (
        <div className="fork-panel-state" role="status">
          <LoaderCircle className="spinning-icon" size={18} aria-hidden="true" />
          <span>正在读取可用运行</span>
        </div>
      ) : null}

      {sourceLoadPhase === "empty"
      || sourceLoadPhase === "error"
      || sourceLoadPhase === "permission_error" ? (
        <div
          className="fork-panel-state"
          data-tone={permissionError ? "permission" : "warning"}
          role={permissionError ? "alert" : "status"}
        >
          {permissionError
            ? <ShieldAlert size={18} aria-hidden="true" />
            : <CircleAlert size={18} aria-hidden="true" />}
          <span>{permissionError && phase === "permission_error"
            ? failureMessage
            : sourceLoadMessage}</span>
          {sourceLoadPhase === "error" ? (
            <button type="button" onClick={() => void loadSources()}>
              <RefreshCw size={15} aria-hidden="true" />
              重新读取
            </button>
          ) : null}
        </div>
      ) : null}

      {sourceLoadPhase === "ready" ? (
        <form className="fork-form" onSubmit={submitFork}>
          <label className="fork-source-control">
            <span>源运行</span>
            <select
              value={sourceRunId}
              onChange={(event) => selectSource(event.target.value)}
              disabled={disabled || submitting || selectedRunId !== null}
            >
              {sources.map((run) => (
                <option value={run.run_id} key={run.run_id}>
                  {forkSourceLabel(run)}
                </option>
              ))}
            </select>
          </label>
          <button
            className="fork-submit-button"
            type="submit"
            disabled={disabled || submitting || !selectedSource || permissionError}
          >
            {submitting
              ? <LoaderCircle className="spinning-icon" size={17} aria-hidden="true" />
              : <GitFork size={17} aria-hidden="true" />}
            {forkSubmitLabel(phase)}
          </button>
        </form>
      ) : null}

      {sourceLoadPhase === "ready" && failureMessage ? (
        <div
          className="fork-panel-state fork-submission-state"
          data-tone={phase === "permission_error" ? "permission" : "warning"}
          role="alert"
        >
          {phase === "permission_error"
            ? <ShieldAlert size={18} aria-hidden="true" />
            : <CircleAlert size={18} aria-hidden="true" />}
          <span>{failureMessage}</span>
          {refreshContextAfterFailure ? (
            <button type="button" onClick={refreshAfterFailure}>
              <RefreshCw size={15} aria-hidden="true" />
              重新读取
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function isCurrentOperation(
  mounted: boolean,
  activeContextKey: string,
  activeVersion: number,
  requestedContextKey: string,
  requestedVersion: number,
): boolean {
  return mounted
    && activeContextKey === requestedContextKey
    && activeVersion === requestedVersion;
}

function forkSourceLabel(run: ProductRunSummary): string {
  return `第 ${run.attempt} 次运行 · ${statusLabels[run.status]} · ${formatDateTime(run.finished_at ?? run.created_at)}`;
}

function forkSubmitLabel(phase: ForkPanelPhase): string {
  if (phase === "submitting") return "正在创建分支";
  if (phase === "network_error") return "重试创建分支";
  if (phase === "accepted") return "分支已排队";
  return "创建分支";
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
