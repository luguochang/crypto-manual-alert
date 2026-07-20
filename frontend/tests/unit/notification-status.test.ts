import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  NotificationStatus,
  notificationProjectionFingerprint,
  notificationStatusLabel,
  shouldPollNotifications,
} from "../../src/features/notifications/notification-status";
import type { NotificationList } from "../../src/lib/schemas/product-api";

describe("notification status", () => {
  it("renders a stable pending state when notification was requested", () => {
    const html = renderToStaticMarkup(createElement(NotificationStatus, {
      taskId: "22222222-2222-4222-8222-222222222222",
      requested: true,
      taskStatus: "running",
    }));

    expect(html).toContain("通知");
    expect(html).toContain("读取通知状态");
    expect(html).toContain("刷新通知状态");
  });

  it("maps provider states and polls only non-terminal delivery", () => {
    expect(notificationStatusLabel("delivered")).toBe("Provider 已接收");
    expect(notificationStatusLabel("unknown")).toBe("结果待确认");
    expect(shouldPollNotifications(null)).toBe(false);
    expect(shouldPollNotifications({
      task_id: "22222222-2222-4222-8222-222222222222",
      items: [],
    }, "running", 0)).toBe(false);
    expect(shouldPollNotifications({
      task_id: "22222222-2222-4222-8222-222222222222",
      items: [],
    }, "succeeded", 0)).toBe(true);
    expect(shouldPollNotifications({
      task_id: "22222222-2222-4222-8222-222222222222",
      items: [],
    }, "succeeded", 20)).toBe(false);
    expect(shouldPollNotifications({
      task_id: "22222222-2222-4222-8222-222222222222",
      items: [{ status: "sending", manual_resend_pending: false }],
    } as NotificationList)).toBe(true);
    expect(shouldPollNotifications({
      task_id: "22222222-2222-4222-8222-222222222222",
      items: [{ status: "delivered", manual_resend_pending: false }],
    } as NotificationList)).toBe(false);
  });

  it("discovers a delayed outbox after refresh without local request state", () => {
    const emptyView = {
      task_id: "22222222-2222-4222-8222-222222222222",
      items: [],
    } satisfies NotificationList;

    expect(shouldPollNotifications(emptyView, "succeeded", 1)).toBe(true);
    expect(shouldPollNotifications(emptyView, "succeeded", 19)).toBe(true);
    expect(shouldPollNotifications(emptyView, "succeeded", 20)).toBe(false);
    expect(notificationProjectionFingerprint(emptyView)).toBe("[]");
  });
});
