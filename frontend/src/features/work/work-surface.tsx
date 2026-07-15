"use client";

import { CircleAlert, CircleX, RefreshCw, Send } from "lucide-react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { AnalysisProjection } from "@/features/analysis/analysis-projection";
import { OfficialRunStream } from "@/features/agent-runtime/official-run-stream";
import { HumanReviewPanel } from "@/features/work/human-review-panel";
import {
  cancelTask,
  createAnalysis,
  getTask,
  ProductApiError,
  respondInterrupt,
} from "@/lib/api/product-client";
import type {
  AgentStreamBinding,
  InterruptResponse,
  PendingInterrupt,
  ProductSymbol,
  ProductTask,
} from "@/lib/schemas/product-api";

const symbols: Array<{ short: string; value: ProductSymbol }> = [
  { short: "BTC", value: "BTC-USDT-SWAP" },
  { short: "ETH", value: "ETH-USDT-SWAP" },
  { short: "SOL", value: "SOL-USDT-SWAP" },
];

const terminalStatuses = new Set(["succeeded", "blocked", "failed", "cancelled"]);
const productTaskIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const officialStreamAttachDelayMs = 1_000;
const taskPollIntervalMs = 1_000;
const subscribeHydration = () => () => undefined;

export function WorkSurface() {
  const hydrated = useSyncExternalStore(
    subscribeHydration,
    () => true,
    () => false,
  );
  const [symbol, setSymbol] = useState<ProductSymbol>("BTC-USDT-SWAP");
  const [horizon, setHorizon] = useState("4h");
  const [query, setQuery] = useState("");
  const [task, setTask] = useState<ProductTask | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [recoverableTaskId, setRecoverableTaskId] = useState<string | null>(null);
  const [streamBinding, setStreamBinding] = useState<AgentStreamBinding | null>(null);
  const [historicalRunSelection, setHistoricalRunSelection] = useState(false);
  const pollVersion = useRef(0);
  const submitLock = useRef(false);
  const cancelLock = useRef(false);
  const cancelRequest = useRef<{ taskId: string; idempotencyKey: string } | null>(null);
  const pollingLock = useRef(false);
  const taskRef = useRef<ProductTask | null>(null);
  const selectedRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    taskRef.current = task;
    if (task === null || terminalStatuses.has(task.status)) {
      cancelRequest.current = null;
      cancelLock.current = false;
    }
  }, [task]);

  const pollTask = useCallback(async (
    initialTask: ProductTask,
    version: number,
    selectedRunId: string | null,
  ) => {
    let currentTask = initialTask;

    try {
      while (
        shouldPollTask(currentTask)
        && pollVersion.current === version
      ) {
        await delay(taskPollIntervalMs);
        if (pollVersion.current !== version) return;

        currentTask = await getTask(
          initialTask.task_id,
          undefined,
          selectedRunId ?? undefined,
        );
        if (pollVersion.current !== version) return;
        setTask(currentTask);
        setRequestError(null);
        setRecoverableTaskId(null);
      }
    } catch (error) {
      if (pollVersion.current !== version) return;
      setRecoverableTaskId(
        isRecoverableTaskRead(error) ? initialTask.task_id : null,
      );
      setRequestError(readableRequestError(error));
    } finally {
      if (pollVersion.current === version) {
        pollingLock.current = false;
        setPolling(false);
      }
    }
  }, []);

  const startPolling = useCallback((
    initialTask: ProductTask,
    version: number,
    selectedRunId: string | null,
  ) => {
    if (
      pollVersion.current !== version
      || !shouldPollTask(initialTask)
    ) return;

    pollingLock.current = true;
    setPolling(true);
    void pollTask(initialTask, version, selectedRunId);
  }, [pollTask]);

  const recoverTask = useCallback(async (
    taskId: string,
    selectedRunId: string | null,
  ) => {
    const version = pollVersion.current + 1;
    pollVersion.current = version;
    pollingLock.current = true;
    setPolling(true);
    setRequestError(null);
    setRecoverableTaskId(null);
    selectedRunIdRef.current = selectedRunId;
    setHistoricalRunSelection(selectedRunId !== null);

    try {
      const recoveredTask = await getTask(
        taskId,
        undefined,
        selectedRunId ?? undefined,
      );
      if (pollVersion.current !== version) return;
      setTask(recoveredTask);
      setSymbol(recoveredTask.symbol);
      setHorizon(recoveredTask.horizon);
      if (recoveredTask.query_text !== null) setQuery(recoveredTask.query_text);
      pollingLock.current = false;
      setPolling(false);
      startPolling(recoveredTask, version, selectedRunId);
    } catch (error) {
      if (pollVersion.current !== version) return;
      pollingLock.current = false;
      setPolling(false);
      setRecoverableTaskId(isRecoverableTaskRead(error) ? taskId : null);
      setRequestError(readableRequestError(error));
    }
  }, [startPolling]);

  const refreshProductTask = useCallback(async (taskId: string) => {
    const version = pollVersion.current;
    try {
      const refreshedTask = await getTask(
        taskId,
        undefined,
        selectedRunIdRef.current ?? undefined,
      );
      if (pollVersion.current !== version || taskRef.current?.task_id !== taskId) return;
      setTask(refreshedTask);
      setRequestError(null);
      setRecoverableTaskId(null);

      if (!shouldPollTask(refreshedTask)) {
        pollVersion.current += 1;
        pollingLock.current = false;
        setPolling(false);
      } else if (!pollingLock.current) {
        startPolling(refreshedTask, version, selectedRunIdRef.current);
      }
    } catch (error) {
      if (pollVersion.current !== version || taskRef.current?.task_id !== taskId) return;
      setRecoverableTaskId(isRecoverableTaskRead(error) ? taskId : null);
      setRequestError(readableRequestError(error));
    }
  }, [startPolling]);

  const handleOfficialCompleted = useCallback(() => {
    const taskId = taskRef.current?.task_id;
    if (taskId) void refreshProductTask(taskId);
  }, [refreshProductTask]);

  const respondToPendingInterrupt = useCallback(async (
    interrupt: PendingInterrupt,
    response: InterruptResponse,
    idempotencyKey: string,
  ) => {
    const currentTask = taskRef.current;
    if (
      currentTask === null
      || currentTask.task_id !== interrupt.task_id
      || selectedRunIdRef.current !== null
    ) {
      throw new ProductApiError("该审核项已不属于当前实时任务，请重新读取任务状态。", 409);
    }

    const updatedTask = await respondInterrupt(
      interrupt.task_id,
      interrupt.interrupt_id,
      response,
      undefined,
      idempotencyKey,
    );
    if (taskRef.current?.task_id !== interrupt.task_id) return updatedTask;

    const version = pollVersion.current + 1;
    pollVersion.current = version;
    pollingLock.current = false;
    setPolling(false);
    setTask(updatedTask);
    setRequestError(null);
    setRecoverableTaskId(null);
    startPolling(updatedTask, version, null);
    return updatedTask;
  }, [startPolling]);

  const refreshAfterInterruptConflict = useCallback(() => {
    const taskId = taskRef.current?.task_id;
    if (taskId !== undefined) void recoverTask(taskId, null);
  }, [recoverTask]);

  useEffect(() => {
    const selection = taskSelectionFromLocation();
    const recoveryTimer = selection === null
      ? undefined
      : window.setTimeout(
        () => void recoverTask(selection.taskId, selection.runId),
        0,
      );

    return () => {
      if (recoveryTimer !== undefined) window.clearTimeout(recoveryTimer);
      pollVersion.current += 1;
      submitLock.current = false;
      pollingLock.current = false;
    };
  }, [recoverTask]);

  const agentAssistantId = task?.agent_stream?.assistant_id ?? null;
  const agentThreadId = task?.agent_stream?.thread_id ?? null;
  const agentRunId = task?.agent_stream?.run_id ?? null;
  const streamEligible = task !== null
    && !historicalRunSelection
    && !terminalStatuses.has(task.status)
    && task.cancel_requested_at === null;

  useEffect(() => {
    if (
      !streamEligible
      || agentAssistantId === null
      || agentThreadId === null
      || agentRunId === null
    ) return;

    const timer = window.setTimeout(() => {
      setStreamBinding({
        protocol: "langgraph-v2",
        assistant_id: agentAssistantId,
        thread_id: agentThreadId,
        run_id: agentRunId,
      });
    }, officialStreamAttachDelayMs);
    return () => window.clearTimeout(timer);
  }, [agentAssistantId, agentRunId, agentThreadId, streamEligible]);

  const activeStreamBinding = streamBinding?.assistant_id === agentAssistantId
    && streamBinding.thread_id === agentThreadId
    && streamBinding.run_id === agentRunId
    && streamEligible
    ? streamBinding
    : null;

  const active = submitting || polling || cancelling;
  const controlsDisabled = !hydrated || active;
  const liveTask = task !== null
    && !historicalRunSelection
    && !terminalStatuses.has(task.status);
  const cancellationPending = liveTask && task.cancel_requested_at !== null;

  const createProductTask = useCallback(async () => {
    if (submitLock.current) return;

    submitLock.current = true;
    const version = pollVersion.current + 1;
    pollVersion.current = version;
    pollingLock.current = false;
    setSubmitting(true);
    setPolling(false);
    setRequestError(null);
    setRecoverableTaskId(null);
    setStreamBinding(null);
    cancelRequest.current = null;
    cancelLock.current = false;
    setTask(null);
    selectedRunIdRef.current = null;
    setHistoricalRunSelection(false);

    try {
      const createdTask = await createAnalysis({
        symbol,
        horizon,
        query_text: query,
        notify: false,
      });
      if (pollVersion.current !== version) {
        submitLock.current = false;
        return;
      }

      setTask(createdTask);
      persistTaskId(createdTask.task_id);
      setSubmitting(false);
      submitLock.current = false;
      startPolling(createdTask, version, null);
    } catch (error) {
      submitLock.current = false;
      if (pollVersion.current !== version) return;
      setSubmitting(false);
      setRequestError(readableRequestError(error));
    }
  }, [horizon, query, startPolling, symbol]);

  const cancelCurrentTask = useCallback(async () => {
    const currentTask = taskRef.current;
    if (
      currentTask === null
      || historicalRunSelection
      || terminalStatuses.has(currentTask.status)
      || currentTask.cancel_requested_at !== null
      || cancelLock.current
    ) return;

    cancelLock.current = true;
    const request = cancelRequest.current?.taskId === currentTask.task_id
      ? cancelRequest.current
      : {
          taskId: currentTask.task_id,
          idempotencyKey: crypto.randomUUID(),
        };
    cancelRequest.current = request;
    const version = pollVersion.current + 1;
    pollVersion.current = version;
    pollingLock.current = false;
    setPolling(false);
    setCancelling(true);
    setRequestError(null);
    setRecoverableTaskId(null);
    try {
      const requested = await cancelTask(
        currentTask.task_id,
        undefined,
        request.idempotencyKey,
      );
      if (pollVersion.current !== version) return;
      setTask(requested);
      startPolling(requested, version, null);
    } catch (error) {
      if (pollVersion.current !== version) return;
      setRequestError(readableRequestError(error));
      startPolling(
        { ...currentTask, cancel_requested_at: new Date().toISOString() },
        version,
        null,
      );
    } finally {
      cancelLock.current = false;
      setCancelling(false);
    }
  }, [historicalRunSelection, startPolling]);

  function submitAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void createProductTask();
  }

  function resumePolling() {
    if (!recoverableTaskId || pollingLock.current) return;
    void recoverTask(recoverableTaskId, selectedRunIdRef.current);
  }

  return (
    <div className="work-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Work / New analysis</p>
          <h1>市场分析工作台</h1>
          <p>提交一项人工决策分析，持续读取产品状态与最终报告。</p>
        </div>
        <span className="boundary-label">
          <CircleAlert size={17} aria-hidden="true" />
          不执行交易
        </span>
      </header>

      {requestError ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div>
            <h2>请求未完成</h2>
            <p>{requestError}</p>
          </div>
          {recoverableTaskId ? (
            <button className="submit-button" type="button" onClick={resumePolling} disabled={polling}>
              <RefreshCw size={17} aria-hidden="true" />
              恢复读取
            </button>
          ) : null}
        </section>
      ) : null}

      {activeStreamBinding && !historicalRunSelection ? (
        <OfficialRunStream
          binding={activeStreamBinding}
          onCompleted={handleOfficialCompleted}
        />
      ) : null}

      {liveTask ? (
        <div className="task-command-bar" role="group" aria-label="任务操作">
          <button
            className="cancel-task-button"
            type="button"
            onClick={() => void cancelCurrentTask()}
            disabled={cancelling || cancellationPending}
            aria-describedby={cancellationPending ? "cancel-task-status" : undefined}
          >
            <CircleX size={17} aria-hidden="true" />
            {cancelling || cancellationPending ? "正在停止" : "取消分析"}
          </button>
          {cancellationPending ? (
            <span id="cancel-task-status" className="task-command-status" role="status">
              取消请求已保存，正在安全停止本次执行。
            </span>
          ) : null}
        </div>
      ) : null}

      {task && task.pending_interrupts.length > 0 ? (
        <div className="hitl-review-stack">
          {task.pending_interrupts.map((interrupt) => (
            <HumanReviewPanel
              key={`${interrupt.interrupt_id}:${interrupt.response_version}`}
              interrupt={interrupt}
              disabled={historicalRunSelection || cancelling || cancellationPending}
              onRespond={(response, idempotencyKey) =>
                respondToPendingInterrupt(interrupt, response, idempotencyKey)}
              onConflict={refreshAfterInterruptConflict}
            />
          ))}
        </div>
      ) : null}

      {task ? (
        <AnalysisProjection
          key={`${task.task_id}:${task.status}:${task.artifact?.content_version ?? 0}`}
          task={task}
          onRetry={!active && query.trim().length >= 4 ? createProductTask : undefined}
          retrying={submitting}
        />
      ) : null}

      {!task && (submitting || polling) ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div>
            <h2>{submitting ? "正在提交分析" : "正在恢复分析"}</h2>
            <p>{submitting ? "正在创建持久化任务。" : "正在读取已保存的任务与运行状态。"}</p>
          </div>
        </section>
      ) : null}

      <section
        className={`composer-panel${task ? " composer-panel-after-task" : ""}`}
        aria-labelledby="analysis-request-title"
      >
        <div className="section-heading">
          <div>
            <h2 id="analysis-request-title">分析请求</h2>
            <p>选择标的与周期，并描述需要判断的问题。</p>
          </div>
          <span className="service-indicator"><span aria-hidden="true" />Product API</span>
        </div>

        <form className="analysis-form" onSubmit={submitAnalysis}>
          <fieldset className="symbol-fieldset" disabled={controlsDisabled}>
            <legend>分析标的</legend>
            <div className="segmented-control">
              {symbols.map((item) => (
                <label key={item.value}>
                  <input
                    type="radio"
                    name="symbol"
                    value={item.value}
                    checked={symbol === item.value}
                    onChange={() => setSymbol(item.value)}
                    aria-label={item.short}
                  />
                  <span>{item.short}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <label className="field-control horizon-control">
            <span>分析周期</span>
            <select
              value={horizon}
              onChange={(event) => setHorizon(event.target.value)}
              disabled={controlsDisabled}
            >
              <option value="15m">15 分钟</option>
              <option value="1h">1 小时</option>
              <option value="4h">4 小时</option>
              <option value="1d">1 天</option>
            </select>
          </label>

          <label className="field-control query-control">
            <span>分析问题</span>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="例如：结合近期宏观事件和市场结构，判断当前方向与失效条件"
              minLength={4}
              maxLength={2000}
              rows={4}
              required
              disabled={controlsDisabled}
            />
          </label>

          <div className="form-actions">
            <p>分析结果仅供人工决策参考，所有操作均需自行确认。</p>
            <button
              className="submit-button"
              type="submit"
              disabled={controlsDisabled || query.trim().length < 4}
            >
              <Send size={18} aria-hidden="true" />
              {submitting
                ? "正在提交"
                : cancelling || cancellationPending
                  ? "正在停止"
                  : active
                    ? "分析处理中"
                    : "开始分析"}
            </button>
          </div>
        </form>
      </section>

      {!task && hydrated && !submitting && !polling && !requestError
        ? <EmptyWorkState />
        : null}
    </div>
  );
}

function EmptyWorkState() {
  return (
    <section className="empty-work-state" aria-label="尚未提交分析">
      <span className="empty-state-line" aria-hidden="true" />
      <div>
        <h2>等待新的分析请求</h2>
        <p>提交后将在这里显示排队、执行、门禁与最终报告状态。</p>
      </div>
    </section>
  );
}

function readableRequestError(error: unknown): string {
  if (error instanceof ProductApiError) return error.message;
  return "无法连接 Product API，请检查本地服务后重试。";
}

function isRecoverableTaskRead(error: unknown): boolean {
  if (!(error instanceof ProductApiError)) return true;
  return error.status === 408 || error.status === 429 || error.status >= 500;
}

function shouldPollTask(task: ProductTask) {
  return !terminalStatuses.has(task.status);
}

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function taskSelectionFromLocation(): { taskId: string; runId: string | null } | null {
  const search = new URLSearchParams(window.location.search);
  const taskId = search.get("task");
  if (!taskId || !productTaskIdPattern.test(taskId)) return null;
  const candidateRunId = search.get("run");
  const runId = candidateRunId && productTaskIdPattern.test(candidateRunId)
    ? candidateRunId
    : null;
  return { taskId, runId };
}

function persistTaskId(taskId: string) {
  if (!productTaskIdPattern.test(taskId)) return;
  const url = new URL(window.location.href);
  url.searchParams.set("task", taskId);
  url.searchParams.delete("run");
  window.history.replaceState(window.history.state, "", url);
}
