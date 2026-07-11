import { expect, test } from "@playwright/test";
import type { APIRequestContext, Page, Route } from "@playwright/test";
import {
  attachRuntimeCollectors,
  expectBusinessPageNotJson,
  expectPageHealthy,
  expectPageHealthyNow,
  expectPageHealthyAtScrollPoints
} from "./audit-helpers";

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8010";

function manualRunSuccessPayload(traceId: string) {
  return {
    ok: true,
    data: {
      trace_id: traceId,
      plan: {
        plan_id: `${traceId}-plan`,
        instrument: "ETH-USDT-SWAP",
        main_action: "trigger long",
        horizon: "6h",
        manual_execution_required: true,
        expires_at: "2026-07-09T12:00:00+08:00",
        reference_price: 3500,
        entry_trigger: 3510,
        stop_price: 3435,
        target_1: 3580,
        target_2: 3660,
        probability: 0.58
      },
      verdict: {
        allowed: false,
        reasons: ["missing_execution_fact:order_book"],
        warnings: []
      }
    }
  };
}

function evalRunSuccessPayload(evalRunId: string) {
  return {
    ok: true,
    data: {
      eval_run_id: evalRunId,
      dataset_name: "failure_cases",
      mode: "cheap",
      status: "passed",
      started_at: "2026-07-09T00:00:00+00:00",
      ended_at: "2026-07-09T00:00:01+00:00",
      case_count: 0,
      pass_count: 0,
      fail_count: 0,
      metadata: {}
    }
  };
}

async function delayedJson(route: Route, payload: unknown, delayMs = 1_200) {
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload)
  });
}

async function createManualRun(request: APIRequestContext) {
  const response = await request.post(`${API_BASE_URL}/api/runs/manual`, {
    data: {
      symbol: "ETH-USDT-SWAP",
      query: "移动端详情深滚动回归：检查摘要、复盘、通知和复核状态。",
      horizon: "6h",
      alert_channel: "bark",
      position: { side: "unknown" },
      risk_mode: "normal"
    }
  });
  expect(response.ok(), "mobile deep-scroll seed response").toBeTruthy();
  const body = await response.json();
  const traceId = body?.data?.trace_id;
  expect(traceId, "mobile deep-scroll trace id").toBeTruthy();
  return String(traceId);
}

async function assertManualSubmitIsInProgress(page: Page) {
  const submitButton = page.getByRole("button", { name: "提交中" });
  await expect(submitButton).toBeVisible();
  await expect(submitButton).toBeDisabled();
  await expect(page.getByRole("status", { name: "提醒生成进度" })).toContainText(
    "正在生成提醒建议，请不要重复提交"
  );
}

async function assertEvalSubmitIsInProgress(page: Page) {
  const submitButton = page.getByRole("button", { name: "运行中..." });
  await expect(submitButton).toBeVisible();
  await expect(submitButton).toBeDisabled();
  await expect(page.getByRole("status", { name: "复盘运行进度" })).toContainText(
    "正在运行复盘，请不要重复提交"
  );
}

