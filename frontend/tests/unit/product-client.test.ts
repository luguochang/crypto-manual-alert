import { describe, expect, it, vi } from "vitest";

import { createAnalysis, getTask, listRuns } from "../../src/lib/api/product-client";

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
