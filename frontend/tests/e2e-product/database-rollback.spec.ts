import { expect, test, type Page, type TestInfo } from "@playwright/test";
import axe from "axe-core";
import fs from "node:fs/promises";
import path from "node:path";

import {
  artifactLibrarySchema,
  notificationListSchema,
  productTaskSchema,
} from "../../src/lib/schemas/product-api";

const scenarioPath = "/api/product/api/v2/testing/failure-scenario";

test("rolls back a terminal projection and recovers through Product retry", async ({
  page,
  request,
}, testInfo) => {
  requireFailureInjectionProfile();
  test.setTimeout(240_000);
  const controlHeaders = {
    "X-Failure-Injection-Control-Token": process.env.FAILURE_INJECTION_CONTROL_TOKEN ?? "",
  };
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
  page.on("requestfailed", (failedRequest) => {
    failedRequests.push({
      method: failedRequest.method(),
      pathname: new URL(failedRequest.url()).pathname,
      error: failedRequest.failure()?.errorText ?? "unknown_request_failure",
    });
  });
  page.on("response", (response) => {
    if (response.status() >= 500) {
      failedResponses.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });

  const current = await request.get(scenarioPath, { headers: controlHeaders });
  expect(current.ok()).toBe(true);
  const currentSnapshot = await current.json() as { generation: string };
  const configured = await request.put(scenarioPath, {
    headers: controlHeaders,
    data: {
      scenario: "database_rollback",
      expected_generation: currentSnapshot.generation,
    },
  });
  expect(configured.ok()).toBe(true);
  let activeScenario = "database_rollback";
  let destinationEnabled = false;

  try {
    const enabledDestination = await request.patch(
      "/api/product/api/v2/settings/notifications",
      {
        data: {
          enabled: true,
          device_key: "database-rollback-device-key",
        },
      },
    );
    expect(enabledDestination.ok()).toBe(true);
    expect(await enabledDestination.json()).toMatchObject({
      channel: "bark",
      enabled: true,
      configured: true,
    });
    destinationEnabled = true;

    await page.goto("/work");
    await page.getByLabel("分析问题").fill(
      "验证终态事务回滚不得留下部分报告，并可通过产品重试完整恢复。",
    );
    const notificationToggle = page.getByRole("checkbox", {
      name: "完成后通知 Bark",
      exact: true,
    });
    await page.locator("label.notification-toggle").click({ timeout: 10_000 });
    await expect(notificationToggle).toBeChecked();
    await page.getByRole("button", { name: "开始分析" }).click({ timeout: 10_000 });

    const statusHeading = page.getByTestId("task-status").getByRole("heading");
    await expect(statusHeading).toHaveText("分析失败", { timeout: 120_000 });
    const failure = page.locator("section.failure-panel[role='alert']");
    await expect(failure).toContainText("最终结果暂时不可用");
    await expect(failure).toContainText("系统已回滚未完成的写入，没有留下部分报告");
    await expect(failure).toContainText("请点击“重新分析”重试");
    const diagnostics = failure.locator("details");
    await expect(diagnostics).toBeVisible();
    await expect(diagnostics).not.toHaveAttribute("open", "");
    await expect(diagnostics.locator("summary")).toHaveText("查看失败诊断");
    await expect(diagnostics.getByText("terminal_projection_unavailable", { exact: true })).toBeHidden();
    await expect(diagnostics.getByText("DatabaseOperationalError", { exact: true })).toBeHidden();
    await diagnostics.locator("summary").click();
    await expect(diagnostics).toHaveAttribute("open", "");
    await expect(diagnostics).toContainText("terminal_projection_unavailable");
    await expect(diagnostics).toContainText("DatabaseOperationalError");
    await expect(failure.getByRole("button", { name: "重新分析" })).toBeVisible();
    await expect(page.getByTestId("analysis-result")).toHaveCount(0);
    await expect(page.locator("pre")).toHaveCount(0);

    const taskId = new URL(page.url()).searchParams.get("task");
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i);
    const failedTaskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(failedTaskResponse.ok()).toBe(true);
    const failedTask = productTaskSchema.parse(await failedTaskResponse.json());
    expect(failedTask).toMatchObject({
      task_id: taskId,
      status: "failed",
      artifact: null,
      completion_scope: {
        analysis: "failed",
        notification: "not_started",
      },
      warnings: [],
    });
    expect(failedTask.errors).toHaveLength(1);
    expect(failedTask.errors[0]).toMatchObject({
      code: "terminal_projection_unavailable",
      error_type: "DatabaseOperationalError",
      retryable: true,
      attempt: 3,
    });
    const failedNotificationsResponse = await request.get(
      `/api/product/api/v2/tasks/${taskId}/notifications`,
    );
    expect(failedNotificationsResponse.ok()).toBe(true);
    expect(notificationListSchema.parse(await failedNotificationsResponse.json()).items)
      .toEqual([]);
    const emptyLibraryResponse = await request.get("/api/product/api/v2/artifacts?limit=100");
    expect(emptyLibraryResponse.ok()).toBe(true);
    expect(
      artifactLibrarySchema.parse(await emptyLibraryResponse.json()).items
        .some((item) => item.task_id === taskId),
    ).toBe(false);
    await diagnostics.locator("summary").click();
    await expect(diagnostics).not.toHaveAttribute("open", "");
    await assertProductSurfaceQuality(page);
    await saveScreenshot(page, testInfo, "failed");

    const beforeRecovery = await request.get(scenarioPath, { headers: controlHeaders });
    expect(beforeRecovery.ok()).toBe(true);
    const beforeRecoverySnapshot = await beforeRecovery.json() as {
      generation: string;
      scenario: string;
    };
    expect(beforeRecoverySnapshot.scenario).toBe("database_rollback");
    const recoveryScenario = await request.put(scenarioPath, {
      headers: controlHeaders,
      data: {
        scenario: "notification_failure",
        expected_generation: beforeRecoverySnapshot.generation,
      },
    });
    expect(recoveryScenario.ok()).toBe(true);
    activeScenario = "notification_failure";

    await failure.getByRole("button", { name: "重新分析" }).click({ timeout: 10_000 });
    await expect(statusHeading).toHaveText("分析完成", { timeout: 120_000 });
    await expect(page.getByTestId("analysis-result")).toBeVisible();
    await expect(page.getByTestId("completion-warning")).toContainText("交付未完成", {
      timeout: 30_000,
    });
    await expect(page.getByText("等待重试", { exact: true })).toBeVisible();
    await expect(page.getByText("Provider 已接收", { exact: true })).toHaveCount(0);
    await expect(page.locator("pre")).toHaveCount(0);

    const recoveredTaskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(recoveredTaskResponse.ok()).toBe(true);
    const recoveredTask = productTaskSchema.parse(await recoveredTaskResponse.json());
    expect(recoveredTask).toMatchObject({
      task_id: taskId,
      status: "succeeded",
      completion_scope: {
        analysis: "complete",
        notification: "retrying",
      },
      warnings: ["notification_delivery_retrying"],
    });
    expect(recoveredTask.artifact?.status).toBe("committed");
    expect(recoveredTask.artifact?.provenance).toMatchObject({
      market_provider: "controlled_dependency",
      search_provider: "controlled_dependency_test",
      model_provider: "controlled_dependency",
    });
    expect(recoveredTask.errors).toEqual([]);

    const recoveredNotificationsResponse = await request.get(
      `/api/product/api/v2/tasks/${taskId}/notifications`,
    );
    expect(recoveredNotificationsResponse.ok()).toBe(true);
    const recoveredNotifications = notificationListSchema.parse(
      await recoveredNotificationsResponse.json(),
    );
    expect(recoveredNotifications.items).toHaveLength(1);
    expect(recoveredNotifications.items[0]).toMatchObject({
      task_id: taskId,
      status: "failed_retryable",
      attempt_count: 1,
    });
    const recoveredLibraryResponse = await request.get(
      "/api/product/api/v2/artifacts?limit=100",
    );
    expect(recoveredLibraryResponse.ok()).toBe(true);
    expect(
      artifactLibrarySchema.parse(await recoveredLibraryResponse.json()).items
        .some((item) => item.task_id === taskId),
    ).toBe(true);

    await page.reload();
    await expect(statusHeading).toHaveText("分析完成", { timeout: 30_000 });
    await expect(page.getByTestId("analysis-result")).toBeVisible();
    await expect(page.getByTestId("completion-warning")).toContainText("交付未完成");
    await expect(page.getByText("等待重试", { exact: true })).toBeVisible();
    await assertProductSurfaceQuality(page);
    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
    expect(failedResponses).toEqual([]);
    expect(failedRequests.filter((item) => !isExpectedStreamAbort(item))).toEqual([]);
    await saveScreenshot(page, testInfo, "recovered");
  } finally {
    if (destinationEnabled) {
      const disabledDestination = await request.patch(
        "/api/product/api/v2/settings/notifications",
        { data: { enabled: false } },
      );
      expect(disabledDestination.ok()).toBe(true);
    }
    const latest = await request.get(scenarioPath, { headers: controlHeaders });
    expect(latest.ok()).toBe(true);
    const latestSnapshot = await latest.json() as {
      generation: string;
      scenario: string;
    };
    expect(latestSnapshot.scenario).toBe(activeScenario);
    const reset = await request.delete(scenarioPath, {
      headers: {
        ...controlHeaders,
        "X-Failure-Injection-Generation": latestSnapshot.generation,
      },
    });
    expect(reset.ok()).toBe(true);
  }
});

