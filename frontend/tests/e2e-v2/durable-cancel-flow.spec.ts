import { expect, test } from "@playwright/test";


test.skip(
  process.env.REAL_PRODUCT_E2E !== "1",
  "set REAL_PRODUCT_E2E=1 to run the real Product API chain",
);

test("durably cancels a live Product task without browser-side Run commands", async ({ page }) => {
  test.setTimeout(120_000);
  const requests: Array<{ method: string; pathname: string }> = [];
  const serverErrors: string[] = [];
  page.on("request", (request) => {
    requests.push({
      method: request.method().toUpperCase(),
      pathname: new URL(request.url()).pathname,
    });
  });
  page.on("response", (response) => {
    if (response.status() >= 500) {
      serverErrors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });

  await page.goto("/work");
  await page.getByLabel("分析问题").fill(
    "创建一项真实分析，然后由 Product durable command 取消。",
  );
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    "分析中",
    { timeout: 20_000 },
  );
  await expect(page.getByTestId("official-run-stream")).toBeVisible({
    timeout: 20_000,
  });
  const cancel = page.getByRole("button", { name: "取消分析" });
  await expect(cancel).toBeVisible();
  await cancel.click();
  await expect(
    page.getByRole("group", { name: "任务操作" })
      .getByRole("button", { name: "正在停止" }),
  ).toBeVisible();
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    "已取消",
    { timeout: 45_000 },
  );
  await expect(page.getByRole("button", { name: "取消分析" })).toHaveCount(0);
  await expect(page.getByTestId("official-run-stream")).toHaveCount(0);
  await expect(page.getByTestId("durable-run-progress")).toBeVisible();
  await expect(
    page.getByTestId("durable-run-progress").getByRole("heading", { name: "执行进度" }),
  ).toBeVisible();
  const terminalRequestBoundary = requests.length;
  await page.waitForTimeout(1_500);
  expect(
    requests.slice(terminalRequestBoundary).filter((request) =>
      request.pathname.startsWith("/api/agent/")),
  ).toEqual([]);

  const taskUrl = new URL(page.url());
  expect(taskUrl.pathname).toBe("/work");
  expect(taskUrl.searchParams.get("task")).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  );
  expect(
    requests.filter((request) =>
      request.method === "POST"
      && /^\/api\/product\/api\/v2\/tasks\/[0-9a-f-]{36}\/cancel$/i.test(
        request.pathname,
      )),
  ).toHaveLength(1);
  expect(
    requests.some((request) =>
      request.method === "GET"
      && /^\/api\/agent\/threads\/[0-9a-f-]{36}\/state$/i.test(request.pathname)),
  ).toBe(true);
  expect(
    requests.filter((request) =>
      request.method !== "GET"
      && /(?:^|\/)runs(?:\/|$)/.test(request.pathname)),
  ).toEqual([]);
  expect(serverErrors).toEqual([]);
  await expect(page.locator("pre")).toHaveCount(0);

  const horizontalOverflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(0);

  const reloadRequestBoundary = requests.length;
  await page.reload();
  await expect(page).toHaveURL(taskUrl.toString());
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    "已取消",
    { timeout: 15_000 },
  );
  await expect(page.getByTestId("official-run-stream")).toHaveCount(0);
  await expect(page.getByTestId("durable-run-progress")).toBeVisible();
  await page.waitForTimeout(1_500);
  expect(
    requests.slice(reloadRequestBoundary).filter((request) =>
      request.pathname.startsWith("/api/agent/")),
  ).toEqual([]);
});
