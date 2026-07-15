import { describe, expect, it } from "vitest";

import {
  classifyForkSubmissionFailure,
  forkContextKey,
  forkSourceOptions,
  isSameForkContext,
  resolveForkAcceptedTransition,
  resolveForkRequestIdentity,
  shouldOfferForkControl,
} from "../../src/features/work/fork-control";
import { isCurrentOperation } from "../../src/features/work/task-fork-panel";
import { ProductApiError } from "../../src/lib/api/product-client";
import type {
  ProductRunSummary,
  ProductTask,
} from "../../src/lib/schemas/product-api";

describe("historical Run fork control", () => {
  it("offers the control only for an explicit historical Run selection", () => {
    expect(shouldOfferForkControl(null)).toBe(false);
    expect(shouldOfferForkControl(sourceRunId)).toBe(true);
  });

  it("accepts only the selected owner-scoped Product Run list item", () => {
    const runs = [
      runSummary(sourceRunId, taskId, 1),
      runSummary("44444444-4444-4444-8444-444444444444", taskId, 2),
      runSummary("55555555-5555-4555-8555-555555555555", otherTaskId, 3),
    ];

    expect(forkSourceOptions(runs, taskId, sourceRunId)).toEqual([runs[0]]);
    expect(forkSourceOptions(runs, taskId, "66666666-6666-4666-8666-666666666666"))
      .toEqual([]);
    expect(forkSourceOptions(runs, taskId, null).map((run) => run.attempt))
      .toEqual([2, 1]);
  });

  it("keeps one idempotency identity only for an unchanged fork retry", () => {
    const first = resolveForkRequestIdentity(
      { source_run_id: sourceRunId },
      null,
      () => "fork-key-1",
    );
    const retry = resolveForkRequestIdentity(
      { source_run_id: sourceRunId },
      first,
      () => "must-not-be-used",
    );
    const changed = resolveForkRequestIdentity(
      { source_run_id: "44444444-4444-4444-8444-444444444444" },
      retry,
      () => "fork-key-2",
    );

    expect(retry).toBe(first);
    expect(retry.idempotencyKey).toBe("fork-key-1");
    expect(changed.idempotencyKey).toBe("fork-key-2");
  });

  it("switches an accepted historical fork to latest context and polling", () => {
    const requested = { taskId, selectedRunId: sourceRunId };
    const transition = resolveForkAcceptedTransition(
      requested,
      { ...requested },
      queuedTask(),
    );

    expect(transition).toMatchObject({
      selectedRunId: null,
      shouldPoll: true,
      task: { task_id: taskId, status: "queued" },
    });
    expect(resolveForkAcceptedTransition(
      requested,
      { taskId, selectedRunId: "44444444-4444-4444-8444-444444444444" },
      queuedTask(),
    )).toBeNull();
    expect(resolveForkAcceptedTransition(
      requested,
      requested,
      { ...queuedTask(), task_id: otherTaskId },
    )).toBeNull();
  });

  it("fences late operations after context, version, or mount changes", () => {
    const key = forkContextKey({ taskId, selectedRunId: sourceRunId });

    expect(isCurrentOperation(true, key, 4, key, 4)).toBe(true);
    expect(isCurrentOperation(false, key, 4, key, 4)).toBe(false);
    expect(isCurrentOperation(true, `${taskId}:latest`, 4, key, 4)).toBe(false);
    expect(isCurrentOperation(true, key, 5, key, 4)).toBe(false);
    expect(isSameForkContext(
      { taskId, selectedRunId: sourceRunId },
      { taskId, selectedRunId: sourceRunId },
    )).toBe(true);
  });

  it.each([408, 429, 500, 502, 503])(
    "preserves the fork identity for uncertain HTTP %s delivery",
    (status) => {
      expect(classifyForkSubmissionFailure(
        new ProductApiError("temporary", status),
      )).toMatchObject({
        phase: "network_error",
        preserveRequestIdentity: true,
        refreshContext: false,
      });
    },
  );

  it("maps permission, non-disclosure, conflict, and invalid request failures", () => {
    expect(classifyForkSubmissionFailure(
      new ProductApiError("forbidden", 403),
    )).toMatchObject({ phase: "permission_error", preserveRequestIdentity: false });
    expect(classifyForkSubmissionFailure(
      new ProductApiError("not found", 404),
    )).toMatchObject({ phase: "unavailable", refreshContext: false });
    expect(classifyForkSubmissionFailure(
      new ProductApiError("Source Run has no forkable checkpoint.", 409),
    )).toEqual({
      phase: "conflict",
      message: "该运行没有可用于创建分支的保存点。",
      preserveRequestIdentity: false,
      refreshContext: true,
    });
    expect(classifyForkSubmissionFailure(
      new ProductApiError("invalid", 422),
    )).toMatchObject({ phase: "invalid_request", refreshContext: true });
  });
});

const taskId = "22222222-2222-4222-8222-222222222222";
const otherTaskId = "33333333-3333-4333-8333-333333333333";
const sourceRunId = "11111111-1111-4111-8111-111111111111";

function runSummary(
  runId: string,
  runTaskId: string,
  attempt: number,
): ProductRunSummary {
  return {
    run_id: runId,
    task_id: runTaskId,
    attempt,
    status: "succeeded",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: `2026-07-1${attempt}T08:30:00Z`,
    finished_at: `2026-07-1${attempt}T08:35:00Z`,
    main_action: "no_trade",
  };
}

function queuedTask(): ProductTask {
  return {
    task_id: taskId,
    status: "queued",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    query_text: "Assess the next BTC move.",
    created_at: "2026-07-15T08:30:00Z",
    completed_at: null,
    cancel_requested_at: null,
    artifact: null,
    errors: [],
    agent_stream: null,
    market_snapshot: null,
    web_evidence: [],
    pending_interrupts: null,
  };
}
