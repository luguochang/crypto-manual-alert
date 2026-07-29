import { expect, test, type Page, type TestInfo } from "@playwright/test";
import axe from "axe-core";
import fs from "node:fs/promises";
import path from "node:path";


test("real Product chain renders committed model analysis with a cited source", async ({ page }, testInfo) => {
  if (
    process.env.V2_E2E_PROFILE !== "real-provider"
    || process.env.REAL_PRODUCT_E2E !== "1"
  ) {
    throw new Error(
      "real-provider projects require V2_E2E_PROFILE=real-provider and REAL_PRODUCT_E2E=1",
    );
  }
  test.setTimeout(420_000);
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedResponses: string[] = [];
  const failedRequests: Array<{ method: string; pathname: string; error: string }> = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      method: request.method(),
      pathname: new URL(request.url()).pathname,
      error: request.failure()?.errorText ?? "unknown_request_failure",
    });
  });
  page.on("response", (response) => {
    const pathname = new URL(response.url()).pathname;
    if (
      response.status() >= 400
      && (pathname.startsWith("/api/product/") || pathname.startsWith("/api/agent/"))
    ) {
      failedResponses.push(`${response.status()} ${pathname}`);
    }
  });

  await page.goto("/work");
  await page.getByLabel("分析问题").fill(
    "使用真实交易所行情和实时 Web Search 分析 BTC；宏观证据不足时必须返回 no_trade，所有事实必须引用来源。",
  );
  await page.getByRole("button", { name: "开始分析" }).click();

  const statusHeading = page.getByTestId("task-status").getByRole("heading");
  await expect(statusHeading).toHaveText(
    /^(?:等待人工确认|分析完成|已被风险门禁阻断|分析失败|已取消)$/,
    {
      timeout: 360_000,
    },
  );
  if ((await statusHeading.innerText()).trim() === "等待人工确认") {
    await resolveHumanReview(page, testInfo);
  }
  await expect(statusHeading).toHaveText(/^(?:分析完成|已被风险门禁阻断|分析失败|已取消)$/, {
    timeout: 360_000,
  });
  const terminalStatus = (await statusHeading.innerText()).trim();
  let visibleFailure: string | null = null;
  if (terminalStatus === "分析失败") {
    const failure = page.locator("section.failure-panel[role='alert']");
    await expect(failure).toBeVisible();
    visibleFailure = (await failure.innerText()).replace(/\s+/g, " ").trim();
    await testInfo.attach("visible-product-failure", {
      body: visibleFailure,
      contentType: "text/plain",
    });
  } else if (terminalStatus === "已取消") {
    visibleFailure = "真实 Product 主流程在完成前被取消。";
  } else {
    const analysisResult = page.getByTestId("analysis-result");
    await expect(analysisResult).toBeVisible();
    if (terminalStatus === "已被风险门禁阻断") {
      visibleFailure = "真实 Product 主流程被风险门禁阻断，没有生成 committed 分析结果。";
      await expect(page.getByText("门禁阻断", { exact: true })).toBeVisible();
      await expect(page.getByText(/不可执行，也不代表已提交建议/)).toBeVisible();
      await expect(analysisResult).toHaveAttribute("data-actionable", "false");
    } else {
      await expect(analysisResult).toHaveAttribute("data-artifact-state", "committed");
      await expect(analysisResult).toHaveAttribute("data-actionable", "true");
      const matchedSources = analysisResult.locator(
        '.source-list li[data-evidence-matched="true"]',
      );
      expect(await matchedSources.count()).toBeGreaterThan(0);
      await expect(analysisResult.locator(
        '.source-list li[data-evidence-matched="false"]',
      )).toHaveCount(0);
    }
    await expect(page.getByRole("heading", { name: "证据门禁" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "风险门禁" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "数据溯源" })).toBeVisible();
    const modelAudit = page.getByLabel("模型调用审计");
    await expect(modelAudit).toBeVisible();
    await expect(modelAudit).toContainText("research-extraction-v1");
    await expect(modelAudit).toContainText("market-analysis-v2");
    const rationaleItems = page.locator(".rationale-list li");
    expect(await rationaleItems.count()).toBeGreaterThan(0);
    expect((await rationaleItems.allTextContents()).join(" ")).toMatch(/[\u3400-\u9fff]/);
    const firstSource = page.getByTestId("analysis-result").locator(".source-list a").first();
    await expect(firstSource).toHaveAttribute("href", /^https:\/\//);
    await expect(firstSource).not.toContainText(/^来源 \d+$/);
    const evidenceSummaries = await page.locator(".web-evidence-card .evidence-summary").allTextContents();
    expect(evidenceSummaries.length).toBeGreaterThan(0);
    if (evidenceSummaries.length > 1) {
      expect(new Set(evidenceSummaries.map((summary) => summary.trim())).size).toBeGreaterThan(1);
    }
    const fallbackNotice = page.getByText("市场来源说明", { exact: true });
    if (await fallbackNotice.count()) {
      await expect(fallbackNotice).toBeVisible();
      await expect(modelAudit).toContainText("web-market-extraction-v2");
      await expect(page.getByText(/不等同于交易所原生行情/)).toBeVisible();
      await expect(page.getByText("Web Search 引用证据", { exact: false }).first()).toBeVisible();
    } else {
      await expect(page.getByText("OKX", { exact: true }).first()).toBeVisible();
    }
  }
  await expect(page.locator("pre")).toHaveCount(0);

  await page.addScriptTag({ content: axe.source });
  const layout = await page.evaluate(() => ({
    overflow: Math.max(
      document.documentElement.scrollWidth,
      document.body.scrollWidth,
    ) - document.documentElement.clientWidth,
    evidenceCardOverflow: Array.from(
      document.querySelectorAll<HTMLElement>(".web-evidence-card"),
    ).map((card) => card.scrollWidth - card.clientWidth),
    clippedControls: Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"),
    ).filter((element) => {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      return rect.left < -0.5
        || rect.right > document.documentElement.clientWidth + 0.5;
    }).length,
    unnamedControls: Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"),
    ).filter((element) => {
        const labelledBy = element.getAttribute("aria-labelledby");
        const labelledByText = labelledBy
          ? labelledBy
              .split(/\s+/)
              .map((id) => document.getElementById(id)?.textContent ?? "")
              .join(" ")
          : "";
        const associatedLabel =
          (element as HTMLInputElement).labels?.[0]?.textContent ?? "";
        const name =
          element.getAttribute("aria-label") ||
          labelledByText ||
          associatedLabel ||
          element.getAttribute("placeholder") ||
          element.textContent ||
          "";
        return !name.trim();
      }).length,
  }));
  const accessibility = await page.evaluate(async () => {
    const audit = await (window as typeof window & {
      axe: { run: () => Promise<{ violations: Array<{ id: string }> }> };
    }).axe.run();
    return audit.violations.map((violation) => violation.id);
  });
  expect(layout.overflow).toBeLessThanOrEqual(0);
  expect(layout.evidenceCardOverflow.every((overflow) => overflow <= 1)).toBe(true);
  expect(layout.clippedControls).toBe(0);
  expect(layout.unnamedControls).toBe(0);
  expect(accessibility).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(failedRequests.filter((failure) => !isExpectedStreamAbort(failure))).toEqual([]);
  expect(failedResponses).toEqual([]);

  await saveScreenshot(page, testInfo, visibleFailure === null ? "success" : "failure");
  if (visibleFailure !== null) {
    throw new Error(`Real Product flow failed: ${visibleFailure}`);
  }
});