function requireFailureInjectionProfile() {
  if (
    process.env.V2_E2E_PROFILE !== "failure-injection"
    || process.env.FAILURE_INJECTION_ENABLED !== "1"
    || !process.env.FAILURE_INJECTION_CONTROL_TOKEN
  ) {
    throw new Error("database rollback E2E requires the explicit failure-injection profile");
  }
}

async function assertProductSurfaceQuality(page: Page) {
  await page.addScriptTag({ content: axe.source });
  const layout = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - window.innerWidth,
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
      const associatedLabel = (element as HTMLInputElement).labels?.[0]?.textContent ?? "";
      const name = element.getAttribute("aria-label")
        || labelledByText
        || associatedLabel
        || element.getAttribute("placeholder")
        || element.textContent
        || "";
      return !name.trim();
    }).length,
  }));
  const accessibility = await page.evaluate(async () => {
    const result = await (window as typeof window & {
      axe: { run: () => Promise<{ violations: Array<{ id: string }> }> };
    }).axe.run();
    return result.violations.map((violation) => violation.id);
  });
  expect(layout.overflow).toBeLessThanOrEqual(0);
  expect(layout.unnamedControls).toBe(0);
  expect(accessibility).toEqual([]);
}

function isExpectedStreamAbort(item: { method: string; pathname: string; error: string }) {
  return item.method === "POST"
    && /^\/api\/agent\/threads\/[0-9a-f-]{36}\/stream\/events$/i.test(item.pathname)
    && /(?:ERR_ABORTED|NS_BINDING_ABORTED)/i.test(item.error);
}

async function saveScreenshot(page: Page, testInfo: TestInfo, phase: string) {
  const directory = path.resolve(process.cwd(), "artifacts", "playwright-real");
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, `database-rollback-${phase}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}
