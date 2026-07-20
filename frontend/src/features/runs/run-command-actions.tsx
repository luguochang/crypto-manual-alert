"use client";

import { CircleAlert, GitFork, LoaderCircle, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { forkTask, ProductApiError, retryTask } from "@/lib/api/product-client";
import type { RunDetail } from "@/lib/schemas/product-api";

import styles from "./run-command-actions.module.css";

export type DirectRunCommand = "retry" | "fork";

type CommandPhase = "idle" | "submitting" | "error";

type PendingCommandRequest = {
  command: DirectRunCommand;
  contextKey: string;
  idempotencyKey: string;
};

export type RunCommandAvailability = {
  retry: boolean;
  fork: boolean;
};

export type RunCommandFailure = {
  message: string;
  preserveRequestIdentity: boolean;
};

type RunCommandActionsProps = {
  taskId: string;
  sourceRunId: string;
  availability: RunCommandAvailability;
};

const retryableStatuses = new Set(["failed", "blocked", "cancelled"]);
const forkableSourceStatuses = new Set([
  "waiting_human",
  "succeeded",
  "blocked",
  "failed",
]);

export function RunCommandActions({
  taskId,
  sourceRunId,
  availability,
}: RunCommandActionsProps) {
  const router = useRouter();
  const contextKey = `${taskId}:${sourceRunId}`;
  const contextKeyRef = useRef(contextKey);
  const mountedRef = useRef(false);
  const operationVersionRef = useRef(0);
  const submitLockRef = useRef(false);
  const pendingRequestRef = useRef<PendingCommandRequest | null>(null);
  const [phase, setPhase] = useState<CommandPhase>("idle");
  const [activeCommand, setActiveCommand] = useState<DirectRunCommand | null>(null);
  const [failureMessage, setFailureMessage] = useState("");

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      operationVersionRef.current += 1;
      submitLockRef.current = false;
      pendingRequestRef.current = null;
    };
  }, []);

  async function submit(command: DirectRunCommand) {
    if (
      submitLockRef.current
      || (command === "retry" && !availability.retry)
      || (command === "fork" && !availability.fork)
    ) return;

    const request = resolveRunCommandRequest(
      pendingRequestRef.current,
      command,
      contextKey,
    );
    const operationVersion = operationVersionRef.current + 1;
    operationVersionRef.current = operationVersion;
    submitLockRef.current = true;
    pendingRequestRef.current = request;
    setPhase("submitting");
    setActiveCommand(command);
    setFailureMessage("");

    try {
      const task = command === "retry"
        ? await retryTask(taskId, undefined, request.idempotencyKey)
        : await forkTask(
            taskId,
            { source_run_id: sourceRunId },
            undefined,
            request.idempotencyKey,
          );
      if (!isCurrentCommandOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        contextKey,
        operationVersion,
      )) return;
      pendingRequestRef.current = null;
      router.push(workTaskHref(task.task_id));
    } catch (reason) {
      if (!isCurrentCommandOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        contextKey,
        operationVersion,
      )) return;
      const failure = classifyRunCommandFailure(command, reason);
      pendingRequestRef.current = failure.preserveRequestIdentity ? request : null;
      setPhase("error");
      setFailureMessage(failure.message);
    } finally {
      if (isCurrentCommandOperation(
        mountedRef.current,
        contextKeyRef.current,
        operationVersionRef.current,
        contextKey,
        operationVersion,
      )) {
        submitLockRef.current = false;
      }
    }
  }

  if (!availability.retry && !availability.fork) return null;

  const submitting = phase === "submitting";
  return (
    <div className={styles.root} aria-label="运行命令">
      {availability.retry ? (
        <button
          className={styles.retryButton}
          type="button"
          onClick={() => void submit("retry")}
          disabled={submitting}
        >
          {submitting && activeCommand === "retry"
            ? <LoaderCircle className={styles.spinner} size={16} aria-hidden="true" />
            : <RotateCcw size={16} aria-hidden="true" />}
          {submitting && activeCommand === "retry" ? "正在重试" : retryButtonLabel(phase, activeCommand)}
        </button>
      ) : null}
      {availability.fork ? (
        <button
          className={styles.forkButton}
          type="button"
          onClick={() => void submit("fork")}
          disabled={submitting}
        >
          {submitting && activeCommand === "fork"
            ? <LoaderCircle className={styles.spinner} size={16} aria-hidden="true" />
            : <GitFork size={16} aria-hidden="true" />}
          {submitting && activeCommand === "fork" ? "正在创建" : forkButtonLabel(phase, activeCommand)}
        </button>
      ) : null}
      {phase === "error" && failureMessage ? (
        <p className={styles.error} role="alert">
          <CircleAlert size={16} aria-hidden="true" />
          <span>{failureMessage}</span>
        </p>
      ) : null}
    </div>
  );
}

