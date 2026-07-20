import { describe, expect, it } from "vitest";

import {
  runWorkActionLabel,
  runWorkHref,
  isResolvedHistoricalReview,
  shouldOfferRunCancellation,
  shouldRevalidateRun,
  shouldShowRunFeedback,
} from "../../src/features/runs/run-detail-surface";
import {
  classifyRunCommandFailure,
  directRunCommandAvailability,
  resolveRunCommandRequest,
  workTaskHref,
} from "../../src/features/runs/run-command-actions";
import { ProductApiError } from "../../src/lib/api/product-client";
import type { RunDetail } from "../../src/lib/schemas/product-api";

describe("Run detail product state", () => {
  it.each(["queued", "running", "waiting_human"] as const)(
    "revalidates the active %s status",
    (status) => {
      expect(shouldRevalidateRun(runDetail(status, {
        pendingPauseStatus: status === "waiting_human" ? "pending" : undefined,
      }))).toBe(true);
    },
  );

  it.each(["succeeded", "blocked", "failed", "cancelled"] as const)(
    "does not poll the terminal %s status",
    (status) => {
      expect(shouldRevalidateRun(runDetail(status))).toBe(false);
    },
  );

  it("does not poll or offer cancellation for a resolved historical waiting Run", () => {
    const detail = runDetail("waiting_human", {
      currentTaskStatus: "succeeded",
      isCurrentRun: false,
    });

    expect(shouldRevalidateRun(detail)).toBe(false);
    expect(shouldOfferRunCancellation(detail)).toBe(false);
    expect(isResolvedHistoricalReview(detail)).toBe(true);
  });

  it.each(["queued", "running", "waiting_human", "failed", "cancelled"] as const)(
    "hides feedback for %s without a report",
    (status) => {
      expect(shouldShowRunFeedback(runDetail(status))).toBe(false);
    },
  );

  it.each(["succeeded", "blocked"] as const)(
    "shows feedback for a %s Run with a report",
    (status) => {
      expect(shouldShowRunFeedback(runDetail(status, { artifact: {} }))).toBe(true);
    },
  );

  it("keeps an existing feedback receipt visible regardless of Run status", () => {
    expect(shouldShowRunFeedback(runDetail("failed", { feedback: {} }))).toBe(true);
  });

  it("opens a waiting human review on the current task without historical Run selection", () => {
    const detail = runDetail("waiting_human", {
      taskId: "task/with space",
      runId: "run?version=1",
      pendingPauseStatus: "pending",
    });

    expect(runWorkHref(detail)).toBe("/work?task=task%2Fwith%20space");
  });

  it("keeps a resolved historical waiting Run selected in Work", () => {
    const detail = runDetail("waiting_human", {
      taskId: "task/with space",
      runId: "run?version=1",
      currentTaskStatus: "succeeded",
      isCurrentRun: false,
    });

    expect(runWorkHref(detail)).toBe("/work?task=task%2Fwith%20space");
    expect(runWorkActionLabel(detail)).toBe("查看任务最新状态");
  });

  it.each(["queued", "running", "succeeded", "blocked", "failed", "cancelled"] as const)(
    "builds an encoded historical Work selection for %s",
    (status) => {
      const detail = runDetail(status, {
        taskId: "task/with space",
        runId: "run?version=1",
      });

      expect(runWorkHref(detail)).toBe("/work?task=task%2Fwith%20space&run=run%3Fversion%3D1");
    },
  );

  it.each([
    ["waiting_human", "前往人工确认"],
    ["failed", "在工作台查看"],
    ["blocked", "在工作台查看"],
    ["running", "在工作台打开"],
    ["succeeded", "在工作台打开"],
  ] as const)("maps %s to a status-consistent Work action", (status, label) => {
    const detail = runDetail(status, {
      pendingPauseStatus: status === "waiting_human" ? "pending" : undefined,
    });
    expect(runWorkActionLabel(detail)).toBe(label);
  });

  it("describes an accepted waiting-human response as recovery progress", () => {
    expect(runWorkActionLabel(runDetail("waiting_human", {
      pendingPauseStatus: "responding",
    }))).toBe("查看确认进度");
  });

  it("offers direct Retry only for the current retryable Run and Fork for a stable source", () => {
    expect(directRunCommandAvailability(runDetail("failed"))).toEqual({
      retry: true,
      fork: true,
    });
    expect(directRunCommandAvailability(runDetail("succeeded"))).toEqual({
      retry: false,
      fork: true,
    });
    expect(directRunCommandAvailability(runDetail("failed", {
      currentTaskStatus: "running",
      isCurrentRun: false,
    }))).toEqual({
      retry: false,
      fork: false,
    });
    expect(directRunCommandAvailability(runDetail("cancelled"))).toEqual({
      retry: true,
      fork: false,
    });
  });

  it("reuses idempotency only for the same uncertain command and source context", () => {
    const first = resolveRunCommandRequest(null, "fork", "task-1:run-1", () => "key-1");
    const same = resolveRunCommandRequest(first, "fork", "task-1:run-1", () => "unused");
    const changedCommand = resolveRunCommandRequest(same, "retry", "task-1:run-1", () => "key-2");
    const changedRun = resolveRunCommandRequest(first, "fork", "task-1:run-2", () => "key-3");

    expect(same).toBe(first);
    expect(changedCommand.idempotencyKey).toBe("key-2");
    expect(changedRun.idempotencyKey).toBe("key-3");
  });

  it("keeps uncertain delivery retryable but refreshes stale command conflicts", () => {
    expect(classifyRunCommandFailure("fork", new Error("offline"))).toEqual({
      message: "网络连接中断，分支请求是否到达服务端尚未确认。",
      preserveRequestIdentity: true,
    });
    expect(classifyRunCommandFailure(
      "retry",
      new ProductApiError("temporary", 503),
    ).preserveRequestIdentity).toBe(true);
    expect(classifyRunCommandFailure(
      "fork",
      new ProductApiError("Source Run has no forkable checkpoint.", 409),
    )).toEqual({
      message: "该运行没有可用于创建分支的保存点。",
      preserveRequestIdentity: false,
    });
    expect(classifyRunCommandFailure(
      "retry",
      new ProductApiError("The latest terminal Run is not retryable.", 409),
    ).message).toBe("当前最新运行已不可重试，请重新读取任务状态。");
  });

  it("encodes the accepted command destination as the latest Task projection", () => {
    expect(workTaskHref("task/with space")).toBe("/work?task=task%2Fwith%20space");
  });
});

function runDetail(
  status: RunDetail["run"]["status"],
  options: {
    artifact?: object;
    feedback?: object;
    taskId?: string;
    runId?: string;
    pendingPauseStatus?: "pending" | "responding";
    currentTaskStatus?: RunDetail["task"]["status"];
    isCurrentRun?: boolean;
  } = {},
): RunDetail {
  return {
    run: {
      status,
      task_id: options.taskId ?? "task-id",
      run_id: options.runId ?? "run-id",
    },
    task: {
      status: options.currentTaskStatus ?? status,
      pending_interrupts: options.pendingPauseStatus
        ? { status: options.pendingPauseStatus }
        : null,
    },
    run_projection: {
      artifact: options.artifact ?? null,
    },
    is_current_run: options.isCurrentRun ?? true,
    feedback: options.feedback ?? null,
  } as unknown as RunDetail;
}
