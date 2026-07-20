import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NotificationSettingsSurface } from "../../src/features/settings/notification-settings-surface";

describe("Notification settings surface", () => {
  it("announces the initial load without rendering any credential value", () => {
    const markup = renderToStaticMarkup(createElement(NotificationSettingsSurface));

    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain('aria-busy="true"');
    expect(markup).toContain("正在读取通知设置");
    expect(markup).not.toContain("device_key");
  });
});
