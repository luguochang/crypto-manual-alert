import { ProductApiError } from "@/lib/api/product-client";
import {
  notificationSettingsUpdateSchema,
  type NotificationSettings,
  type NotificationSettingsUpdate,
} from "@/lib/schemas/product-api";

type PreparedNotificationSettingsUpdate =
  | { success: true; submission: NotificationSettingsUpdate; replacesDeviceKey: boolean }
  | { success: false; message: string };

export function prepareNotificationSettingsUpdate(
  current: NotificationSettings,
  enabled: boolean,
  deviceKey: string,
): PreparedNotificationSettingsUpdate {
  const normalizedDeviceKey = deviceKey.trim();
  if (enabled && !current.configured && !normalizedDeviceKey) {
    return {
      success: false,
      message: "启用 Bark 通知前，请输入设备 key。",
    };
  }

  const parsed = notificationSettingsUpdateSchema.safeParse({
    enabled,
    ...(normalizedDeviceKey ? { device_key: normalizedDeviceKey } : {}),
  });
  if (!parsed.success) {
    return {
      success: false,
      message: normalizedDeviceKey.length > 255
        ? "设备 key 不能超过 255 个字符。"
        : "设备 key 至少需要 8 个字符。",
    };
  }
  return {
    success: true,
    submission: parsed.data,
    replacesDeviceKey: normalizedDeviceKey.length > 0,
  };
}

export function notificationSettingsErrorMessage(
  reason: unknown,
  fallback: string,
): string {
  if (!(reason instanceof ProductApiError)) return fallback;
  if (reason.status === 401) return "登录状态已失效，请重新登录后重试。";
  if (reason.status === 403) return "当前工作区没有修改通知设置的权限。";
  if (reason.status === 409) {
    if (reason.message.includes("key rotation")) {
      return "凭据加密密钥已轮换，请重新输入 Bark 设备 key 后再启用。";
    }
    return "启用 Bark 通知前，请输入设备 key。";
  }
  if (reason.status === 503) {
    return "通知凭据服务暂时不可用，请稍后重试。";
  }
  if (reason.status === 502) {
    return "通知设置服务返回了无效响应，请稍后重试。";
  }
  return reason.message || fallback;
}
