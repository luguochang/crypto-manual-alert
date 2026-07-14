import { expect, test, type Page, type TestInfo } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";


test.skip(
  process.env.REAL_PRODUCT_E2E !== "1",
  "set REAL_PRODUCT_E2E=1 to run the real Product API chain",
);

test("real Product chain renders committed model analysis with a cited source", async ({ page }, testInfo) => {
  test.setTimeout(420_000);
  const consoleErrors: string[] = [];
  const failedResponses: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 500) {
      failedResponses.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/work");
  await page.getByLabel("分析问题").fill(
    "使用真实交易所行情和实时 Web Search 分析 BTC；宏观证据不足时必须返回 no_trade，所有事实必须引用来源。",
  );
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("分析完成", {
    timeout: 360_000,
  });
  await expect(page.getByTestId("analysis-result")).toBeVisible();
  await expect(page.getByText("暂不操作", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Risk" })).toBeVisible();
  const firstSource = page.getByTestId("analysis-result").locator(".source-list a").first();
  await expect(firstSource).toHaveAttribute("href", /^https:\/\//);
  await expect(firstSource).not.toContainText(/^来源 \d+$/);
  await expect(page.locator("pre")).toHaveCount(0);

  const layout = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    unnamedControls: Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"),
    ).filter((element) => {
      const name = element.getAttribute("aria-label") ?? element.textContent ?? "";
      return !name.trim();
    }).length,
  }));
  expect(layout.overflow).toBeLessThanOrEqual(0);
  expect(layout.unnamedControls).toBe(0);
  expect(consoleErrors).toEqual([]);
  expect(failedResponses).toEqual([]);

  await saveScreenshot(page, testInfo);
});

async function saveScreenshot(page: Page, testInfo: TestInfo) {
  const directory = path.resolve(process.cwd(), "artifacts", "playwright-real");
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, `real-product-success-${testInfo.project.name}.png`),
    fullPage: true,
  });
}
