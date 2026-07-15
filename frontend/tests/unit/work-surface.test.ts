import { describe, expect, it } from "vitest";

import { ProductApiError } from "../../src/lib/api/product-client";
import {
  buildRespondAllSubmission,
  classifyReviewSubmissionFailure,
  createEmptyReviewBatchState,
  hasUnsubmittedReviewDrafts,
  isReviewBatchComplete,
  reconcileReviewBatchState,
  recordReviewDecision,
  resolveReviewBatchRequestIdentity,
  reviewPauseFingerprint,
} from "../../src/features/work/work-surface";
import type {
  InterruptResponse,
  PendingInterrupt,
  PendingInterruptPause,
} from "../../src/lib/schemas/product-api";

describe("work surface aggregate review coordinator", () => {
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

function reviewMember(interruptId: string, responseVersion: number): PendingInterrupt {
  return {
    interrupt_id: interruptId,
    response_version: responseVersion,
    status: "pending",
    payload: {} as PendingInterrupt["payload"],
    response: null,
    responded_at: null,
  };
}
