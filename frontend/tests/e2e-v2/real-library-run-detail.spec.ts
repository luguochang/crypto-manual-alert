import { expect, test } from "@playwright/test";
import axe from "axe-core";
import fs from "node:fs/promises";
import path from "node:path";

test.skip(
  process.env.REAL_LIBRARY_E2E !== "1",
  "set REAL_LIBRARY_E2E=1 to run the real Library and Run detail chain",
);

test("real persisted Library opens a readable Artifact version detail", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  const failedResponses: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 500) failedResponses.push(`${response.status()} ${response.url()}`);
  });

  await page.goto("/library");
  await expect(page.getByRole("heading", { name: "报告资料库", exact: true })).toBeVisible();
  const firstReport = page.locator(".runs-list .run-row").first();
  await expect(firstReport).toBeVisible();
  await expect(firstReport).toContainText("报告 v1");
  await expect(firstReport).not.toContainText("undefined");

  const href = await firstReport.getAttribute("href");
  expect(href).toMatch(/^\/artifacts\/[0-9a-f-]{36}\?version_number=1$/i);
  await firstReport.click();

  await expect(page).toHaveURL(/\/artifacts\/[0-9a-f-]{36}\?version_number=1$/i);
  await expect(page.getByRole("heading", { name: /分析报告$/, exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "版本历史", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "证据门禁", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "风险门禁", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "决策持久化记录", exact: true })).toBeVisible();
  await expect(page.locator("pre")).toHaveCount(0);
  await expect(page.locator("main")).not.toContainText(
    /Artifact ID|Task ID|Decision ID|Product API|owner scope/,
  );

  await page.addScriptTag({ content: axe.source });
  const audit = await page.evaluate(async () => {
    const result = await (window as typeof window & {
      axe: { run: () => Promise<{ violations: Array<{ id: string }> }> };
    }).axe.run();
    return {
      violations: result.violations.map((item) => item.id),
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      unnamedControls: Array.from(
        document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"),
      ).filter((element) => {
        const labelledBy = element.getAttribute("aria-labelledby") ?? "";
        const labelledText = labelledBy
          .split(/\s+/)
          .filter(Boolean)
          .map((id) => document.getElementById(id)?.textContent ?? "")
          .join(" ");
        const associatedLabel = (element as HTMLInputElement).labels?.[0]?.textContent ?? "";
        return ![
          element.getAttribute("aria-label"),
          labelledText,
          associatedLabel,
          element.getAttribute("placeholder"),
          element.textContent,
        ].some((name) => Boolean(name?.trim()));
      }).length,
    };
  });

  expect(audit.violations).toEqual([]);
  expect(audit.overflow).toBeLessThanOrEqual(0);
  expect(audit.unnamedControls).toBe(0);
  expect(consoleErrors).toEqual([]);
  expect(failedResponses).toEqual([]);

  const artifactDirectory = path.resolve(process.cwd(), "artifacts", "playwright-real");
  await fs.mkdir(artifactDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(artifactDirectory, `real-library-artifact-detail-${testInfo.project.name}.png`),
    fullPage: true,
  });
  await testInfo.attach("real-library-artifact-detail", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  const runLink = page.getByRole("link", { name: /打开对应运行/ });
  await expect(runLink).toBeVisible();
  const runHref = await runLink.getAttribute("href");
  expect(runHref).toMatch(/^\/runs\/[0-9a-f-]{36}$/i);
  await page.goto(runHref!);
  await expect(page.getByRole("heading", { name: "运行详情", exact: true })).toBeVisible();
  await expect(page.locator("main")).not.toContainText(/运行 ID|Product API|Product 持久投影/);
  await expect(page.getByRole("button", { name: "取消本次运行", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "这次结果对你有帮助吗？", exact: true })).toBeVisible();
  const feedbackButton = page.getByRole("button", { name: "有帮助", exact: true });
  if (await feedbackButton.count() > 0) {
    await page.getByLabel("补充说明（可选）").fill("真实历史报告反馈。");
    await feedbackButton.click();
    await expect(page.getByText("已记录", { exact: true })).toBeVisible();
    await expect(page.getByText(/反馈已关联到本次分析/)).toBeVisible();
  } else {
    await expect(page.getByText("已记录", { exact: true })).toBeVisible();
  }
});
