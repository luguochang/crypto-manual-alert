import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { proxyProductRequest } from "../../src/lib/api/product-proxy";

const settingsPath = ["api", "v2", "settings", "notifications"];

describe("Notification settings Product BFF allowlist", () => {
  it.each(["GET", "PATCH"])("allows the exact %s settings route", async (method) => {
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json({
          channel: "bark",
          enabled: false,
          configured: false,
          updated_at: null,
        });
      },
    );
    const body = method === "PATCH"
      ? JSON.stringify({ enabled: false, device_key: "bark-device-key" })
      : undefined;
    const response = await proxyProductRequest(
      new Request(
        "http://127.0.0.1:3101/api/product/api/v2/settings/notifications",
        {
          method,
          headers: body ? { "content-type": "application/json" } : undefined,
          body,
        },
      ),
      settingsPath,
      fetcher,
    );

    expect(response.status).toBe(200);
    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:8123/app/api/v2/settings/notifications",
      expect.objectContaining({ method, cache: "no-store" }),
    );
    if (method === "PATCH") {
      const init = fetcher.mock.calls[0]?.[1];
      expect(new TextDecoder().decode(init?.body as ArrayBuffer)).toBe(body);
    }
  });

  it.each([
    ["POST", ["api", "v2", "settings", "notifications"]],
    ["PUT", ["api", "v2", "settings", "notifications"]],
    ["GET", ["api", "v2", "settings", "notifications", "extra"]],
    ["GET", ["api", "v2", "settings", "notification"]],
    ["PATCH", ["api", "v2", "settings"]],
  ])("rejects an allowlist lookalike (%s %j)", async (method, path) => {
    const fetcher = vi.fn();
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/${path.join("/")}`, {
        method,
        body: method === "GET" ? undefined : "{}",
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
