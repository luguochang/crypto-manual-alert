import { ProductApiError } from "@/lib/api/product-client";
import {
  forkSubmissionSchema,
  type ForkSubmission,
  type ProductRunSummary,
  type ProductTask,
} from "@/lib/schemas/product-api";
import { stableFingerprint } from "@/lib/stable-fingerprint";

export type ForkContext = {
  taskId: string;
  selectedRunId: string | null;
};

export type ForkRequestIdentity = {
  fingerprint: string;
  idempotencyKey: string;
};

export type ForkFailurePhase =
  | "network_error"
  | "permission_error"
  | "conflict"
  | "unavailable"
  | "invalid_request";

export type ForkSubmissionFailure = {
  phase: ForkFailurePhase;
  message: string;
  preserveRequestIdentity: boolean;
  refreshContext: boolean;
};

export type ForkAcceptedTransition = {
  task: ProductTask;
  selectedRunId: null;
  shouldPoll: boolean;
};

const terminalStatuses = new Set(["succeeded", "blocked", "failed", "cancelled"]);

export function forkContextKey(context: ForkContext): string {
  return `${context.taskId}:${context.selectedRunId ?? "latest"}`;
}

export function isSameForkContext(left: ForkContext, right: ForkContext): boolean {
  return left.taskId === right.taskId && left.selectedRunId === right.selectedRunId;
}

export function shouldOfferForkControl(selectedRunId: string | null): boolean {
  return selectedRunId !== null;
}

export function resolveForkAcceptedTransition(
  requestedContext: ForkContext,
  activeContext: ForkContext,
  forkedTask: ProductTask,
): ForkAcceptedTransition | null {
  if (
    !isSameForkContext(requestedContext, activeContext)
    || forkedTask.task_id !== activeContext.taskId
  ) return null;
  return {
    task: forkedTask,
    selectedRunId: null,
    shouldPoll: !terminalStatuses.has(forkedTask.status),
  };
}

export function forkSourceOptions(
  runs: readonly ProductRunSummary[],
  taskId: string,
  selectedRunId: string | null,
): ProductRunSummary[] {
  const scopedRuns = runs.filter((run) => run.task_id === taskId);
  const selectedRuns = selectedRunId === null
    ? scopedRuns
    : scopedRuns.filter((run) => run.run_id === selectedRunId);
  return [...selectedRuns].sort((left, right) => {
    if (left.attempt !== right.attempt) return right.attempt - left.attempt;
    return Date.parse(right.created_at) - Date.parse(left.created_at);
  });
}

export function resolveForkRequestIdentity(
  input: ForkSubmission,
  previous: ForkRequestIdentity | null,
  createIdempotencyKey: () => string = () => crypto.randomUUID(),
): ForkRequestIdentity {
  const fingerprint = stableFingerprint(forkSubmissionSchema.parse(input));
  return previous?.fingerprint === fingerprint
    ? previous
    : { fingerprint, idempotencyKey: createIdempotencyKey() };
}

export function classifyForkSubmissionFailure(error: unknown): ForkSubmissionFailure {
  if (!(error instanceof ProductApiError)) {
    return {
      phase: "network_error",
      message: "网络连接中断，分支请求是否到达服务端尚未确认。",
      preserveRequestIdentity: true,
      refreshContext: false,
    };
  }
  if (error.status === 401 || error.status === 403) {
    return {
      phase: "permission_error",
      message: error.status === 401
        ? "登录状态已失效，请重新登录后再读取任务。"
        : "当前账号没有在这个工作区创建分析分支的权限。",
      preserveRequestIdentity: false,
      refreshContext: false,
    };
  }
  if (error.status === 404) {
    return {
      phase: "unavailable",
      message: "任务或源运行在当前工作区不可用。",
      preserveRequestIdentity: false,
      refreshContext: false,
    };
  }
  if (error.status === 409) {
    return {
      phase: "conflict",
      message: readableForkConflict(error.message),
      preserveRequestIdentity: false,
      refreshContext: true,
    };
  }
  if (
    error.status === 408
    || error.status === 429
    || (error.status >= 500 && error.status <= 599)
  ) {
    return {
      phase: "network_error",
      message: "Product 服务暂时无法确认分支请求，可以原样重试。",
      preserveRequestIdentity: true,
      refreshContext: false,
    };
  }
  return {
    phase: "invalid_request",
    message: "服务端未接受这个分支请求，请重新读取任务后再试。",
    preserveRequestIdentity: false,
    refreshContext: true,
  };
}

function readableForkConflict(message: string): string {
  if (/cancelled tasks cannot be forked/i.test(message)) {
    return "已取消的任务不能创建分析分支。";
  }
  if (/no forkable checkpoint/i.test(message)) {
    return "该运行没有可用于创建分支的保存点。";
  }
  if (/awaiting dispatch|reconciliation/i.test(message)) {
    return "任务还有命令正在处理中，请等待状态更新后再试。";
  }
  if (/checkpoint does not match/i.test(message)) {
    return "源运行的保存状态已经变化，请重新读取运行记录。";
  }
  return "任务状态已经变化，请重新读取后再创建分支。";
}
