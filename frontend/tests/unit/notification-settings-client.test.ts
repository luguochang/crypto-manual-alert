import { describe, expect, it, vi } from "vitest";

import {
  getNotificationSettings,
  updateNotificationSettings,
} from "../../src/lib/api/product-client";

const settingsView = {
  channel: "bark",
  enabled: false,
  configured: true,
  updated_at: "2026-07-16T08:30:00Z",
} as const;

describe("Notification settings Product client", () => {
  it("reads the exact no-store settings endpoint", async () => {
    const fetcher = vi.fn(async () => Response.json(settingsView));

    const settings = await getNotificationSettings(fetcher);

    expect(settings).toEqual(settingsView);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/settings/notifications",
      {
        method: "GET",
        headers: { accept: "application/json" },
        cache: "no-store",
      },
    );
  });

  it("sends only the strict replacement DTO and never expects the key back", async () => {
    const fetcher = vi.fn(async () => Response.json({
      ...settingsView,
      enabled: true,
    }));

    const settings = await updateNotificationSettings({
      enabled: true,
      device_key: "  bark-device-key-canary  ",
    }, fetcher);

    expect(settings).toEqual({ ...settingsView, enabled: true });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/product/api/v2/settings/notifications",
      expect.objectContaining({
        method: "PATCH",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          enabled: true,
          device_key: "bark-device-key-canary",
        }),
      }),
    );
    expect("device_key" in settings).toBe(false);
  });

  it("rejects a leaked key or malformed replacement before it crosses the client boundary", async () => {
    const leakingFetcher = vi.fn(async () => Response.json({
      ...settingsView,
      device_key: "leaked-device-key",
    }));
    await expect(getNotificationSettings(leakingFetcher)).rejects.toMatchObject({
      name: "ProductApiError",
      status: 502,
      message: "Product API returned invalid notification settings.",
    });

    const untouchedFetcher = vi.fn();
    await expect(updateNotificationSettings({
      enabled: true,
      device_key: "short",
    }, untouchedFetcher)).rejects.toThrow();
    expect(untouchedFetcher).not.toHaveBeenCalled();
  });

  it("preserves a safe upstream conflict detail for accessible form feedback", async () => {
    const fetcher = vi.fn(async () => Response.json({
      detail: "A Bark device key is required before notifications can be enabled.",
    }, { status: 409 }));

    await expect(updateNotificationSettings({ enabled: true }, fetcher)).rejects.toMatchObject({
      name: "ProductApiError",
      status: 409,
      message: "A Bark device key is required before notifications can be enabled.",
    });
  });
});
