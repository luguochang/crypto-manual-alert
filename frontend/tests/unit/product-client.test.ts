import { describe, expect, it, vi } from "vitest";

import {
  cancelRun,
  cancelTask,
  createAnalysis,
  createDeepResearch,
  forkTask,
  getHome,
  getRun,
  getTask,
  listArtifacts,
  listNotifications,
  listRuns,
  requestNotificationResend,
  respondAllInterrupts,
  respondInboxReview,
  retryTask,
  submitFeedback,
  setWatchlistSymbol,
} from "../../src/lib/api/product-client";

describe("Product API client", () => {
  it("submits each analysis with a one-time UUID idempotency key", async () => {
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("queued"), { status: 202 });
      },
    );
    const input = {
      symbol: "SOL-USDT-SWAP" as const,
      horizon: "1h",
      query_text: "Assess SOL risk.",
      notify: false,
    };

    const task = await createAnalysis(input, fetcher);
    await createAnalysis(input, fetcher);

    expect(task.status).toBe("queued");
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/product/api/v2/analysis");
    const firstHeaders = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    const secondHeaders = new Headers(fetcher.mock.calls[1]?.[1]?.headers);
    expect(firstHeaders.get("idempotency-key")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(secondHeaders.get("idempotency-key")).not.toBe(
      firstHeaders.get("idempotency-key"),
    );
  });

  it("allows a network retry to reuse the submission idempotency key", async () => {
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("queued"), { status: 202 });
      },
    );
    const input = {
      symbol: "SOL-USDT-SWAP" as const,
      horizon: "1h",
      query_text: "Assess SOL risk.",
      notify: false,
    };

    await createAnalysis(input, fetcher, "stable-network-retry-1");
    await createAnalysis(input, fetcher, "stable-network-retry-1");

    for (const [, init] of fetcher.mock.calls) {
      expect(new Headers(init?.headers).get("idempotency-key")).toBe(
        "stable-network-retry-1",
      );
    }
  });

  it("submits Deep Research through the dedicated Product admission endpoint", async () => {
    const fetcher = vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      void input;
      void init;
      return Response.json({
        ...taskProjection("queued"),
        task_type: "deep_research",
        artifact: null,
        deep_research_artifact: null,
      }, { status: 202 });
    });

    const task = await createDeepResearch(
      {
        task_type: "deep_research",
        symbol: "BTC-USDT-SWAP",
        horizon: "7d",
        query_text: "研究 BTC 机构采用趋势和主要反证。",
      },
      fetcher,
      "deep-research-network-retry-1",
    );

    expect(task.task_type).toBe("deep_research");
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "/api/product/api/v2/deep-research",
    );
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("idempotency-key"))
      .toBe("deep-research-network-retry-1");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({
      task_type: "deep_research",
      symbol: "BTC-USDT-SWAP",
      horizon: "7d",
      query_text: "研究 BTC 机构采用趋势和主要反证。",
    });
  });

  it("encodes task IDs and exposes readable HTTP failures", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ detail: "Product persistence is unavailable" }, { status: 503 }),
    );

    await expect(getTask("task/with spaces", fetcher)).rejects.toMatchObject({
      name: "ProductApiError",
      status: 503,
      message: "Product persistence is unavailable",
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/tasks/task%2Fwith%20spaces",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("preserves an explicit Run selection when reading Task history", async () => {
    const fetcher = vi.fn(async () => Response.json(taskProjection("failed")));
    const runId = "11111111-1111-4111-8111-111111111111";

    await getTask("22222222-2222-4222-8222-222222222222", fetcher, runId);

    expect(fetcher).toHaveBeenCalledWith(
      `/api/product/api/v2/tasks/22222222-2222-4222-8222-222222222222?run_id=${runId}`,
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
  });

  it("reads strict notification status and queues a single manual resend", async () => {
    const taskId = "22222222-2222-4222-8222-222222222222";
    const notification = notificationProjection();
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      return method === "POST"
        ? Response.json({
            ...notification,
            manual_resend_pending: true,
            manual_resend_available: false,
            manual_resend_requested_at: "2026-07-16T08:03:00Z",
          }, { status: 202 })
        : Response.json({ task_id: taskId, items: [notification] });
    });

    const list = await listNotifications(taskId, fetcher);
    const queued = await requestNotificationResend(
      notification.notification_id,
      { reason: "User confirmed a single retry." },
      fetcher,
    );

    expect(list.items[0]?.status).toBe("unknown");
    expect(queued.manual_resend_pending).toBe(true);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      `/api/product/api/v2/tasks/${taskId}/notifications`,
    );
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      `/api/product/api/v2/notifications/${notification.notification_id}/resend`,
    );
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({
      reason: "User confirmed a single retry.",
    });
  });

  it("submits cancellation through the Product command endpoint", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("running"), { status: 202 });
    });

    const task = await cancelTask(
      "22222222-2222-4222-8222-222222222222",
      fetcher,
      "cancel-network-retry-1",
    );

    expect(task.status).toBe("running");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/tasks/22222222-2222-4222-8222-222222222222/cancel",
      expect.objectContaining({ method: "POST" }),
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("cancel-network-retry-1");
  });

  it("submits selected Run cancellation through the Product command endpoint", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("running"), { status: 202 });
    });
    const runId = "11111111-1111-4111-8111-111111111111";

    const task = await cancelRun(runId, fetcher, "cancel-run-network-retry-1");

    expect(task.status).toBe("running");
    expect(fetcher).toHaveBeenCalledWith(
      `/api/product/api/v2/runs/${runId}/cancel`,
      expect.objectContaining({ method: "POST" }),
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("cancel-run-network-retry-1");
  });

  it("submits typed Run feedback with a stable idempotency key", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({
        feedback_id: "77777777-7777-4777-8777-777777777777",
        task_id: "22222222-2222-4222-8222-222222222222",
        run_id: "11111111-1111-4111-8111-111111111111",
        artifact_version_id: null,
        rating: "negative",
        comment: "Need more macro sources.",
        created_at: "2026-07-13T00:06:00Z",
        updated_at: "2026-07-13T00:06:00Z",
      }, { status: 201 });
    });

    const feedback = await submitFeedback(
      "11111111-1111-4111-8111-111111111111",
      { rating: "negative", comment: "Need more macro sources." },
      fetcher,
      "feedback-network-retry-1",
    );

    expect(feedback.rating).toBe("negative");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/runs/11111111-1111-4111-8111-111111111111/feedback",
      expect.objectContaining({ method: "POST" }),
    );
    const init = fetcher.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("idempotency-key")).toBe("feedback-network-retry-1");
    expect(JSON.parse(String(init?.body))).toEqual({
      rating: "negative",
      comment: "Need more macro sources.",
    });
  });

  it("submits retry through the Product command endpoint with stable idempotency", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("queued"), { status: 202 });
    });
    const task = await retryTask(
      "22222222-2222-4222-8222-222222222222",
      fetcher,
      "retry-network-retry-1",
    );

    expect(task.status).toBe("queued");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/tasks/22222222-2222-4222-8222-222222222222/retry",
      expect.objectContaining({ method: "POST" }),
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("retry-network-retry-1");
  });

  it("admits a fork with only the owner-scoped Product Run capability", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("queued"), { status: 202 });
    });
    const taskId = "22222222-2222-4222-8222-222222222222";
    const sourceRunId = "11111111-1111-4111-8111-111111111111";

    const task = await forkTask(
      taskId,
      { source_run_id: sourceRunId },
      fetcher,
      "fork-network-retry-1",
    );

    expect(task.status).toBe("queued");
    expect(fetcher).toHaveBeenCalledWith(
      `/api/product/api/v2/tasks/${taskId}/fork`,
      expect.objectContaining({ method: "POST" }),
    );
    const init = fetcher.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("fork-network-retry-1");
    expect(JSON.parse(String(init?.body))).toEqual({ source_run_id: sourceRunId });
  });

  it("rejects browser-owned fork coordinates before issuing a request", async () => {
    const fetcher = vi.fn();

    await expect(forkTask(
      "22222222-2222-4222-8222-222222222222",
      {
        source_run_id: "11111111-1111-4111-8111-111111111111",
        checkpoint_id: "checkpoint-1",
        checkpoint_namespace: "runtime/private",
      } as never,
      fetcher,
      "fork-1",
    )).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("submits two pause members in exactly one strict respond-all request", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("waiting_human"), { status: 202 });
    });
    const submission = {
      pause_id: "33333333-3333-4333-8333-333333333334",
      pause_version: 7,
      responses: [{
        interrupt_id: "interrupt:review-4",
        response_version: 4,
        response: {
          action: "edit" as const,
          comment: "Reduce the risk budget.",
          edits: {
            main_action: "open_long" as const,
            probability: 0.62,
            position_size_class: "light" as const,
            max_leverage: 2,
            risk_pct: 0.005,
            root_cause_chain: ["Momentum remains positive"],
            why_not_opposite: "Downside confirmation is incomplete.",
            invalidation: "A close below support invalidates the thesis.",
          },
        },
      }, {
        interrupt_id: "interrupt:compliance-2",
        response_version: 2,
        response: {
          action: "reject" as const,
          comment: "Required evidence is unavailable.",
          edits: null,
        },
      }],
    };

    await respondAllInterrupts(
      "22222222-2222-4222-8222-222222222222",
      submission,
      fetcher,
      "review-network-retry-4",
    );

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "/api/product/api/v2/tasks/22222222-2222-4222-8222-222222222222/interrupts/respond-all",
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("review-network-retry-4");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual(submission);
  });

  it("submits a Product-owned Inbox review without runtime projection coordinates", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({
        task_id: "22222222-2222-4222-8222-222222222222",
        pause_id: "33333333-3333-4333-8333-333333333334",
        pause_version: 7,
        status: "responding",
        responded_at: "2026-07-13T00:01:00Z",
      }, { status: 202 });
    });
    const input = {
      pause_version: 7,
      response: {
        action: "reject" as const,
        comment: "The evidence needs a narrower conclusion.",
      },
    };

    const receipt = await respondInboxReview(
      "33333333-3333-4333-8333-333333333334",
      input,
      fetcher,
      "inbox-review-network-retry-1",
    );

    expect(receipt.status).toBe("responding");
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "/api/product/api/v2/inbox/33333333-3333-4333-8333-333333333334/respond",
    );
    const init = fetcher.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("idempotency-key")).toBe(
      "inbox-review-network-retry-1",
    );
    expect(JSON.parse(String(init?.body))).toEqual(input);
    expect(JSON.stringify(input)).not.toContain("interrupt_id");
    expect(JSON.stringify(input)).not.toContain("response_version");
  });

  it("reuses the caller-owned idempotency key for an unchanged batch retry", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("waiting_human"), { status: 202 });
    });
    const submission = {
      pause_id: "33333333-3333-4333-8333-333333333334",
      pause_version: 7,
      responses: [{
        interrupt_id: "interrupt-review-4",
        response_version: 4,
        response: { action: "approve" as const, comment: null, edits: null },
      }],
    };

    await respondAllInterrupts(
      "22222222-2222-4222-8222-222222222222",
      submission,
      fetcher,
      "stable-batch-retry-4",
    );
    await respondAllInterrupts(
      "22222222-2222-4222-8222-222222222222",
      submission,
      fetcher,
      "stable-batch-retry-4",
    );

    for (const [, init] of fetcher.mock.calls) {
      expect(new Headers(init?.headers).get("idempotency-key")).toBe(
        "stable-batch-retry-4",
      );
    }
  });

  it("rejects malformed or coordinate-bearing batches before issuing a request", async () => {
    const fetcher = vi.fn();

    await expect(respondAllInterrupts(
      "22222222-2222-4222-8222-222222222222",
      {
        pause_id: "33333333-3333-4333-8333-333333333331",
        pause_version: 1,
        responses: [{
          interrupt_id: "interrupt-review-1",
          response_version: 1,
          namespace: "runtime/private",
          response: { action: "approve" },
        }],
      } as never,
      fetcher,
      "review-1",
    )).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("loads a bounded persisted Run list through the Product BFF", async () => {
    const fetcher = vi.fn(async () => Response.json({
      items: [{
        run_id: "11111111-1111-4111-8111-111111111111",
        task_id: "22222222-2222-4222-8222-222222222222",
        attempt: 1,
        status: "succeeded",
        symbol: "BTC-USDT-SWAP",
        horizon: "4h",
        created_at: "2026-07-13T08:30:00Z",
        finished_at: "2026-07-13T08:35:00Z",
        main_action: "no_trade",
      }],
      limit: 25,
    }));

    const runs = await listRuns(25, fetcher);

    expect(runs.items).toHaveLength(1);
    expect(runs.items[0]?.task_id).toBe("22222222-2222-4222-8222-222222222222");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/runs?limit=25",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
  });

  it("loads a typed historical Run detail and Artifact library through the Product BFF", async () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    const taskId = "22222222-2222-4222-8222-222222222222";
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes(`/runs/${runId}`)) {
        return Response.json({
          run: {
            run_id: runId,
            task_id: taskId,
            attempt: 1,
            status: "failed",
            symbol: "BTC-USDT-SWAP",
            horizon: "4h",
            created_at: "2026-07-13T08:30:00Z",
            finished_at: "2026-07-13T08:35:00Z",
            main_action: null,
          },
          task: {
            task_id: taskId,
            correlation_id: "33333333-3333-5333-8333-333333333333",
            status: "failed",
            symbol: "BTC-USDT-SWAP",
            horizon: "4h",
            created_at: "2026-07-13T08:30:00Z",
            artifact: null,
            errors: [],
            projection_scope: {
              mode: "latest",
              selected_run_id: null,
            },
          },
          run_projection: {
            task_id: taskId,
            correlation_id: "33333333-3333-5333-8333-333333333333",
            status: "failed",
            symbol: "BTC-USDT-SWAP",
            horizon: "4h",
            created_at: "2026-07-13T08:30:00Z",
            artifact: null,
            errors: [],
            projection_scope: {
              mode: "selected_run",
              selected_run_id: runId,
            },
          },
          is_current_run: true,
        });
      }
      return Response.json({
        items: [{
          artifact_id: "44444444-4444-4444-8444-444444444444",
          artifact_version_id: "55555555-5555-4555-8555-555555555555",
          artifact_type: "analysis_report",
          schema_version: "1.0",
          version_number: 1,
          status: "committed",
          task_id: taskId,
          run_id: runId,
          symbol: "BTC-USDT-SWAP",
          horizon: "4h",
          main_action: "no_trade",
          created_at: "2026-07-13T08:35:00Z",
        }],
        limit: 50,
      });
    });

    const detail = await getRun(runId, fetcher);
    const library = await listArtifacts(50, fetcher);

    expect(detail.run.run_id).toBe(runId);
    expect(detail.task.task_id).toBe(taskId);
    expect(library.items[0]?.artifact_type).toBe("analysis_report");
    expect(fetcher.mock.calls[0]?.[0]).toBe(`/api/product/api/v2/runs/${runId}`);
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/product/api/v2/artifacts?limit=50");
  });

  it("loads Home and updates the owner-scoped watchlist", async () => {
    const homeProjection = {
      watchlist: [{
        symbol: "BTC-USDT-SWAP",
        latest_snapshot: null,
        created_at: "2026-07-13T08:35:00Z",
      }],
      active_tasks: [],
      pending_inbox_count: 0,
      recent_reports: [],
    };
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      void _input;
      void _init;
      return Response.json(homeProjection);
    });

    const home = await getHome(fetcher);
    const updated = await setWatchlistSymbol("BTC-USDT-SWAP", false, fetcher);

    expect(home.watchlist[0]?.symbol).toBe("BTC-USDT-SWAP");
    expect(updated.pending_inbox_count).toBe(0);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/product/api/v2/home");
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "/api/product/api/v2/watchlist/BTC-USDT-SWAP",
    );
    expect(fetcher.mock.calls[1]?.[1]?.method).toBe("DELETE");
  });
});