async function resolveHumanReview(page: Page, testInfo: TestInfo) {
  const panels = page.locator("section.hitl-review-panel");
  await expect(panels.first()).toBeVisible({ timeout: 30_000 });
  const panelCount = await panels.count();
  expect(panelCount).toBeGreaterThan(0);
  const decisions: Array<"approve" | "reject"> = [];

  for (let index = 0; index < panelCount; index += 1) {
    const panel = panels.nth(index);
    const approve = panel.getByRole("button", { name: /(?:^|：)批准$/ }).first();
    const canApprove = await approve.count() > 0 && await approve.isEnabled();
    const action = canApprove ? "approve" : "reject";
    const actionButton = canApprove
      ? approve
      : panel.getByRole("button", { name: /(?:^|：)拒绝$/ }).first();
    await expect(actionButton).toBeEnabled();
    await actionButton.click();

    const confirmation = panel.getByRole("button", {
      name: action === "approve"
        ? /(?:^|：)(?:确认批准|在本页选择批准)$/
        : /(?:^|：)(?:确认拒绝|在本页选择拒绝)$/,
    }).first();
    await expect(confirmation).toBeEnabled();
    await confirmation.click();
    decisions.push(action);
  }

  if (panelCount > 1) {
    const submitBatch = page.getByRole("button", {
      name: /^确认提交 \d+ 项决定$/,
    });
    await expect(submitBatch).toBeEnabled();
    await submitBatch.click();
  }

  await testInfo.attach("human-review-decisions", {
    body: decisions.join("\n"),
    contentType: "text/plain",
  });
}

function isExpectedStreamAbort(failure: { method: string; pathname: string; error: string }) {
  return failure.method === "POST"
    && /^\/api\/agent\/threads\/[0-9a-f-]{36}\/stream\/events$/i.test(failure.pathname)
    && /(?:ERR_ABORTED|NS_BINDING_ABORTED)/i.test(failure.error);
}

async function saveScreenshot(page: Page, testInfo: TestInfo, outcome: "success" | "failure") {
  const directory = path.resolve(process.cwd(), "artifacts", "playwright-real");
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, `real-product-${outcome}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}
