import { expect, test, type Page, type TestInfo } from "@playwright/test";
import axe from "axe-core";

const taskId = "22222222-2222-4222-8222-222222222222";
const runId = "11111111-1111-4111-8111-111111111111";

test("lists persisted analysis runs and opens the corresponding Product task", async ({ page }, testInfo) => {
  await installRunsFixture(page);

  await page.goto("/runs");

  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.getByRole("heading", { name: "分析记录", exact: true, level: 1 })).toBeVisible();
  await expect(page.getByText("BTC", { exact: true })).toBeVisible();
  await expect(page.getByText("分析完成", { exact: true })).toBeVisible();
  await expect(page.getByText("暂不操作", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /BTC.*第 1 次运行.*分析完成/ })).toHaveAttribute(
    "href",
    `/work?task=${taskId}&run=${runId}`,
  );

  await assertPageQuality(page, testInfo);
});

async function installRunsFixture(page: Page) {
  await page.route("**/api/product/api/v2/runs?limit=25", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          run_id: runId,
          task_id: taskId,
          attempt: 1,
          status: "succeeded",
          symbol: "BTC-USDT-SWAP",
          horizon: "4h",
          created_at: new Date().toISOString(),
          finished_at: new Date().toISOString(),
          main_action: "no_trade",
        }],
        limit: 25,
      }),
    });
  });
}

async function assertPageQuality(page: Page, testInfo: TestInfo) {
  await page.addScriptTag({ content: axe.source });
  const audit = await page.evaluate(async () => {
    const runtime = (window as typeof window & {
      axe: { run: () => Promise<{ violations: Array<{ id: string }> }> };
    }).axe;
    const result = await runtime.run();
    return {
      violations: result.violations.map((item) => item.id),
      viewportOverflow: document.documentElement.scrollWidth - window.innerWidth,
      unnamedControls: Array.from(
        document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"),
      ).filter((element) => !(
        element.getAttribute("aria-label")
        ?? element.textContent
        ?? ""
      ).trim()).length,
    };
  });

  expect(audit.violations).toEqual([]);
  expect(audit.viewportOverflow).toBeLessThanOrEqual(0);
  expect(audit.unnamedControls).toBe(0);
  await testInfo.attach("runs-full-page", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
}
