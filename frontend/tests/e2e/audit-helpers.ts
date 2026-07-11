import { expect, type Page, type TestInfo } from "@playwright/test";

type BrowserIssue = {
  selector: string;
  message: string;
  rect?: { x: number; y: number; width: number; height: number };
};

export function attachRuntimeCollectors(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const requestFailures: string[] = [];

  const withPageContext = (message: string, eventUrl?: string) => `${new Date().toISOString()} ${eventUrl || page.url()}: ${message}`;

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(withPageContext(message.text(), message.location().url));
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(withPageContext(error.message));
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure();
    const url = request.url();
    if (url.includes("/_next/webpack-hmr") || (url.includes("_rsc=") && failure?.errorText === "net::ERR_ABORTED")) {
      return;
    }
    requestFailures.push(withPageContext(`${request.method()} ${url}: ${failure?.errorText ?? "unknown"}`));
  });

  return {
    async assertClean(testInfo: TestInfo) {
      await attachList(testInfo, "console-errors", consoleErrors);
      await attachList(testInfo, "page-errors", pageErrors);
      await attachList(testInfo, "request-failures", requestFailures);
      expect(consoleErrors, "browser console errors").toEqual([]);
      expect(pageErrors, "browser page errors").toEqual([]);
      expect(requestFailures, "failed browser requests").toEqual([]);
    }
  };
}

export async function expectPageHealthy(page: Page, testInfo: TestInfo, label: string) {
  await page.waitForLoadState("networkidle");
  await expectPageHealthyNow(page, testInfo, label);
}

export async function expectPageHealthyNow(page: Page, testInfo: TestInfo, label: string) {
  const issues = await scanDomIssues(page);
  await testInfo.attach(`${label}-dom-audit.json`, {
    body: JSON.stringify(issues, null, 2),
    contentType: "application/json"
  });
  expect(issues, `${label} DOM/visual audit`).toEqual([]);
}

export async function expectPageHealthyAtScrollPoints(page: Page, testInfo: TestInfo, label: string) {
  await page.waitForLoadState("networkidle");
  const points = [
    { name: "top", ratio: 0 },
    { name: "middle", ratio: 0.5 },
    { name: "bottom", ratio: 1 }
  ];
  for (const point of points) {
    await page.evaluate((ratio) => {
      const maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      window.scrollTo(0, Math.round(maxY * ratio));
    }, point.ratio);
    await page.waitForTimeout(50);
    await expectPageHealthy(page, testInfo, `${label}-${point.name}`);
  }
}

export async function expectBusinessPageNotJson(page: Page, requiredText: string) {
  await expect(page.locator("main")).toBeVisible();
  await expect(page.locator("body > pre")).toHaveCount(0);
  await expect(page.locator("main pre")).toHaveCount(0);
  await expect(page.locator("main").getByText(requiredText, { exact: false }).first()).toBeVisible();
  const visibleText = await page.locator("body").evaluate((body) => {
    const clone = body.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("script, style").forEach((node) => node.remove());
    return (clone.innerText ?? clone.textContent ?? "").trim();
  });
  expect(visibleText, "business page must not render raw JSON").not.toMatch(/^\s*[\[{]/);
  expect(visibleText, "business page must not render API envelope").not.toMatch(/"ok"\s*:|"data"\s*:|"trace_id"\s*:|"error"\s*:/);
}

async function scanDomIssues(page: Page): Promise<BrowserIssue[]> {
  return page.evaluate(() => {
    const issues: BrowserIssue[] = [];
    const contains = (parent: Element, child: Element): boolean => parent !== child && parent.contains(child);
    const intersectionArea = (a: DOMRect, b: DOMRect): number => {
      const left = Math.max(a.left, b.left);
      const right = Math.min(a.right, b.right);
      const top = Math.max(a.top, b.top);
      const bottom = Math.min(a.bottom, b.bottom);
      return Math.max(0, right - left) * Math.max(0, bottom - top);
    };
    const isInViewport = (rect: DOMRect): boolean =>
      rect.right > 0 &&
      rect.bottom > 0 &&
      rect.left < window.innerWidth &&
      rect.top < window.innerHeight;
    const toRect = (rect: DOMRect) => ({
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    });
    const describeElement = (element: Element): string => {
      const id = element.id ? `#${element.id}` : "";
      const className = Array.from(element.classList).slice(0, 3).map((item) => `.${item}`).join("");
      const text = (element.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40);
      return `${element.tagName.toLowerCase()}${id}${className}${text ? ` "${text}"` : ""}`;
    };
    const viewportWidth = document.documentElement.clientWidth;
    const bodyOverflow = document.documentElement.scrollWidth - viewportWidth;
    if (bodyOverflow > 2) {
      issues.push({
        selector: "document",
        message: `body horizontal overflow ${bodyOverflow}px beyond viewport`
      });
    }

    const visibleElements = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return (
          rect.width > 0 &&
          rect.height > 0 &&
          style.visibility !== "hidden" &&
          style.display !== "none" &&
          Number(style.opacity) !== 0
        );
      });

    for (const element of visibleElements) {
      const rect = element.getBoundingClientRect();
      const selector = describeElement(element);
      const style = window.getComputedStyle(element);
      const isTableArea = Boolean(element.closest(".table-wrap, table"));
      const isCodeArea = Boolean(element.closest("pre, code, .code-box, .inline-code, .mono-cell"));
      const hasElementChildren = Array.from(element.children).some((child) => {
        const childStyle = window.getComputedStyle(child);
        return childStyle.display !== "contents" && child.getBoundingClientRect().width > 0 && child.getBoundingClientRect().height > 0;
      });

      if (!isTableArea && !isCodeArea && !hasElementChildren && element.scrollWidth - element.clientWidth > 3) {
        issues.push({ selector, message: "text/content horizontal overflow", rect: toRect(rect) });
      }

      if (
        (element.tagName === "BUTTON" || element.tagName === "A") &&
        element.getAttribute("aria-disabled") !== "true" &&
        style.pointerEvents !== "none" &&
        (rect.width < 32 || rect.height < 32)
      ) {
        issues.push({ selector, message: `click target too small (${Math.round(rect.width)}x${Math.round(rect.height)})`, rect: toRect(rect) });
      }
    }

    const candidates = visibleElements
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        if (!isInViewport(rect)) {
          return false;
        }
        if (rect.width < 24 || rect.height < 16) {
          return false;
        }
        if (element.closest(".table-wrap, table, svg, path, .sidebar")) {
          return false;
        }
        return ["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "LABEL", "H1", "H2", "H3"].includes(element.tagName);
      })
      .map((element) => ({ element, rect: element.getBoundingClientRect() }));

    for (let i = 0; i < candidates.length; i += 1) {
      for (let j = i + 1; j < candidates.length; j += 1) {
        const a = candidates[i];
        const b = candidates[j];
        if (!a || !b || contains(a.element, b.element) || contains(b.element, a.element)) {
          continue;
        }
        const area = intersectionArea(a.rect, b.rect);
        const minArea = Math.min(a.rect.width * a.rect.height, b.rect.width * b.rect.height);
        if (area > 32 && area / minArea > 0.35) {
          issues.push({
            selector: `${describeElement(a.element)} / ${describeElement(b.element)}`,
            message: "visible controls/text overlap",
            rect: toRect(a.rect)
          });
        }
      }
    }

    return issues.slice(0, 50);
  });
}

async function attachList(testInfo: TestInfo, name: string, values: string[]) {
  if (values.length === 0) {
    return;
  }
  await testInfo.attach(`${name}.txt`, {
    body: values.join("\n"),
    contentType: "text/plain"
  });
}
