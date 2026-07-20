import { afterEach, describe, expect, it, vi } from "vitest";

import { ProductApiError } from "../../src/lib/api/product-client";
import { artifactReviewPayloadSchema } from "../../src/lib/schemas/product-api";
import {
  buildRespondAllSubmission,
  classifyReviewSubmissionFailure,
  createEmptyReviewBatchState,
  hasUnsubmittedReviewDrafts,
  isReviewBatchComplete,
  reconcileReviewBatchState,
  recordReviewDecision,
  preservesAnalysisRequestIdentity,
  resolveAnalysisRequestIdentity,
  resolveTaskSelection,
  resolveReviewBatchRequestIdentity,
  reviewPauseFingerprint,
  shouldApplyProductTaskProjection,
  shouldAttachOfficialStream,
  shouldPollTask,
  startTerminalTaskRevalidation,
  taskCompletionWarning,
  taskPollRetryDelayMs,
} from "../../src/features/work/work-surface";
import type {
  AnalysisPendingInterrupt,
  InterruptResponse,
  PendingInterruptPause,
  ProductTask,
} from "../../src/lib/schemas/product-api";

describe("work surface aggregate review coordinator", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it.each([
    ["task", "11111111-1111-4111-8111-111111111111"],
    ["task_id", "22222222-2222-4222-8222-222222222222"],
  ] as const)("restores a task from the %s Work URL parameter", (key, taskId) => {
    expect(resolveTaskSelection(new URLSearchParams({ [key]: taskId }))).toEqual({
      taskId,
      runId: null,
    });
  });

  it.each(["queued", "running", "waiting_human"] as const)(
    "attaches the official stream only for a live %s Task",
    (status) => {
      const task = {
        status,
        cancel_requested_at: null,
      } as Pick<ProductTask, "status" | "cancel_requested_at">;

      expect(shouldAttachOfficialStream(task, false)).toBe(true);
      expect(shouldAttachOfficialStream(task, true)).toBe(false);
      expect(shouldAttachOfficialStream({
        ...task,
        cancel_requested_at: "2026-07-18T09:00:00Z",
      }, false)).toBe(false);
    },
  );

  it.each(["succeeded", "blocked", "failed", "cancelled"] as const)(
    "never attaches the official stream for a terminal %s Task",
    (status) => {
      expect(shouldAttachOfficialStream({
        status,
        cancel_requested_at: null,
      }, false)).toBe(false);
    },
  );

  it("does not attach the official stream without a Product Task", () => {
    expect(shouldAttachOfficialStream(null, false)).toBe(false);
  });

  it("does not poll a resolved waiting boundary selected from Run history", () => {
    const historical = {
      status: "waiting_human",
      pending_interrupts: null,
      projection_scope: {
        mode: "selected_run",
        selected_run_id: "11111111-1111-4111-8111-111111111111",
      },
    } as ProductTask;

    expect(shouldPollTask(historical)).toBe(false);
    expect(shouldPollTask({
      ...historical,
      projection_scope: { mode: "latest", selected_run_id: null },
    })).toBe(true);
  });

  it("backs off transient task reads without allowing an unbounded retry delay", () => {
    expect([1, 2, 3, 4, 5, 6].map(taskPollRetryDelayMs)).toEqual([
      1_000,
      2_000,
      4_000,
      8_000,
      10_000,
      10_000,
    ]);
    expect(taskPollRetryDelayMs(0)).toBe(1_000);
  });

  it("revalidates a terminal Task on a bounded low-frequency schedule", async () => {
    vi.useFakeTimers();
    const visibility = createVisibilityHarness(true);
    const revalidate = vi.fn().mockResolvedValue(true);

    startTerminalTaskRevalidation({
      delaysMs: [5_000, 15_000, 30_000],
      revalidate,
      environment: visibility.environment,
    });

    await vi.advanceTimersByTimeAsync(4_999);
    expect(revalidate).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(revalidate).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(15_000);
    expect(revalidate).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(30_000);
    expect(revalidate).toHaveBeenCalledTimes(3);

    await vi.advanceTimersByTimeAsync(300_000);
    expect(revalidate).toHaveBeenCalledTimes(3);
    expect(visibility.listenerCount()).toBe(0);
  });

  it("stops terminal Task revalidation as soon as authority is corrected", async () => {
    vi.useFakeTimers();
    const visibility = createVisibilityHarness(true);
    const revalidate = vi.fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false);

    startTerminalTaskRevalidation({
      delaysMs: [5_000, 15_000, 30_000],
      revalidate,
      environment: visibility.environment,
    });

    await vi.advanceTimersByTimeAsync(20_000);
    expect(revalidate).toHaveBeenCalledTimes(2);
    expect(visibility.listenerCount()).toBe(0);

    await vi.advanceTimersByTimeAsync(300_000);
    expect(revalidate).toHaveBeenCalledTimes(2);
  });

  it("defers a due terminal revalidation while hidden and resumes once visible", async () => {
    vi.useFakeTimers();
    const visibility = createVisibilityHarness(false);
    const revalidate = vi.fn().mockResolvedValue(true);
    const stop = startTerminalTaskRevalidation({
      delaysMs: [5_000, 15_000],
      revalidate,
      environment: visibility.environment,
    });

    await vi.advanceTimersByTimeAsync(5_000);
    expect(revalidate).not.toHaveBeenCalled();

    visibility.emit();
    expect(revalidate).not.toHaveBeenCalled();

    visibility.setVisible(true);
    visibility.emit();
    await Promise.resolve();
    expect(revalidate).toHaveBeenCalledTimes(1);

    visibility.setVisible(false);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(revalidate).toHaveBeenCalledTimes(1);

    stop();
    visibility.setVisible(true);
    visibility.emit();
    await vi.advanceTimersByTimeAsync(300_000);
    expect(revalidate).toHaveBeenCalledTimes(1);
    expect(visibility.listenerCount()).toBe(0);
  });

  it("does not schedule another terminal revalidation after stopping an in-flight request", async () => {
    vi.useFakeTimers();
    const visibility = createVisibilityHarness(true);
    let finishRequest: ((shouldContinue: boolean) => void) | undefined;
    const revalidate = vi.fn(() => new Promise<boolean>((resolve) => {
      finishRequest = resolve;
    }));
    const stop = startTerminalTaskRevalidation({
      delaysMs: [5_000, 15_000],
      revalidate,
      environment: visibility.environment,
    });

    await vi.advanceTimersByTimeAsync(5_000);
    expect(revalidate).toHaveBeenCalledTimes(1);

    stop();
    finishRequest?.(true);
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(300_000);

    expect(revalidate).toHaveBeenCalledTimes(1);
    expect(visibility.listenerCount()).toBe(0);
  });

  it("keeps a terminal Product projection authoritative over stale concurrent reads", () => {
    const succeeded = {
      task_id: "11111111-1111-4111-8111-111111111111",
      status: "succeeded",
    } as unknown as ProductTask;
    const staleResponding = {
      task_id: succeeded.task_id,
      status: "waiting_human",
    } as unknown as ProductTask;
    const enrichedSuccess = {
      ...succeeded,
      warnings: ["notification_delivery_retrying"],
    } as unknown as ProductTask;

    expect(shouldApplyProductTaskProjection(succeeded, staleResponding)).toBe(false);
    expect(shouldApplyProductTaskProjection(succeeded, enrichedSuccess)).toBe(true);
    expect(shouldApplyProductTaskProjection(staleResponding, succeeded)).toBe(true);
  });

  it("allows an intentional new Task projection to replace the current terminal Task", () => {
    const current = {
      task_id: "11111111-1111-4111-8111-111111111111",
      status: "succeeded",
    } as ProductTask;
    const next = {
      task_id: "22222222-2222-4222-8222-222222222222",
      status: "queued",
    } as ProductTask;

    expect(shouldApplyProductTaskProjection(current, next)).toBe(true);
  });

  it("applies a server-owned terminal conflict correction to the same Task", () => {
    const succeeded = {
      task_id: "11111111-1111-4111-8111-111111111111",
      status: "succeeded",
      errors: [],
    } as unknown as ProductTask;
    const correctedFailure = {
      ...succeeded,
      status: "failed",
      errors: [{ code: "terminal_projection_conflict" }],
    } as unknown as ProductTask;
    const unrelatedFailure = {
      ...correctedFailure,
      errors: [{ code: "provider_unavailable" }],
    } as unknown as ProductTask;

    expect(shouldApplyProductTaskProjection(succeeded, correctedFailure)).toBe(true);
    expect(shouldApplyProductTaskProjection(succeeded, unrelatedFailure)).toBe(false);
  });

  it("keeps notification retry visible after analysis succeeds", () => {
    const task = {
      warnings: ["notification_delivery_retrying"],
      completion_scope: { analysis: "complete", notification: "retrying" },
    } as unknown as ProductTask;

    expect(taskCompletionWarning(task)).toContain("通知发送失败");
  });

  it.each([
    ["pending", "运行记录同步仍在处理中"],
    ["degraded", "部分诊断记录未能同步；不影响本次分析结果"],
  ] as const)("surfaces observability %s without replacing the analysis result", (status, message) => {
    const task = {
      warnings: [],
      completion_scope: {
        analysis: "complete",
        notification: "not_requested",
        observability: status,
      },
    } as unknown as ProductTask;

    expect(taskCompletionWarning(task)).toContain(message);
    expect(taskCompletionWarning(task)).not.toContain("分析失败");
  });

  it("reuses analysis admission identity only for an unchanged uncertain retry", () => {
    const input = {
      symbol: "BTC-USDT-SWAP" as const,
      horizon: "4h",
      query_text: "Assess BTC risk.",
      notify: false,
    };
    const first = resolveAnalysisRequestIdentity(input, null, () => "analysis-key-1");
    const retry = resolveAnalysisRequestIdentity(
      structuredClone(input),
      first,
      () => "must-not-be-used",
    );
    const changed = resolveAnalysisRequestIdentity(
      { ...input, horizon: "1d" },
      retry,
      () => "analysis-key-2",
    );

    expect(retry).toBe(first);
    expect(retry.idempotencyKey).toBe("analysis-key-1");
    expect(changed.idempotencyKey).toBe("analysis-key-2");
  });

  it.each([408, 429, 500, 502, 503])(
    "preserves analysis identity when HTTP %s cannot prove non-admission",
    (status) => {
      expect(preservesAnalysisRequestIdentity(new ProductApiError("retry", status))).toBe(true);
    },
  );

  it("preserves analysis identity for transport failures and clears terminal HTTP failures", () => {
    expect(preservesAnalysisRequestIdentity(new TypeError("fetch failed"))).toBe(true);
    expect(preservesAnalysisRequestIdentity(new ProductApiError("invalid", 422))).toBe(false);
    expect(preservesAnalysisRequestIdentity(new ProductApiError("forbidden", 403))).toBe(false);
  });

  it("requires the exact two-member decision set before building one submission", () => {
    const pause = reviewPause();
    const initial = reconcileReviewBatchState(createEmptyReviewBatchState(), pause);
    const withFirst = recordReviewDecision(
      initial,
      pause,
      "interrupt-review-1",
      approveDecision,
    );

    expect(isReviewBatchComplete(pause, withFirst)).toBe(false);
    expect(() => buildRespondAllSubmission(pause, withFirst.drafts)).toThrow(
      "Every member of the active pause requires exactly one decision",
    );

    const complete = recordReviewDecision(
      withFirst,
      pause,
      "interrupt-review-2",
      rejectDecision,
    );
    expect(isReviewBatchComplete(pause, complete)).toBe(true);
    expect(buildRespondAllSubmission(pause, complete.drafts)).toEqual({
      pause_id: "33333333-3333-4333-8333-333333333331",
      pause_version: 5,
      responses: [{
        interrupt_id: "interrupt-review-1",
        response_version: 3,
        response: approveDecision,
      }, {
        interrupt_id: "interrupt-review-2",
        response_version: 8,
        response: rejectDecision,
      }],
    });
    expect(() => buildRespondAllSubmission(pause, {
      ...complete.drafts,
      "interrupt-not-in-pause": approveDecision,
    })).toThrow("Every member of the active pause requires exactly one decision");
  });

  it("keeps the idempotency key stable only for an identical full-batch retry", () => {
    const pause = reviewPause();
    const input = buildRespondAllSubmission(pause, {
      "interrupt-review-1": approveDecision,
      "interrupt-review-2": rejectDecision,
    });
    const first = resolveReviewBatchRequestIdentity(input, null, () => "batch-key-1");
    const retry = resolveReviewBatchRequestIdentity(
      structuredClone(input),
      first,
      () => "must-not-be-used",
    );
    const changed = structuredClone(input);
    changed.responses[1] = {
      ...changed.responses[1],
      response: approveDecision,
    };
    const changedIdentity = resolveReviewBatchRequestIdentity(
      changed,
      retry,
      () => "batch-key-2",
    );

    expect(retry).toBe(first);
    expect(retry.idempotencyKey).toBe("batch-key-1");
    expect(changedIdentity.idempotencyKey).toBe("batch-key-2");
    expect(changedIdentity.fingerprint).not.toBe(first.fingerprint);
  });

  it("preserves drafts across the same server projection and resets on new authority", () => {
    const pause = reviewPause();
    const initial = reconcileReviewBatchState(createEmptyReviewBatchState(), pause);
    const complete = recordReviewDecision(
      recordReviewDecision(initial, pause, "interrupt-review-1", approveDecision),
      pause,
      "interrupt-review-2",
      rejectDecision,
    );
    const submission = buildRespondAllSubmission(pause, complete.drafts);
    const retryRequest = resolveReviewBatchRequestIdentity(
      submission,
      null,
      () => "batch-key-1",
    );
    const networkErrorState = {
      ...complete,
      phase: "network_error" as const,
      failureMessage: "Connection reset",
      retryRequest,
    };
    const refreshed = structuredClone(pause);
    refreshed.members.reverse();

    expect(reviewPauseFingerprint(refreshed)).toBe(reviewPauseFingerprint(pause));
    expect(reconcileReviewBatchState(networkErrorState, refreshed)).toBe(
      networkErrorState,
    );

    const nextVersion = { ...pause, pause_version: pause.pause_version + 1 };
    expect(reconcileReviewBatchState(networkErrorState, nextVersion)).toEqual(
      createEmptyReviewBatchState(reviewPauseFingerprint(nextVersion)),
    );

    const responding = { ...pause, status: "responding" as const };
    expect(reconcileReviewBatchState(networkErrorState, responding)).toEqual(
      createEmptyReviewBatchState(reviewPauseFingerprint(responding)),
    );
  });

  it("protects only pending local drafts that have not reached the Product service", () => {
    const pause = reviewPause();
    const empty = reconcileReviewBatchState(createEmptyReviewBatchState(), pause);
    const drafted = recordReviewDecision(
      empty,
      pause,
      "interrupt-review-1",
      approveDecision,
    );

    expect(hasUnsubmittedReviewDrafts(pause, empty)).toBe(false);
    expect(hasUnsubmittedReviewDrafts(pause, drafted)).toBe(true);
    expect(hasUnsubmittedReviewDrafts({ ...pause, status: "responding" }, drafted)).toBe(false);
    expect(hasUnsubmittedReviewDrafts(null, drafted)).toBe(false);
  });

  it.each([408, 429, 500, 502, 503])(
    "retains retry identity only for recoverable HTTP %s failures",
    (status) => {
      expect(classifyReviewSubmissionFailure(
        new ProductApiError(`HTTP ${status}`, status),
      )).toMatchObject({
        phase: "network_error",
        preserveRequestIdentity: true,
        refreshTask: false,
      });
    },
  );

  it("retains retry identity for a transport failure with unknown delivery", () => {
    expect(classifyReviewSubmissionFailure(new TypeError("fetch failed"))).toEqual({
      phase: "network_error",
      message: "网络连接中断，本次整组响应尚未得到服务端确认。",
      preserveRequestIdentity: true,
      refreshTask: false,
    });
  });

  it.each([401, 403])(
    "turns HTTP %s into an explicit non-retryable authentication failure",
    (status) => {
      expect(classifyReviewSubmissionFailure(
        new ProductApiError("Authentication required", status),
      )).toEqual({
        phase: "auth_error",
        message: status === 401
          ? "登录状态已失效，请重新登录后再读取任务。"
          : "当前账号无权提交这组审核决定。",
        preserveRequestIdentity: false,
        refreshTask: false,
      });
    },
  );

  it.each([400, 404, 422])(
    "discards stale retry identity and refreshes authority after HTTP %s",
    (status) => {
      expect(classifyReviewSubmissionFailure(
        new ProductApiError("Request rejected", status),
      )).toMatchObject({
        phase: "invalid_request",
        preserveRequestIdentity: false,
        refreshTask: true,
      });
    },
  );

  it("classifies conflicts separately and refreshes the Product task", () => {
    expect(classifyReviewSubmissionFailure(
      new ProductApiError("Interrupt response window has expired", 409),
    )).toMatchObject({
      phase: "expired",
      preserveRequestIdentity: false,
      refreshTask: true,
    });
    expect(classifyReviewSubmissionFailure(
      new ProductApiError("Interrupt is stale", 409),
    )).toMatchObject({
      phase: "conflict",
      preserveRequestIdentity: false,
      refreshTask: true,
    });
  });
});