export function directRunCommandAvailability(detail: RunDetail): RunCommandAvailability {
  const currentRunIsRetryable = detail.is_current_run
    && retryableStatuses.has(detail.run.status)
    && retryableStatuses.has(detail.task.status);
  const taskAcceptsFork = !["queued", "running", "cancelled"].includes(detail.task.status);
  return {
    retry: currentRunIsRetryable,
    fork: taskAcceptsFork && forkableSourceStatuses.has(detail.run.status),
  };
}

export function resolveRunCommandRequest(
  previous: PendingCommandRequest | null,
  command: DirectRunCommand,
  contextKey: string,
  createIdempotencyKey: () => string = () => crypto.randomUUID(),
): PendingCommandRequest {
  if (previous?.command === command && previous.contextKey === contextKey) {
    return previous;
  }
  return { command, contextKey, idempotencyKey: createIdempotencyKey() };
}

export function classifyRunCommandFailure(
  command: DirectRunCommand,
  reason: unknown,
): RunCommandFailure {
  const noun = command === "retry" ? "重试" : "分支";
  if (!(reason instanceof ProductApiError)) {
    return {
      message: `网络连接中断，${noun}请求是否到达服务端尚未确认。`,
      preserveRequestIdentity: true,
    };
  }
  if (reason.status === 401) {
    return { message: "登录状态已失效，请重新登录后再操作。", preserveRequestIdentity: false };
  }
  if (reason.status === 403) {
    return { message: `当前账号没有执行${noun}的权限。`, preserveRequestIdentity: false };
  }
  if (reason.status === 404) {
    return { message: "任务或源运行在当前工作区不可用。", preserveRequestIdentity: false };
  }
  if (reason.status === 409) {
    return {
      message: readableCommandConflict(command, reason.message),
      preserveRequestIdentity: false,
    };
  }
  if (
    reason.status === 408
    || reason.status === 429
    || (reason.status >= 500 && reason.status <= 599)
  ) {
    return {
      message: `Product 服务暂时无法确认${noun}请求，可以原样重试。`,
      preserveRequestIdentity: true,
    };
  }
  return {
    message: `服务端未接受${noun}请求，请重新读取运行后再试。`,
    preserveRequestIdentity: false,
  };
}

export function workTaskHref(taskId: string): string {
  return `/work?task=${encodeURIComponent(taskId)}`;
}

function isCurrentCommandOperation(
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

function retryButtonLabel(phase: CommandPhase, activeCommand: DirectRunCommand | null): string {
  return phase === "error" && activeCommand === "retry" ? "重新提交重试" : "重试运行";
}

function forkButtonLabel(phase: CommandPhase, activeCommand: DirectRunCommand | null): string {
  return phase === "error" && activeCommand === "fork" ? "重新提交分支" : "创建分支";
}

function readableCommandConflict(command: DirectRunCommand, message: string): string {
  if (/awaiting dispatch|reconciliation/i.test(message)) {
    return "任务还有命令正在处理中，请等待状态更新后再试。";
  }
  if (command === "retry") {
    if (/latest terminal run is not retryable|only failed|run-cancelled/i.test(message)) {
      return "当前最新运行已不可重试，请重新读取任务状态。";
    }
    return "任务状态已经变化，当前无法重试。";
  }
  if (/cancelled tasks cannot be forked/i.test(message)) {
    return "已取消的任务不能创建分析分支。";
  }
  if (/no forkable checkpoint/i.test(message)) {
    return "该运行没有可用于创建分支的保存点。";
  }
  if (/checkpoint does not match/i.test(message)) {
    return "源运行的保存状态已经变化，请重新读取运行。";
  }
  return "任务状态已经变化，当前无法创建分支。";
}
