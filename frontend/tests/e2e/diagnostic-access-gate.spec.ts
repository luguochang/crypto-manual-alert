import { expect, test } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import {
  attachRuntimeCollectors,
  expectBusinessPageNotJson,
  expectPageHealthy
} from "./audit-helpers";

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8010";

async function createManualRun(request: APIRequestContext) {
  const response = await request.post(`${API_BASE_URL}/api/runs/manual`, {
    data: {
      symbol: "ETH-USDT-SWAP",
      query: "诊断入口关闭回归测试：普通用户不应误入工程视图。",
      horizon: "6h",
      alert_channel: "bark",
      position: { side: "unknown" },
      risk_mode: "normal"
    }
  });
  expect(response.ok(), "manual run seed response").toBeTruthy();
  const body = await response.json();
  const traceId = body?.data?.trace_id;
  expect(traceId, "manual run seed trace id").toBeTruthy();
  return String(traceId);
}

test.describe("diagnostic access gate", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_DIAGNOSTIC_DISABLED !== "true",
    "requires PLAYWRIGHT_LOCAL_STACK_FLAGS='--seed-mock-outcome --diagnostic-routes-disabled'",
  );

  test("diagnostic URLs show product recovery when diagnostic routes are disabled", async ({ page, request }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);
    const traceId = await createManualRun(request);

    await page.goto("/runs?columns=observability");
    await expect(page.getByRole("heading", { name: "诊断入口已关闭" })).toBeVisible();
    await expect(page.getByText("当前环境没有开放工程诊断入口", { exact: false })).toBeVisible();
    await expect(page.getByRole("link", { name: /返回提醒记录/ }).first()).toHaveAttribute("href", "/runs");
    await expect(page.getByRole("link", { name: /查看配置检查/ })).toHaveAttribute("href", "/config");
    await expect(page.locator("main")).not.toContainText(/工程诊断说明|Spans|LLM|原始数据|request_json|response_json/);
    await expectBusinessPageNotJson(page, "诊断入口已关闭");
    await expectPageHealthy(page, testInfo, "diagnostic-disabled-runs-observability");

    await page.goto(`/runs/${encodeURIComponent(traceId)}?columns=observability&tab=raw`);
    await expect(page.getByRole("heading", { name: "诊断入口已关闭" })).toBeVisible();
    await expect(page.getByRole("link", { name: /返回提醒详情/ }).first()).toHaveAttribute(
      "href",
      `/runs/${encodeURIComponent(traceId)}`
    );
    await expect(page.locator("main")).not.toContainText(/原始数据|LLM 交互|request_json|response_json|工程诊断摘要/);
    await expectBusinessPageNotJson(page, "诊断入口已关闭");
    await expectPageHealthy(page, testInfo, "diagnostic-disabled-run-detail-raw");

    await page.goto("/eval?tab=cases");
    await expect(page.getByRole("heading", { name: "诊断入口已关闭" })).toBeVisible();
    await expect(page.getByRole("link", { name: /返回质量复盘/ }).first()).toHaveAttribute("href", "/eval?tab=quality");
    await expect(page.locator("main")).not.toContainText(/工程复盘诊断|发起复盘|问题样本|Badcase IDs|judge_openai/i);
    await expectBusinessPageNotJson(page, "诊断入口已关闭");
    await expectPageHealthy(page, testInfo, "diagnostic-disabled-eval-cases");

    await page.goto("/eval/runs/playwright-financial-quality-gate");
    await expect(page.getByRole("heading", { name: "诊断入口已关闭" })).toBeVisible();
    await expect(page.getByRole("link", { name: /返回质量复盘/ }).first()).toHaveAttribute("href", "/eval?tab=quality");
    await expect(page.locator("main")).not.toContainText(/复盘批次详情|发布证据|回放输入摘要|Promotion Artifacts/i);
    await expectBusinessPageNotJson(page, "诊断入口已关闭");
    await expectPageHealthy(page, testInfo, "diagnostic-disabled-eval-run-detail");

    await runtime.assertClean(testInfo);
  });
});
