import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { proxyProductRequest } from "../../src/lib/api/product-proxy";

describe("Inbox Product BFF allowlist", () => {
  it("allows only the exact GET Inbox route and preserves its query", async () => {
    const fetcher = vi.fn(async () => Response.json({ items: [], next_cursor: null }));
    const response = await proxyProductRequest(
      new Request(
        "http://127.0.0.1:3101/api/product/api/v2/inbox?status=active&limit=20&cursor=page_cursor-1",
      ),
      ["api", "v2", "inbox"],
      fetcher,
    );

    expect(response.status).toBe(200);
    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:8123/app/api/v2/inbox?status=active&limit=20&cursor=page_cursor-1",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
  });

  it.each([
    ["POST", ["api", "v2", "inbox"]],
    ["GET", ["api", "v2", "inbox", "extra"]],
    ["GET", ["api", "v2", "inboxes"]],
  ])("rejects an Inbox allowlist lookalike (%s %j)", async (method, path) => {
    const fetcher = vi.fn();
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/${path.join("/")}`, {
        method,
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
