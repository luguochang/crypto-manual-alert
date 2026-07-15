import { describe, expect, it, vi } from "vitest";

import { resolveReviewRequestIdentity } from "../../src/features/work/human-review-panel";
import {
  cancelTask,
  createAnalysis,
  getTask,
  listRuns,
  respondInterrupt,
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

  it("submits a strict interrupt response with a caller-stable idempotency key", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("waiting_human"), { status: 202 });
    });
    const response = {
      response_version: 4,
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
    };

    await respondInterrupt(
      "22222222-2222-4222-8222-222222222222",
      "interrupt:review-4",
      response,
      fetcher,
      "review-network-retry-4",
    );
    await respondInterrupt(
      "22222222-2222-4222-8222-222222222222",
      "interrupt:review-4",
      response,
      fetcher,
      "review-network-retry-4",
    );

    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "/api/product/api/v2/tasks/22222222-2222-4222-8222-222222222222/interrupts/interrupt%3Areview-4/respond",
    );
    for (const [, init] of fetcher.mock.calls) {
      const headers = new Headers(init?.headers);
      expect(headers.get("content-type")).toBe("application/json");
      expect(headers.get("idempotency-key")).toBe("review-network-retry-4");
      expect(JSON.parse(String(init?.body))).toEqual(response);
    }
  });

  it("rejects malformed interrupt edits before issuing a request", async () => {
    const fetcher = vi.fn();

    await expect(respondInterrupt(
      "22222222-2222-4222-8222-222222222222",
      "interrupt-review-1",
      {
        response_version: 1,
        action: "edit",
        edits: { main_action: "open_long", raw_agent_state: true },
      } as never,
      fetcher,
      "review-1",
    )).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("reuses an interrupt idempotency key only for the same validated response", () => {
    const approve = {
      response_version: 4,
      action: "approve" as const,
      comment: null,
      edits: null,
    };
    const first = resolveReviewRequestIdentity(
      approve,
      null,
      () => "review-key-1",
    );
    const retry = resolveReviewRequestIdentity(
      approve,
      first,
      () => "must-not-be-used",
    );
    const changed = resolveReviewRequestIdentity(
      { ...approve, action: "reject" },
      retry,
      () => "review-key-2",
    );

    expect(retry).toBe(first);
    expect(retry.idempotencyKey).toBe("review-key-1");
    expect(changed.idempotencyKey).toBe("review-key-2");
    expect(changed.fingerprint).not.toBe(first.fingerprint);
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
});

function taskProjection(status: string) {
  return {
    task_id: "task-client-1",
    status,
    symbol: "SOL-USDT-SWAP",
    horizon: "1h",
    created_at: "2026-07-13T08:30:00Z",
    artifact: null,
    errors: [],
  };
}
