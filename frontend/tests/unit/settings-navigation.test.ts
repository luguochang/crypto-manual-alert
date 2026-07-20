import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
}));

import { PrimaryNavigation } from "../../src/components/primary-navigation";

describe("Settings primary navigation", () => {
  it("renders Settings as an active navigable destination", () => {
    const markup = renderToStaticMarkup(createElement(PrimaryNavigation));
    const settingsLink = markup.match(/<a[^>]*href="\/settings"[^>]*>/)?.[0];

    expect(settingsLink).toBeDefined();
    expect(settingsLink).toContain('aria-current="page"');
    expect(settingsLink).not.toContain("disabled");
  });
});