function taskProjection(status: string) {
  const projection: Record<string, unknown> = {
    task_id: "task-client-1",
    correlation_id: "33333333-3333-5333-8333-333333333333",
    status,
    symbol: "SOL-USDT-SWAP",
    horizon: "1h",
    created_at: "2026-07-13T08:30:00Z",
    artifact: null,
    errors: [],
  };
  if (status === "waiting_human") {
    projection.pending_interrupts = respondingPauseProjection();
  }
  return projection;
}

function respondingPauseProjection() {
  return {
    pause_id: "33333333-3333-4333-8333-333333333334",
    pause_version: 7,
    status: "responding",
    expires_at: "2026-07-13T09:30:00Z",
    members: [{
      interrupt_id: "interrupt-review-response",
      response_version: 1,
      status: "responding",
      payload: {
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
            factor_scores: { market_structure: 1 },
            total_score: 1,
            main_action: "no_trade",
            instrument: "SOL-USDT-SWAP",
            horizon: "1h",
            reference_price: "150",
            entry_trigger: "151",
            stop_price: "145",
            target_1: "155",
            target_2: "160",
            probability: 0.55,
            position_size_class: "light",
            max_leverage: 1,
            risk_pct: "0.005",
            root_cause_chain: ["Awaiting confirmation"],
            why_not_opposite: "No directional confirmation.",
            invalidation: "Break of the observed range.",
            unavailable_data: [],
            manual_execution_required: true,
            expires_in_seconds: 3600,
          },
          evidence_verdict: {
            sufficient: true,
            confidence_cap: 0.6,
            missing_required: [],
            missing_optional: [],
            warnings: [],
          },
          risk_verdict: {
            allowed: true,
            blocked_reasons: [],
            warnings: [],
            confidence_cap: 0.6,
          },
          source_references: [],
        },
      },
      response: { action: "approve", comment: null, edits: null },
      responded_at: "2026-07-13T08:35:00Z",
    }],
  };
}

