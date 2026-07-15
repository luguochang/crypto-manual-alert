"use client";

import { CircleAlert, CircleCheck, CircleX, RefreshCw, Send } from "lucide-react";
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
import {
  HumanReviewPanel,
  isServerExpiredReviewConflict,
  type ReviewSubmissionPhase,
} from "@/features/work/human-review-panel";
import {
  forkContextKey,
  resolveForkAcceptedTransition,
  shouldOfferForkControl,
  type ForkContext,
} from "@/features/work/fork-control";
import { TaskForkPanel } from "@/features/work/task-fork-panel";
import {
  cancelTask,
  createAnalysis,
  getTask,
  ProductApiError,
  respondAllInterrupts,
} from "@/lib/api/product-client";
import {
  interruptResponseSchema,
  respondAllInterruptsSchema,
  type AgentStreamBinding,
  type InterruptResponse,
  type PendingInterruptPause,
  type ProductSymbol,
  type ProductTask,
  type RespondAllInterrupts,
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

export type ReviewBatchRequestIdentity = {
  fingerprint: string;
  idempotencyKey: string;
};

type ReviewBatchDisplayState = ReviewSubmissionPhase | "responding";

export type ReviewBatchCoordinatorState = {
  authorityFingerprint: string | null;
  drafts: Readonly<Record<string, InterruptResponse>>;
  phase: ReviewSubmissionPhase;
  failureMessage: string | null;
  retryRequest: ReviewBatchRequestIdentity | null;
};

export type ReviewSubmissionFailure = {
  phase: Exclude<ReviewSubmissionPhase, "idle" | "submitting" | "accepted">;
  message: string;
  preserveRequestIdentity: boolean;
  refreshTask: boolean;
};

export function createEmptyReviewBatchState(
  authorityFingerprint: string | null = null,
): ReviewBatchCoordinatorState {
  return {
    authorityFingerprint,
    drafts: {},
    phase: "idle",
    failureMessage: null,
    retryRequest: null,
  };
}

export function reviewPauseFingerprint(pause: PendingInterruptPause): string {
  const members = pause.members
    .map((member) => [member.interrupt_id, member.response_version] as const)
    .sort(([left], [right]) => left.localeCompare(right));
  return JSON.stringify([pause.pause_id, pause.pause_version, members]);
}

export function reconcileReviewBatchState(
  current: ReviewBatchCoordinatorState,
  pause: PendingInterruptPause | null,
): ReviewBatchCoordinatorState {
  if (pause === null) {
    return current.authorityFingerprint === null
      ? current
      : createEmptyReviewBatchState();
  }

  const authorityFingerprint = reviewPauseFingerprint(pause);
  if (current.authorityFingerprint !== authorityFingerprint) {
    return createEmptyReviewBatchState(authorityFingerprint);
  }
  if (pause.status === "responding" && (
    Object.keys(current.drafts).length > 0
    || current.retryRequest !== null
    || current.failureMessage !== null
    || current.phase !== "idle"
  )) {
    return createEmptyReviewBatchState(authorityFingerprint);
  }
  return current;
}

export function recordReviewDecision(
  current: ReviewBatchCoordinatorState,
  pause: PendingInterruptPause,
  interruptId: string,
  response: InterruptResponse,
): ReviewBatchCoordinatorState {
  const reconciled = reconcileReviewBatchState(current, pause);
  if (
    pause.status !== "pending"
    || !pause.members.some((member) => member.interrupt_id === interruptId)
  ) {
    throw new Error("Review decision does not belong to the active pending pause");
  }
  return {
    ...reconciled,
    drafts: {
      ...reconciled.drafts,
      [interruptId]: interruptResponseSchema.parse(response),
    },
    phase: reconciled.phase === "network_error" ? "idle" : reconciled.phase,
    failureMessage: reconciled.phase === "network_error"
      ? null
      : reconciled.failureMessage,
  };
}

export function buildRespondAllSubmission(
  pause: PendingInterruptPause,
  drafts: Readonly<Record<string, InterruptResponse>>,
): RespondAllInterrupts {
  const memberIds = new Set(pause.members.map((member) => member.interrupt_id));
  const draftIds = Object.keys(drafts);
  if (
    pause.status !== "pending"
    || draftIds.length !== memberIds.size
    || draftIds.some((interruptId) => !memberIds.has(interruptId))
    || pause.members.some((member) => drafts[member.interrupt_id] === undefined)
  ) {
    throw new Error("Every member of the active pause requires exactly one decision");
  }

  return respondAllInterruptsSchema.parse({
    pause_id: pause.pause_id,
    pause_version: pause.pause_version,
    responses: pause.members.map((member) => ({
      interrupt_id: member.interrupt_id,
      response_version: member.response_version,
      response: drafts[member.interrupt_id],
    })),
  });
}

export function isReviewBatchComplete(
  pause: PendingInterruptPause,
  state: ReviewBatchCoordinatorState,
): boolean {
  try {
    buildRespondAllSubmission(pause, state.drafts);
    return state.authorityFingerprint === reviewPauseFingerprint(pause);
  } catch {
    return false;
  }
}

export function resolveReviewBatchRequestIdentity(
  input: RespondAllInterrupts,
  previous: ReviewBatchRequestIdentity | null,
  createIdempotencyKey: () => string = () => crypto.randomUUID(),
): ReviewBatchRequestIdentity {
  const fingerprint = JSON.stringify(respondAllInterruptsSchema.parse(input));
  return previous?.fingerprint === fingerprint
    ? previous
    : { fingerprint, idempotencyKey: createIdempotencyKey() };
}

export function hasUnsubmittedReviewDrafts(
  pause: PendingInterruptPause | null,
  state: ReviewBatchCoordinatorState,
): boolean {
  return pause?.status === "pending"
    && state.authorityFingerprint === reviewPauseFingerprint(pause)
    && Object.keys(state.drafts).length > 0;
}

export function classifyReviewSubmissionFailure(error: unknown): ReviewSubmissionFailure {
  if (!(error instanceof ProductApiError)) {
    return {
      phase: "network_error",
      message: "网络连接中断，本次整组响应尚未得到服务端确认。",
      preserveRequestIdentity: true,
      refreshTask: false,
    };
  }
  if (error.status === 409) {
    const expired = isServerExpiredReviewConflict(error.status, error.message);
    return {
      phase: expired ? "expired" : "conflict",
      message: expired
        ? "服务端已关闭本次审核窗口，正在读取任务的最终状态。"
        : "该审核请求已被处理或版本已更新，正在重新读取服务端状态。",
      preserveRequestIdentity: false,
      refreshTask: true,
    };
  }
  if (error.status === 401 || error.status === 403) {
    return {
      phase: "auth_error",
      message: error.status === 401
        ? "登录状态已失效，请重新登录后再读取任务。"
        : "当前账号无权提交这组审核决定。",
      preserveRequestIdentity: false,
      refreshTask: false,
    };
  }
  if (
    error.status === 408
    || error.status === 429
    || (error.status >= 500 && error.status <= 599)
  ) {
    return {
      phase: "network_error",
      message: error.message,
      preserveRequestIdentity: true,
      refreshTask: false,
    };
  }
  return {
    phase: "invalid_request",
    message: error.status === 404
      ? "审核任务或暂停已不存在，正在重新读取服务端状态。"
      : error.status === 422
        ? "服务端拒绝了审核内容，正在重新读取任务；请勿重试旧请求。"
        : "服务端未接受这组审核决定，正在重新读取任务状态。",
    preserveRequestIdentity: false,
    refreshTask: true,
  };
}

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
  const [selectedProductRunId, setSelectedProductRunId] = useState<string | null>(null);
  const [forkNoticeTaskId, setForkNoticeTaskId] = useState<string | null>(null);
  const [reviewBatch, setReviewBatch] = useState<ReviewBatchCoordinatorState>(
    createEmptyReviewBatchState,
  );
  const pollVersion = useRef(0);
  const submitLock = useRef(false);
  const cancelLock = useRef(false);
  const cancelRequest = useRef<{ taskId: string; idempotencyKey: string } | null>(null);
  const pollingLock = useRef(false);
  const reviewSubmissionLock = useRef(false);
  const taskRef = useRef<ProductTask | null>(null);
  const selectedRunIdRef = useRef<string | null>(null);
  const reviewBatchRef = useRef(reviewBatch);

  useEffect(() => {
    taskRef.current = task;
    if (task === null || terminalStatuses.has(task.status)) {
      cancelRequest.current = null;
      cancelLock.current = false;
    }
  }, [task]);

  useEffect(() => {
    setReviewBatch((current) => {
      const next = reconcileReviewBatchState(
        current,
        task?.pending_interrupts ?? null,
      );
      reviewBatchRef.current = next;
      return next;
    });
  }, [task?.pending_interrupts]);

  const updateReviewBatch = useCallback((
    update: (current: ReviewBatchCoordinatorState) => ReviewBatchCoordinatorState,
  ) => {
    const next = update(reviewBatchRef.current);
    reviewBatchRef.current = next;
    setReviewBatch(next);
    return next;
  }, []);

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
    setSelectedProductRunId(selectedRunId);
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
      setQuery(recoveredTask.query_text ?? "");
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

  const submitReviewBatch = useCallback(async (
    preparedState?: ReviewBatchCoordinatorState,
  ) => {
    if (reviewSubmissionLock.current) return;
    const currentTask = taskRef.current;
    const pause = currentTask?.pending_interrupts ?? null;
    if (
      currentTask === null
      || pause === null
      || selectedRunIdRef.current !== null
      || pause.status !== "pending"
      || currentTask.cancel_requested_at !== null
      || cancelLock.current
    ) return;

    const coordinatorState = reconcileReviewBatchState(
      preparedState ?? reviewBatchRef.current,
      pause,
    );
    let submission: RespondAllInterrupts;
    try {
      submission = buildRespondAllSubmission(pause, coordinatorState.drafts);
    } catch {
      return;
    }

    const request = resolveReviewBatchRequestIdentity(
      submission,
      coordinatorState.retryRequest,
    );
    const authorityFingerprint = reviewPauseFingerprint(pause);
    reviewSubmissionLock.current = true;
    updateReviewBatch((current) => current.authorityFingerprint === authorityFingerprint
      ? {
          ...current,
          phase: "submitting",
          failureMessage: null,
          retryRequest: request,
        }
      : current);

    try {
      const updatedTask = await respondAllInterrupts(
        currentTask.task_id,
        submission,
        undefined,
        request.idempotencyKey,
      );
      if (
        taskRef.current?.task_id !== currentTask.task_id
        || taskRef.current.pending_interrupts === null
        || reviewPauseFingerprint(taskRef.current.pending_interrupts) !== authorityFingerprint
      ) return;

      updateReviewBatch((current) => current.authorityFingerprint === authorityFingerprint
        ? {
            ...current,
            phase: "accepted",
            failureMessage: null,
            retryRequest: null,
          }
        : current);
      const version = pollVersion.current + 1;
      pollVersion.current = version;
      pollingLock.current = false;
      setPolling(false);
      setTask(updatedTask);
      setRequestError(null);
      setRecoverableTaskId(null);
      startPolling(updatedTask, version, null);
    } catch (error) {
      if (
        taskRef.current?.task_id !== currentTask.task_id
        || taskRef.current.pending_interrupts === null
        || reviewPauseFingerprint(taskRef.current.pending_interrupts) !== authorityFingerprint
      ) return;

      const failure = classifyReviewSubmissionFailure(error);
      updateReviewBatch((current) => current.authorityFingerprint === authorityFingerprint
        ? {
            ...current,
            phase: failure.phase,
            failureMessage: failure.message,
            retryRequest: failure.preserveRequestIdentity ? request : null,
          }
        : current);
      if (failure.refreshTask) void recoverTask(currentTask.task_id, null);
    } finally {
      reviewSubmissionLock.current = false;
    }
  }, [recoverTask, startPolling, updateReviewBatch]);

  const handleReviewDecision = useCallback((
    pause: PendingInterruptPause,
    interruptId: string,
    response: InterruptResponse,
  ) => {
    const currentTask = taskRef.current;
    const currentPause = currentTask?.pending_interrupts ?? null;
    if (
      currentTask === null
      || currentPause === null
      || selectedRunIdRef.current !== null
      || reviewPauseFingerprint(currentPause) !== reviewPauseFingerprint(pause)
    ) return;

    let preparedState: ReviewBatchCoordinatorState;
    try {
      preparedState = updateReviewBatch((current) =>
        recordReviewDecision(current, currentPause, interruptId, response));
    } catch {
      return;
    }
    if (currentPause.members.length === 1) {
      void submitReviewBatch(preparedState);
    }
  }, [submitReviewBatch, updateReviewBatch]);

  useEffect(() => {
    const pause = task?.pending_interrupts ?? null;
    if (!hasUnsubmittedReviewDrafts(pause, reviewBatch)) return;

    const protectDrafts = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protectDrafts);
    return () => window.removeEventListener("beforeunload", protectDrafts);
  }, [reviewBatch, task?.pending_interrupts]);

  const loadTaskSelectionFromLocation = useCallback(() => {
    const selection = taskSelectionFromLocation();
    pollVersion.current += 1;
    pollingLock.current = false;
    submitLock.current = false;
    reviewSubmissionLock.current = false;
    cancelLock.current = false;
    cancelRequest.current = null;
    taskRef.current = null;
    selectedRunIdRef.current = selection?.runId ?? null;
    setSelectedProductRunId(selection?.runId ?? null);
    const emptyReviewBatch = createEmptyReviewBatchState();
    reviewBatchRef.current = emptyReviewBatch;
    setReviewBatch(emptyReviewBatch);
    setTask(null);
    setStreamBinding(null);
    setRequestError(null);
    setRecoverableTaskId(null);
    setSubmitting(false);
    setPolling(false);
    setCancelling(false);
    setForkNoticeTaskId(null);
    setHistoricalRunSelection(selection?.runId !== null && selection !== null);
    if (selection !== null) void recoverTask(selection.taskId, selection.runId);
  }, [recoverTask]);

  useEffect(() => {
    const recoveryTimer = window.setTimeout(loadTaskSelectionFromLocation, 0);
    window.addEventListener("popstate", loadTaskSelectionFromLocation);

    return () => {
      window.clearTimeout(recoveryTimer);
      window.removeEventListener("popstate", loadTaskSelectionFromLocation);
      pollVersion.current += 1;
      submitLock.current = false;
      pollingLock.current = false;
      reviewSubmissionLock.current = false;
    };
  }, [loadTaskSelectionFromLocation]);

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
    reviewSubmissionLock.current = false;
    const emptyReviewBatch = createEmptyReviewBatchState();
    reviewBatchRef.current = emptyReviewBatch;
    setReviewBatch(emptyReviewBatch);
    setTask(null);
    selectedRunIdRef.current = null;
    setSelectedProductRunId(null);
    setHistoricalRunSelection(false);
    setForkNoticeTaskId(null);

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
      || reviewSubmissionLock.current
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

  const handleForkAccepted = useCallback((
    requestedContext: ForkContext,
    forkedTask: ProductTask,
  ) => {
    const currentTask = taskRef.current;
    if (currentTask === null) return;
    const transition = resolveForkAcceptedTransition(
      requestedContext,
      {
        taskId: currentTask.task_id,
        selectedRunId: selectedRunIdRef.current,
      },
      forkedTask,
    );
    if (transition === null) return;

    const version = pollVersion.current + 1;
    pollVersion.current = version;
    pollingLock.current = false;
    reviewSubmissionLock.current = false;
    cancelLock.current = false;
    cancelRequest.current = null;
    const emptyReviewBatch = createEmptyReviewBatchState();
    reviewBatchRef.current = emptyReviewBatch;
    setReviewBatch(emptyReviewBatch);
    taskRef.current = transition.task;
    setTask(transition.task);
    setStreamBinding(null);
    setRequestError(null);
    setRecoverableTaskId(null);
    setPolling(false);
    setCancelling(false);
    selectedRunIdRef.current = null;
    setSelectedProductRunId(null);
    setHistoricalRunSelection(false);
    setForkNoticeTaskId(transition.task.task_id);
    persistTaskId(transition.task.task_id);
    if (transition.shouldPoll) startPolling(transition.task, version, null);
  }, [startPolling]);

  const refreshForkContext = useCallback((requestedContext: ForkContext) => {
    const currentTask = taskRef.current;
    if (
      currentTask === null
      || requestedContext.taskId !== currentTask.task_id
      || requestedContext.selectedRunId !== selectedRunIdRef.current
    ) return;
    void recoverTask(requestedContext.taskId, requestedContext.selectedRunId);
  }, [recoverTask]);

  function submitAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void createProductTask();
  }

  function resumePolling() {
    if (!recoverableTaskId || pollingLock.current) return;
    void recoverTask(recoverableTaskId, selectedRunIdRef.current);
  }

  const pendingPause = task?.pending_interrupts ?? null;
  const renderedReviewBatch = reconcileReviewBatchState(reviewBatch, pendingPause);
  const reviewBatchComplete = pendingPause !== null
    && isReviewBatchComplete(pendingPause, renderedReviewBatch);
  const draftedReviewCount = pendingPause === null
    ? 0
    : pendingPause.members.filter(
      (member) => renderedReviewBatch.drafts[member.interrupt_id] !== undefined,
    ).length;
  const externalReviewDisabled = historicalRunSelection
    || cancelling
    || cancellationPending;
  const reviewBatchDisplayState: ReviewBatchDisplayState = pendingPause?.status === "responding"
    ? "responding"
    : renderedReviewBatch.phase;
  const forkControlDisabled = cancelling
    || cancellationPending
    || renderedReviewBatch.phase === "submitting";

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

      {forkNoticeTaskId !== null && forkNoticeTaskId === task?.task_id ? (
        <section className="fork-success-notice" role="status">
          <CircleCheck size={20} aria-hidden="true" />
          <div>
            <h2>分支已排队</h2>
            <p>已切换到新的运行，Product 状态将继续更新。</p>
          </div>
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
            disabled={
              cancelling
              || cancellationPending
              || renderedReviewBatch.phase === "submitting"
            }
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

      {pendingPause !== null ? (
        <div className="hitl-review-stack">
          {pendingPause.members.map((interrupt, index) => (
            <HumanReviewPanel
              key={`${pendingPause.pause_id}:${pendingPause.pause_version}:${interrupt.interrupt_id}:${interrupt.response_version}`}
              interrupt={interrupt}
              expiresAt={pendingPause.expires_at}
              disabled={externalReviewDisabled}
              phase={renderedReviewBatch.phase}
              failureMessage={renderedReviewBatch.failureMessage}
              decision={renderedReviewBatch.drafts[interrupt.interrupt_id] ?? null}
              deferSubmission={pendingPause.members.length > 1}
              announceSubmissionState={pendingPause.members.length === 1}
              showSubmissionNotice={pendingPause.members.length === 1}
              reviewPosition={pendingPause.members.length > 1
                ? { index: index + 1, total: pendingPause.members.length }
                : undefined}
              onDecide={(response) => handleReviewDecision(
                pendingPause,
                interrupt.interrupt_id,
                response,
              )}
            />
          ))}
          {pendingPause.members.length > 1 ? (
            <section
              className="hitl-confirmation"
              data-tone={reviewBatchComplete || reviewBatchDisplayState === "responding"
                ? "positive"
                : undefined}
              aria-labelledby="review-batch-confirmation-title"
            >
              <div>
                <h3 id="review-batch-confirmation-title">提交整组审核决定</h3>
                <p
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  data-state={reviewBatchDisplayState}
                >
                  {reviewBatchStatusMessage(
                    renderedReviewBatch,
                    draftedReviewCount,
                    pendingPause.members.length,
                    reviewBatchDisplayState,
                  )}
                </p>
              </div>
              <div className="hitl-confirmation-actions">
                <button
                  type="button"
                  className="hitl-action-button is-approve"
                  onClick={() => void submitReviewBatch()}
                  disabled={
                    externalReviewDisabled
                    || !reviewBatchComplete
                    || !reviewBatchCanSubmit(reviewBatchDisplayState)
                  }
                >
                  <Send size={17} aria-hidden="true" />
                  {reviewBatchSubmitLabel(
                    reviewBatchDisplayState,
                    pendingPause.members.length,
                  )}
                </button>
              </div>
            </section>
          ) : null}
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


      {task && shouldOfferForkControl(selectedProductRunId) ? (
        <TaskForkPanel
          key={forkContextKey({
            taskId: task.task_id,
            selectedRunId: selectedProductRunId,
          })}
          task={task}
          selectedRunId={selectedProductRunId}
          disabled={forkControlDisabled}
          onAccepted={handleForkAccepted}
          onRefreshContext={refreshForkContext}
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

function reviewBatchCanSubmit(state: ReviewBatchDisplayState): boolean {
  return state === "idle" || state === "network_error";
}

function reviewBatchStatusMessage(
  state: ReviewBatchCoordinatorState,
  draftedCount: number,
  memberCount: number,
  displayState: ReviewBatchDisplayState,
): string {
  if (displayState === "responding") {
    return "整组决定已持久化，Product 服务正在恢复 Agent 执行。";
  }
  if (displayState === "submitting") {
    return "正在一次性提交整组审核决定，请勿重复操作。";
  }
  if (displayState === "accepted") {
    return "整组审核决定已保存，正在同步 Product 任务状态。";
  }
  if (displayState === "conflict") {
    return state.failureMessage ?? "审核状态已更新，正在重新读取服务端状态。";
  }
  if (displayState === "expired") {
    return "服务端已关闭本次审核窗口，最终状态以重新读取的任务为准。";
  }
  if (displayState === "network_error") {
    return state.failureMessage ?? "整组响应尚未得到服务端确认，可以原样重试。";
  }
  if (displayState === "auth_error") {
    return state.failureMessage ?? "登录状态或账号权限不足，不能提交整组决定。";
  }
  if (displayState === "invalid_request") {
    return state.failureMessage ?? "服务端未接受旧请求，不能原样重试。";
  }
  return `本页已选择 ${draftedCount} / ${memberCount} 项决定；全部完成后可一次提交。`;
}

function reviewBatchSubmitLabel(
  state: ReviewBatchDisplayState,
  memberCount: number,
): string {
  if (state === "submitting") return "正在提交整组决定";
  if (state === "accepted") return "整组决定已保存";
  if (state === "responding") return "正在恢复任务";
  if (state === "network_error") return "重试提交整组决定";
  if (state === "conflict" || state === "expired") return "审核状态已更新";
  if (state === "auth_error") return "认证失败，无法提交";
  if (state === "invalid_request") return "请求已拒绝，无法重试";
  return `确认提交 ${memberCount} 项决定`;
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