test.describe("async progress and mobile run-detail depth", () => {
  test("manual run and eval delayed responses keep visible progress and prevent duplicate submits", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);
    let manualPostCount = 0;
    let evalPostCount = 0;

    await page.route(`${API_BASE_URL}/api/runs/manual`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      manualPostCount += 1;
      await delayedJson(route, manualRunSuccessPayload("delayed-manual-trace"));
    });
    await page.route(`${API_BASE_URL}/api/eval/runs`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      evalPostCount += 1;
      await delayedJson(route, evalRunSuccessPayload("delayed-eval-run"));
    });

    await page.goto("/manual-run");
    await page.getByRole("button", { name: "生成提醒建议" }).click();
    await assertManualSubmitIsInProgress(page);
    await expectPageHealthyNow(page, testInfo, "manual-run-delayed-submit");
    await expect(page.getByRole("heading", { name: "本次提醒建议", exact: true })).toBeVisible();
    expect(manualPostCount, "manual delayed POST count").toBe(1);

    await page.goto("/eval?tab=runs");
    await page.getByRole("button", { name: "运行规则 eval" }).click();
    await assertEvalSubmitIsInProgress(page);
    await expectPageHealthyNow(page, testInfo, "eval-delayed-submit");
    await expect(page.getByText("Eval 已完成", { exact: false })).toBeVisible();
    expect(evalPostCount, "eval delayed POST count").toBe(1);

    await runtime.assertClean(testInfo);
  });

  test("mobile run detail deep-scroll keeps summary, review, notification, and status visible", async ({ page, request }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);
    const traceId = await createManualRun(request);

    await page.goto(`/runs/${encodeURIComponent(traceId)}`);
    await expect(page.getByRole("heading", { name: "提醒详情" })).toBeVisible();
    await expectBusinessPageNotJson(page, "提醒详情");
    await expect(page.getByLabel("提醒建议摘要")).toBeVisible();
    await expect(page.getByLabel("复核状态摘要")).toBeVisible();
    await expect(page.getByLabel("后续复盘")).toBeVisible();
    await expect(page.getByLabel("通知历史")).toBeVisible();
    await expectPageHealthyAtScrollPoints(page, testInfo, "mobile-run-detail-deep-scroll");

    await page.getByLabel("提醒建议摘要").scrollIntoViewIfNeeded();
    await expect(page.getByLabel("模型返回摘要")).toBeVisible();
    await expect(page.getByLabel("证据摘要")).toBeVisible();

    await page.getByLabel("复核状态摘要").scrollIntoViewIfNeeded();
    await expect(page.getByLabel("复核状态摘要").getByText(/人工复核|已阻断|证据链/)).toBeVisible();

    await page.getByLabel("后续复盘").scrollIntoViewIfNeeded();
    await expect(page.getByLabel("后续复盘").getByRole("heading", { name: "后续复盘" })).toBeVisible();
    await expect(page.getByLabel("后续复盘")).toContainText(/结果尚未生成|复盘状态已记录/);

    await page.getByLabel("通知历史").scrollIntoViewIfNeeded();
    await expect(page.getByLabel("通知历史").getByRole("heading", { name: "通知历史" })).toBeVisible();
    await expect(page.getByLabel("通知历史")).toContainText(/通知未启用|未记录|Bark 已发送|发送失败/);

    await runtime.assertClean(testInfo);
  });

  test("manual run can jump back to highlighted alert history entry", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);

    await page.goto("/manual-run");
    await page.getByLabel("交易对").fill("ETH-USDT-SWAP");
    await page.getByLabel("关注点").fill("记录页高亮刚生成的提醒，验证跨页面状态同步。");
    await page.getByRole("button", { name: "生成提醒建议" }).click();

    const resultPanel = page.getByRole("heading", { name: "本次提醒建议", exact: true }).locator("xpath=ancestor::*[self::section or self::article or self::div][1]");
    await expect(resultPanel).toBeVisible({ timeout: 30_000 });
    const detailHref = await resultPanel.getByRole("link", { name: "查看详情" }).getAttribute("href");
    const traceId = decodeURIComponent(detailHref?.split("?")[0].split("/").filter(Boolean).pop() ?? "");
    expect(traceId, "generated trace id").not.toEqual("");

    await expect(resultPanel.getByRole("link", { name: "查看记录" })).toHaveAttribute(
      "href",
      `/runs?latest=${encodeURIComponent(traceId)}`
    );
    await resultPanel.getByRole("link", { name: "查看记录" }).click();
    await expect(page).toHaveURL(new RegExp(`/runs\\?latest=${encodeURIComponent(traceId)}$`));
    await expect(page.getByLabel("刚生成的提醒")).toContainText("刚生成的提醒已显示在列表中");
    await expect(page.locator("[data-latest-run='true']")).toContainText("ETH-USDT-SWAP");
    await expectPageHealthy(page, testInfo, "runs-latest-highlight");

    await runtime.assertClean(testInfo);
  });
});