function createVisibilityHarness(initiallyVisible: boolean) {
  let visible = initiallyVisible;
  const listeners = new Set<() => void>();
  return {
    environment: {
      isVisible: () => visible,
      setTimer: (callback: () => void, delayMs: number) => setTimeout(callback, delayMs),
      clearTimer: (timer: ReturnType<typeof setTimeout>) => clearTimeout(timer),
      subscribeVisibility: (listener: () => void) => {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    },
    emit: () => {
      for (const listener of listeners) listener();
    },
    listenerCount: () => listeners.size,
    setVisible: (next: boolean) => {
      visible = next;
    },
  };
}

const approveDecision: InterruptResponse = {
  action: "approve",
  comment: null,
  edits: null,
};

const rejectDecision: InterruptResponse = {
  action: "reject",
  comment: "Evidence remains incomplete.",
  edits: null,
};

function reviewPause(): PendingInterruptPause {
  return {
    pause_id: "33333333-3333-4333-8333-333333333331",
    pause_version: 5,
    status: "pending",
    expires_at: "2026-07-15T10:05:00Z",
    members: [
      reviewMember("interrupt-review-1", 3),
      reviewMember("interrupt-review-2", 8),
    ],
  };
}

function reviewMember(
  interruptId: string,
  responseVersion: number,
): AnalysisPendingInterrupt {
  return {
    interrupt_id: interruptId,
    response_version: responseVersion,
    status: "pending",
    payload: structuredClone(analysisReviewPayload),
    response: null,
    responded_at: null,
  };
}

const analysisReviewPayload = artifactReviewPayloadSchema.parse({
  kind: "artifact_review",
  schema_version: "1.0",
  allowed_actions: ["approve", "reject", "edit"],
  review_iteration: 1,
  artifact: {
    artifact_type: "analysis_report",
    schema_version: "1.0",
    content_version: 1,
    status: "draft",
    analysis: {
      regime: "risk_on",
      factor_scores: { momentum: 1 },
      total_score: 1,
      main_action: "open_long",
      instrument: "BTC-USDT-SWAP",
      horizon: "4h",
      reference_price: 67_250,
      entry_trigger: 67_400,
      stop_price: 65_800,
      target_1: 68_800,
      target_2: 70_100,
      probability: 0.68,
      position_size_class: "light",
      max_leverage: 2,
      risk_pct: 0.01,
      root_cause_chain: ["Momentum improved"],
      why_not_opposite: "Short momentum lacks confirmation.",
      invalidation: "A close below support invalidates the setup.",
      unavailable_data: [],
      manual_execution_required: true,
      expires_in_seconds: 900,
    },
    evidence_verdict: {
      sufficient: true,
      confidence_cap: 0.8,
      missing_required: [],
      missing_optional: [],
      warnings: [],
    },
    risk_verdict: {
      allowed: true,
      blocked_reasons: [],
      warnings: [],
      confidence_cap: 0.8,
    },
    source_references: ["https://example.com/evidence"],
  },
});
