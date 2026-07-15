import { describe, expect, it, vi } from "vitest";

import { listInbox } from "../../src/lib/api/product-client";

describe("Inbox Product client", () => {
  it("forwards a bounded status query and opaque pagination cursor", async () => {
    const fetcher = vi.fn(async () => Response.json({
      items: [],
      next_cursor: "next_page_cursor-2",
    }));

    const view = await listInbox({
      status: "resolved",
      limit: 250,
      cursor: "current_page_cursor-1",
    }, fetcher);

    expect(view.next_cursor).toBe("next_page_cursor-2");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/inbox?status=resolved&limit=100&cursor=current_page_cursor-1",
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
      }),
    );
  });

  it("defaults to the active Inbox and fails readably on an invalid projection", async () => {
    const fetcher = vi.fn(async () => Response.json({
      items: [{ status: "mystery" }],
      next_cursor: null,
    }));

    await expect(listInbox({}, fetcher)).rejects.toMatchObject({
      name: "ProductApiError",
      status: 502,
      message: "Product API returned an invalid Inbox view.",
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/inbox?status=active&limit=25",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("rejects malformed cursors before issuing a request", async () => {
    const fetcher = vi.fn();

    await expect(listInbox({ cursor: "cursor with spaces" }, fetcher)).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
