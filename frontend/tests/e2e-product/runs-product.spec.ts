import { expect, test, type Page, type TestInfo } from "@playwright/test";
import axe from "axe-core";

const taskId = "22222222-2222-4222-8222-222222222222";
const runId = "11111111-1111-4111-8111-111111111111";

test("lists persisted analysis runs and opens the corresponding Run detail", async ({ page }, testInfo) => {
  await installRunsFixture(page);

  await page.goto("/runs");

  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.getByRole("heading", { name: "运行记录", exact: true, level: 1 })).toBeVisible();
  await expect(page.getByText("BTC", { exact: true })).toBeVisible();
  await expect(page.getByText("分析完成", { exact: true })).toBeVisible();
  await expect(page.getByText("暂不操作", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /BTC.*第 1 次运行.*分析完成/ })).toHaveAttribute(
    "href",
    `/runs/${runId}`,
  );

  await assertPageQuality(page, testInfo);
});

test("revalidates an active Run and exposes status-consistent actions", async ({ page }, testInfo) => {
  const requests = await installRunDetailFixture(page);

  await page.goto(`/runs/${runId}`);

  const runMetadata = page.getByLabel("运行元数据");
  await expect(runMetadata.getByRole("heading", { name: "分析中", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "这次结果对你有帮助吗？" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "在工作台打开" })).toHaveAttribute(
    "href",
    `/work?task=${taskId}&run=${runId}`,
  );
  await expect(runMetadata.getByRole("heading", { name: "分析失败", exact: true })).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByRole("link", { name: "在工作台重试或创建分支" })).toHaveAttribute(
    "href",
    `/work?task=${taskId}&run=${runId}`,
  );
  await expect(page.getByRole("button", { name: "取消本次运行" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "这次结果对你有帮助吗？" })).toHaveCount(0);
  expect(requests()).toBeGreaterThanOrEqual(2);

  await assertPageQuality(page, testInfo);
});

test("renders a resolved historical review without stale actions or polling", async ({ page }, testInfo) => {
  let requests = 0;
  await page.route(`**/api/product/api/v2/runs/${runId}`, async (route) => {
    requests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(resolvedHistoricalReviewFixture()),
    });
  });

  await page.goto(`/runs/${runId}`);

  const runMetadata = page.getByLabel("运行元数据");
  await expect(runMetadata.getByRole("heading", { name: "等待人工确认", exact: true })).toBeVisible();
  await expect(page.getByText("该次人工确认已由后续运行处理。", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看任务最新状态" })).toHaveAttribute(
    "href",
    `/work?task=${taskId}`,
  );
  await expect(page.getByRole("button", { name: "取消本次运行" })).toHaveCount(0);
  await page.waitForTimeout(5_500);
  expect(requests).toBe(1);

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

async function installRunDetailFixture(page: Page) {
  let requests = 0;
  await page.route(`**/api/product/api/v2/runs/${runId}`, async (route) => {
    requests += 1;
    const status = requests === 1 ? "running" : "failed";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(runDetailFixture(status)),
    });
  });
  return () => requests;
}

function runDetailFixture(status: "running" | "failed") {
  const now = new Date().toISOString();
  const correlationId = "33333333-3333-4333-8333-333333333333";
  return {
    run: {
      run_id: runId,
      task_id: taskId,
      attempt: 1,
      status,
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      created_at: now,
      finished_at: status === "failed" ? now : null,
      main_action: null,
    },
    task: {
      task_id: taskId,
      correlation_id: correlationId,
      status,
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      query_text: "评估 BTC 当前方向与风险边界",
      created_at: now,
      completed_at: status === "failed" ? now : null,
      cancel_requested_at: null,
      artifact: null,
      errors: [],
      completion_scope: {
        analysis: status === "failed" ? "failed" : "pending",
        notification: "not_requested",
        observability: "not_enabled",
      },
      warnings: [],
      agent_stream: null,
      stage_history: null,
      market_snapshot: null,
      web_evidence: [],
      pending_interrupts: null,
      projection_scope: {
        mode: "latest",
        selected_run_id: null,
      },
    },
    run_projection: {
      task_id: taskId,
      correlation_id: correlationId,
      status,
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      query_text: "评估 BTC 当前方向与风险边界",
      created_at: now,
      completed_at: status === "failed" ? now : null,
      cancel_requested_at: null,
      artifact: null,
      errors: [],
      completion_scope: {
        analysis: status === "failed" ? "failed" : "pending",
        notification: "not_requested",
        observability: "not_enabled",
      },
      warnings: [],
      agent_stream: null,
      stage_history: null,
      market_snapshot: null,
      web_evidence: [],
      pending_interrupts: null,
      projection_scope: {
        mode: "selected_run",
        selected_run_id: runId,
      },
    },
    is_current_run: true,
    feedback: null,
  };
}

function resolvedHistoricalReviewFixture() {
  const now = new Date().toISOString();
  const correlationId = "33333333-3333-4333-8333-333333333333";
  const task = {
    task_id: taskId,
    correlation_id: correlationId,
    status: "failed",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    query_text: "评估 BTC 当前方向与风险边界",
    created_at: now,
    completed_at: now,
    cancel_requested_at: null,
    artifact: null,
    errors: [],
    completion_scope: {
      analysis: "failed",
      notification: "not_requested",
      observability: "not_enabled",
    },
    warnings: [],
    agent_stream: null,
    stage_history: null,
    market_snapshot: null,
    web_evidence: [],
    pending_interrupts: null,
  };
  return {
    run: {
      run_id: runId,
      task_id: taskId,
      attempt: 1,
      status: "waiting_human",
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      created_at: now,
      finished_at: null,
      main_action: null,
    },
    task: {
      ...task,
      projection_scope: { mode: "latest", selected_run_id: null },
    },
    run_projection: {
      ...task,
      status: "waiting_human",
      completed_at: null,
      completion_scope: {
        ...task.completion_scope,
        analysis: "pending",
      },
      projection_scope: { mode: "selected_run", selected_run_id: runId },
    },
    is_current_run: false,
    feedback: null,
  };
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
