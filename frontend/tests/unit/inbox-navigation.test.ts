import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/inbox",
}));

import { PrimaryNavigation } from "../../src/components/primary-navigation";

describe("Inbox primary navigation", () => {
  it("renders Inbox as an active navigable destination", () => {
    const markup = renderToStaticMarkup(createElement(PrimaryNavigation));
    const inboxLink = markup.match(/<a[^>]*href="\/inbox"[^>]*>/)?.[0];

    expect(inboxLink).toBeDefined();
    expect(inboxLink).toContain('aria-current="page"');
    expect(inboxLink).not.toContain("disabled");
  });
});
