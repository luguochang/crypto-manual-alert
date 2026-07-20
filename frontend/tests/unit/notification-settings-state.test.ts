import { describe, expect, it } from "vitest";

import { ProductApiError } from "../../src/lib/api/product-client";
import {
  notificationSettingsErrorMessage,
  prepareNotificationSettingsUpdate,
} from "../../src/features/settings/notification-settings-state";

const configuredSettings = {
  channel: "bark",
  enabled: false,
  configured: true,
  updated_at: "2026-07-16T08:30:00Z",
} as const;

describe("Notification settings form state", () => {
  it("enables a configured destination without synthesizing or echoing its existing key", () => {
    expect(prepareNotificationSettingsUpdate(
      configuredSettings,
      true,
      "",
    )).toEqual({
      success: true,
      submission: { enabled: true },
      replacesDeviceKey: false,
    });
  });

  it("requires a key only when enabling an unconfigured destination", () => {
    const unconfigured = {
      ...configuredSettings,
      configured: false,
      updated_at: null,
    };

    expect(prepareNotificationSettingsUpdate(unconfigured, true, "")).toEqual({
      success: false,
      message: "启用 Bark 通知前，请输入设备 key。",
    });
    expect(prepareNotificationSettingsUpdate(
      unconfigured,
      false,
      "  replacement-device-key  ",
    )).toEqual({
      success: true,
      submission: {
        enabled: false,
        device_key: "replacement-device-key",
      },
      replacesDeviceKey: true,
    });
  });

  it("maps permission, rotation, and availability errors to actionable copy", () => {
    expect(notificationSettingsErrorMessage(
      new ProductApiError("forbidden", 403),
      "fallback",
    )).toBe("当前工作区没有修改通知设置的权限。");
    expect(notificationSettingsErrorMessage(
      new ProductApiError(
        "The Bark device key must be re-entered after key rotation.",
        409,
      ),
      "fallback",
    )).toBe("凭据加密密钥已轮换，请重新输入 Bark 设备 key 后再启用。");
    expect(notificationSettingsErrorMessage(
      new ProductApiError("unavailable", 503),
      "fallback",
    )).toBe("通知凭据服务暂时不可用，请稍后重试。");
  });
});
