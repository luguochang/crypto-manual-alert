import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { proxyProductRequest } from "../../src/lib/api/product-proxy";

const monitorId = "11111111-1111-4111-8111-111111111111";

describe("Monitor Product BFF routes", () => {
  it("allows only the exact list and trigger-history reads", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ items: [] });
    });
    const list = await proxyProductRequest(
      new Request("http://127.0.0.1:3001/api/product/api/v2/monitors?status=attention"),
      ["api", "v2", "monitors"],
      fetcher,
    );
    const triggers = await proxyProductRequest(
      new Request(`http://127.0.0.1:3001/api/product/api/v2/monitors/${monitorId}/triggers`),
      ["api", "v2", "monitors", monitorId, "triggers"],
      fetcher,
    );
    const rejected = await proxyProductRequest(
      new Request(`http://127.0.0.1:3001/api/product/api/v2/monitors/${monitorId}`),
      ["api", "v2", "monitors", monitorId],
      fetcher,
    );

    expect(list.status).toBe(200);
    expect(triggers.status).toBe(200);
    expect(rejected.status).toBe(404);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8123/app/api/v2/monitors?status=attention",
    );
  });

  it.each([
    ["POST", ["api", "v2", "monitors"], "create-monitor-1"],
    ["POST", ["api", "v2", "monitors", monitorId, "pause"], "pause-monitor-3"],
    ["POST", ["api", "v2", "monitors", monitorId, "resume"], "resume-monitor-3"],
    ["POST", ["api", "v2", "monitors", monitorId, "trigger"], "trigger-monitor-3"],
    ["DELETE", ["api", "v2", "monitors", monitorId], "delete-monitor-3"],
  ])("forwards idempotency for %s %s", async (method, path, key) => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ accepted: true }, { status: 202 });
    });
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3001/api/product/${path.join("/")}`, {
        method,
        headers: {
          "content-type": "application/json",
          "idempotency-key": key,
        },
        body: method === "POST" && path.at(-1) === "trigger" ? undefined : "{}",
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("idempotency-key")).toBe(key);
  });

  it("rejects unknown monitor actions", async () => {
    const fetcher = vi.fn(async () => Response.json({ accepted: true }));
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3001/api/product/api/v2/monitors/${monitorId}/replace`, {
        method: "POST",
      }),
      ["api", "v2", "monitors", monitorId, "replace"],
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