function notificationProjection() {
  return {
    notification_id: "77777777-7777-4777-8777-777777777777",
    task_id: "22222222-2222-4222-8222-222222222222",
    run_id: "33333333-3333-4333-8333-333333333333",
    artifact_id: "44444444-4444-4444-8444-444444444444",
    artifact_version_id: "55555555-5555-4555-8555-555555555555",
    decision_id: "66666666-6666-4666-8666-666666666666",
    decision_version: 1,
    channel: "bark",
    type: "analysis_completed",
    status: "unknown",
    attempt_count: 1,
    manual_resend_pending: false,
    manual_resend_available: true,
    manual_resend_requested_at: null,
    available_at: "2026-07-16T08:00:00Z",
    delivered_at: null,
    terminal_at: "2026-07-16T08:02:00Z",
    created_at: "2026-07-16T08:00:00Z",
    updated_at: "2026-07-16T08:02:00Z",
    attempts: [{
      attempt_id: "88888888-8888-4888-8888-888888888888",
      attempt_number: 1,
      trigger: "automatic",
      result: "unknown",
      reason: "delivery_outcome_uncertain",
      delay_seconds: 0,
      retry_after_seconds: null,
      cost_units: "0.000000",
      provider_receipt: null,
      error_code: "delivery_outcome_uncertain",
      created_at: "2026-07-16T08:01:00Z",
      finished_at: "2026-07-16T08:02:00Z",
    }],
  };
}
