import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  HomeMarketSource,
  marketSourceDisclosure,
} from "../../src/features/home/home-surface";

describe("Home market source disclosure", () => {
  it.each([
    [
      "exchange_native",
      {
        label: "交易所原生行情",
        tone: "is-available",
        warning: null,
      },
    ],
    [
      "web_search_verified",
      {
        label: "Web Search 已验证证据（降级）",
        tone: "is-partial",
        warning: "降级警示：交易所原生行情不可用；此快照来自带引用的 Web Search 市场证据，不等同于交易所原生行情。",
      },
    ],
    [
      "controlled_dependency",
      {
        label: "受控依赖（降级）",
        tone: "is-unavailable",
        warning: "降级警示：此快照来自受控依赖，不是交易所原生行情，不能视为交易所实时行情。",
      },
    ],
  ] as const)("maps %s to an honest Home disclosure", (sourceLevel, expected) => {
    expect(marketSourceDisclosure({ source_level: sourceLevel })).toEqual(expected);
  });

  it("renders the source level, fallback warning, and fetched time", () => {
    const fetchedAt = "2026-07-19T08:15:00Z";
    const html = renderToStaticMarkup(createElement(HomeMarketSource, {
      snapshot: {
        source_level: "web_search_verified",
        fetched_at: fetchedAt,
      },
    }));

    expect(html).toContain("来源等级：Web Search 已验证证据（降级）");
    expect(html).toContain("降级警示：交易所原生行情不可用");
    expect(html).toContain("不等同于交易所原生行情");
    expect(html).toContain("抓取时间");
    expect(html).toContain(`dateTime="${fetchedAt}"`);
    expect(html).not.toContain("历史真实行情快照");
  });

  it.each(["web_search_verified", "controlled_dependency"] as const)(
    "never calls %s an exchange-native price",
    (sourceLevel) => {
      const disclosure = marketSourceDisclosure({ source_level: sourceLevel });

      expect(disclosure.warning).toContain("交易所原生行情");
      expect(disclosure.warning).not.toContain("交易所真实行情");
      expect(disclosure.label).not.toBe("交易所原生行情");
    },
  );
});
