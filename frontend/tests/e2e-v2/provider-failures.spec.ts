import {
  expect,
  test,
  type APIRequestContext,
  type Page,
  type TestInfo,
} from "@playwright/test";
import axe from "axe-core";
import fs from "node:fs/promises";
import path from "node:path";

import {
  artifactLibrarySchema,
  notificationListSchema,
  productTaskSchema,
} from "../../src/lib/schemas/product-api";

const scenarioPath = "/api/product/api/v2/testing/failure-scenario";
const scenarios = [
  {
    id: "okx_unavailable",
    code: "provider_unavailable",
    provider: "okx",
    errorType: null,
    retryable: false,
  },
  {
    id: "okx_http_500",
    code: "provider_unavailable",
    provider: "okx",
    errorType: null,
    retryable: true,
  },
  {
    id: "okx_timeout",
    code: "provider_unavailable",
    provider: "okx",
    errorType: null,
    retryable: true,
  },
  {
    id: "search_unavailable",
    code: "research_unavailable",
    provider: "failure_injection",
    errorType: "InjectedSearchUnavailable",
    retryable: false,
  },
  {
    id: "model_invalid_output",
    code: "model_invalid_output",
    provider: null,
    errorType: "StructuredOutputValidationError",
    retryable: false,
  },
] as const;

for (const scenario of scenarios) {
  test(`renders ${scenario.id} without generic success`, async ({ page, request }, testInfo) => {
    requireFailureInjectionProfile();
    test.setTimeout(180_000);
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
        scenario: scenario.id,
        expected_generation: currentSnapshot.generation,
      },
    });
    expect(configured.ok()).toBe(true);
    const configuredSnapshot = await configured.json() as { scenario: string };
    expect(configuredSnapshot.scenario).toBe(scenario.id);

    try {
      await page.goto("/work");
      await page.getByLabel("分析问题").fill(
        `验证服务端 ${scenario.id} 故障必须返回可解释失败，不得生成成功分析。`,
      );
      await page.getByRole("button", { name: "开始分析" }).click();

      const statusHeading = page.getByTestId("task-status").getByRole("heading");
      await expect(statusHeading).toHaveText("分析失败", { timeout: 120_000 });
      const failure = page.locator("section.failure-panel[role='alert']");
      await expect(failure).toBeVisible();
      await expect(failure).toContainText(scenario.code);
      if (scenario.provider !== null) {
        await expect(failure).toContainText(scenario.provider);
      }
      if (scenario.errorType !== null) {
        await expect(failure).toContainText(scenario.errorType);
      }
      const retry = failure.getByRole("button", { name: "重新分析" });
      await expect(retry).toHaveCount(scenario.retryable ? 1 : 0);
      await expect(page.getByTestId("analysis-result")).toHaveCount(0);
      await expect(page.locator("pre")).toHaveCount(0);

      const taskId = new URL(page.url()).searchParams.get("task");
      expect(taskId).toMatch(/^[0-9a-f-]{36}$/i);
      const taskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
      expect(taskResponse.ok()).toBe(true);
      const task = productTaskSchema.parse(await taskResponse.json());
      expect(task.task_id).toBe(taskId);
      expect(task.status).toBe("failed");
      expect(task.artifact).toBeNull();
      expect(task.errors).toHaveLength(1);
      expect(task.errors[0]).toMatchObject({
        code: scenario.code,
        provider: scenario.provider,
        error_type: scenario.errorType,
        retryable: scenario.retryable,
        correlation_id: task.correlation_id,
      });

      if (scenario.id === "search_unavailable" || scenario.id === "model_invalid_output") {
        expect(task.market_snapshot?.symbol).toBe("BTC-USDT-SWAP");
        expect(task.market_snapshot?.source_level).toBe("controlled_dependency");
        if (scenario.id === "model_invalid_output") {
          expect(task.web_evidence).toHaveLength(1);
          expect(task.web_evidence[0]).toMatchObject({
            source: "controlled_dependency_test",
            parser_version: "controlled-dependency-v1",
            evidence_relation: "controlled_dependency",
          });
        } else {
          expect(task.web_evidence).toEqual([]);
        }
        const libraryResponse = await request.get("/api/product/api/v2/artifacts?limit=100");
        expect(libraryResponse.ok()).toBe(true);
        const library = artifactLibrarySchema.parse(await libraryResponse.json());
        expect(library.items.some((item) => item.task_id === taskId)).toBe(false);

        await page.reload();
        await expect(statusHeading).toHaveText("分析失败", { timeout: 30_000 });
        await expect(failure).toContainText(scenario.code);
        if (scenario.errorType !== null) {
          await expect(failure).toContainText(scenario.errorType);
        }
        await expect(page.getByTestId("analysis-result")).toHaveCount(0);
      }

      await assertProductSurfaceQuality(page);
      expect(consoleErrors).toEqual([]);
      expect(pageErrors).toEqual([]);
      expect(failedResponses).toEqual([]);
      expect(failedRequests.filter((failure) => !isExpectedStreamAbort(failure))).toEqual([]);
      await saveScreenshot(page, testInfo, scenario.id);
    } finally {
      const latest = await request.get(scenarioPath, { headers: controlHeaders });
      expect(latest.ok()).toBe(true);
      const latestSnapshot = await latest.json() as {
        generation: string;
        scenario: string;
      };
      expect(latestSnapshot.scenario).toBe(scenario.id);
      const reset = await request.delete(scenarioPath, {
        headers: {
          ...controlHeaders,
          "X-Failure-Injection-Generation": latestSnapshot.generation,
        },
      });
      expect(reset.ok()).toBe(true);
    }
  });
}

test("uses controlled Web Search market fallback after OKX retries are exhausted", async ({
  page,
  request,
}, testInfo) => {
  requireFailureInjectionProfile();
  test.setTimeout(210_000);
  const generation = await setFailureScenario(request, "okx_web_fallback_success");

  try {
    await page.goto("/work");
    await page.getByLabel("分析问题").fill(
      "验证 OKX 重试耗尽后使用带引用的 Web Search 行情，并完成可审计的保守分析。",
    );
    await page.getByRole("button", { name: "开始分析" }).click();

    const statusHeading = page.getByTestId("task-status").getByRole("heading");
    await expect(statusHeading).toHaveText("分析完成", { timeout: 150_000 });
    await expect(page.getByTestId("analysis-result")).toBeVisible();
    await expect(
      page.locator(".market-snapshot").getByText("Web Search 引用证据"),
    ).toBeVisible();
    await expect(page.getByText(/交易所原生行情数据不可用.*带引用的 Web Search 市场证据/)).toBeVisible();

    const taskId = new URL(page.url()).searchParams.get("task");
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i);
    const taskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(taskResponse.ok()).toBe(true);
    const task = productTaskSchema.parse(await taskResponse.json());
    expect(task.status).toBe("succeeded");
    expect(task.errors).toEqual([]);
    expect(task.market_snapshot).toMatchObject({
      symbol: "BTC-USDT-SWAP",
      source_level: "web_search_verified",
    });
    expect(task.artifact).toMatchObject({
      status: "committed",
      provenance: {
        market_provider: "web_search_market",
        search_provider: "controlled_dependency_test",
      },
    });
    const fallbackEvidence = task.web_evidence.filter(
      (item) => item.evidence_relation === "market_snapshot",
    );
    expect(fallbackEvidence).toHaveLength(1);
    expect(fallbackEvidence[0]).toMatchObject({
      source: "controlled_dependency_test",
      parser_version: "controlled-web-market-v1",
      evidence_relation: "market_snapshot",
    });
    expect(fallbackEvidence[0]?.final_url).toMatch(/^https:\/\//);

    const fallbackCard = page.locator("article.web-evidence-card").filter({
      hasText: "市场行情",
    });
    await expect(fallbackCard).toHaveCount(1);
    await expect(fallbackCard).toContainText("controlled_dependency_test");
    await expect(fallbackCard.getByRole("link")).toHaveAttribute("href", /^https:\/\//);

    const libraryResponse = await request.get("/api/product/api/v2/artifacts?limit=100");
    expect(libraryResponse.ok()).toBe(true);
    const library = artifactLibrarySchema.parse(await libraryResponse.json());
    expect(library.items.some((item) => item.task_id === taskId)).toBe(true);

    await assertProductSurfaceQuality(page);
    await saveScreenshot(page, testInfo, "okx_web_fallback_success");
  } finally {
    await resetFailureScenario(request, "okx_web_fallback_success", generation);
  }
});

test("persists both OKX and Web Search fallback failure diagnostics", async ({
  page,
  request,
}, testInfo) => {
  requireFailureInjectionProfile();
  test.setTimeout(210_000);
  const generation = await setFailureScenario(request, "okx_web_fallback_unavailable");

  try {
    await page.goto("/work");
    await page.getByLabel("分析问题").fill(
      "验证 OKX 与 Web Search 行情降级连续失败时保留两层依赖诊断，且不生成报告。",
    );
    await page.getByRole("button", { name: "开始分析" }).click();

    const statusHeading = page.getByTestId("task-status").getByRole("heading");
    await expect(statusHeading).toHaveText("分析失败", { timeout: 150_000 });
    const failure = page.locator("section.failure-panel[role='alert']");
    await expect(failure).toBeVisible();
    await failure.getByText("查看失败诊断", { exact: true }).click();
    await expect(failure).toContainText("builtin_web_search");
    await expect(failure).toContainText(/OKX/i);
    await expect(failure).toContainText("web_search_market");
    await expect(failure).toContainText("3");
    await expect(page.getByTestId("analysis-result")).toHaveCount(0);

    const taskId = new URL(page.url()).searchParams.get("task");
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i);
    const taskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(taskResponse.ok()).toBe(true);
    const task = productTaskSchema.parse(await taskResponse.json());
    expect(task.status).toBe("failed");
    expect(task.artifact).toBeNull();
    expect(task.errors).toHaveLength(1);
    expect(task.errors[0]).toMatchObject({
      code: "provider_unavailable",
      provider: "builtin_web_search",
      error_type: "InjectedWebMarketFallbackUnavailable",
      retryable: false,
      endpoint: "web_search_market",
      fallback_from: "okx",
      primary_attempt: 3,
      correlation_id: task.correlation_id,
    });
    expect(task.market_snapshot).toBeNull();
    expect(task.web_evidence).toEqual([]);

    const libraryResponse = await request.get("/api/product/api/v2/artifacts?limit=100");
    expect(libraryResponse.ok()).toBe(true);
    const library = artifactLibrarySchema.parse(await libraryResponse.json());
    expect(library.items.some((item) => item.task_id === taskId)).toBe(false);

    await page.reload();
    await expect(statusHeading).toHaveText("分析失败", { timeout: 30_000 });
    await expect(failure).toContainText("builtin_web_search");
    await expect(failure).toContainText(/OKX/i);
    await expect(page.getByTestId("analysis-result")).toHaveCount(0);
    const refreshedTaskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(refreshedTaskResponse.ok()).toBe(true);
    expect(productTaskSchema.parse(await refreshedTaskResponse.json())).toEqual(task);

    await assertProductSurfaceQuality(page);
    await saveScreenshot(page, testInfo, "okx_web_fallback_unavailable");
  } finally {
    await resetFailureScenario(request, "okx_web_fallback_unavailable", generation);
  }
});

test("renders retained Web market evidence when later research fails", async ({
  page,
  request,
}, testInfo) => {
  requireFailureInjectionProfile();
  test.setTimeout(210_000);
  const generation = await setFailureScenario(
    request,
    "okx_web_fallback_research_unavailable",
  );

  try {
    await page.goto("/work");
    await page.getByLabel("分析问题").fill(
      "验证行情回退成功但后续研究失败时保留来源，并明确显示 partial 状态。",
    );
    await page.getByRole("button", { name: "开始分析" }).click();

    const statusHeading = page.getByTestId("task-status").getByRole("heading");
    await expect(statusHeading).toHaveText("分析失败", { timeout: 150_000 });
    const failure = page.locator("section.failure-panel[role='alert']");
    await expect(failure).toContainText("后续研究检索未完成");
    await expect(failure).toContainText("已保留 1 条可验证 Web 来源");
    await expect(page.getByTestId("analysis-result")).toHaveCount(0);
    await expect(page.locator("pre")).toHaveCount(0);

    const evidenceRegion = page.locator("section.research-evidence");
    await expect(evidenceRegion).toContainText("已保留 1 条来源，研究未完成");
    await expect(evidenceRegion).toContainText("Web Search 引用证据");
    await expect(evidenceRegion.locator("article.web-evidence-card")).toHaveCount(1);
    await expect(evidenceRegion).toContainText("controlled_dependency_test");

    const taskId = new URL(page.url()).searchParams.get("task");
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i);
    const taskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(taskResponse.ok()).toBe(true);
    const task = productTaskSchema.parse(await taskResponse.json());
    expect(task).toMatchObject({
      task_id: taskId,
      status: "failed",
      artifact: null,
      market_snapshot: {
        source_level: "web_search_verified",
      },
    });
    expect(task.web_evidence).toHaveLength(1);
    expect(task.web_evidence[0]).toMatchObject({
      source: "controlled_dependency_test",
      parser_version: "controlled-web-market-v1",
      evidence_relation: "market_snapshot",
    });
    expect(task.errors).toHaveLength(1);
    expect(task.errors[0]).toMatchObject({
      code: "research_unavailable",
      endpoint: "research_events",
      provider: "failure_injection",
      error_type: "InjectedSearchUnavailable",
      retryable: false,
      correlation_id: task.correlation_id,
    });

    await page.reload();
    await expect(statusHeading).toHaveText("分析失败", { timeout: 30_000 });
    await expect(page.locator("section.research-evidence")).toContainText(
      "已保留 1 条来源，研究未完成",
    );

    await assertProductSurfaceQuality(page);
    await saveScreenshot(page, testInfo, "okx_web_fallback_research_unavailable");
  } finally {
    await resetFailureScenario(
      request,
      "okx_web_fallback_research_unavailable",
      generation,
    );
  }
});

test("keeps successful analysis distinct from retryable notification failure", async ({
  page,
  request,
}, testInfo) => {
  requireFailureInjectionProfile();
  test.setTimeout(210_000);
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
      scenario: "notification_failure",
      expected_generation: currentSnapshot.generation,
    },
  });
  expect(configured.ok()).toBe(true);
  const configuredSnapshot = await configured.json() as { scenario: string };
  expect(configuredSnapshot.scenario).toBe("notification_failure");

  let destinationEnabled = false;
  try {
    const enabledDestination = await request.patch(
      "/api/product/api/v2/settings/notifications",
      {
        data: {
          enabled: true,
          device_key: "failure-injection-device-key",
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
      "验证分析成功与通知可重试失败必须分别呈现，并保留完整持久化记录。",
    );
    const notificationToggle = page.getByRole("checkbox", {
      name: "完成后通知 Bark",
      exact: true,
    });
    await page.locator("label.notification-toggle").click({ timeout: 10_000 });
    await expect(notificationToggle).toBeChecked();
    await page.getByRole("button", { name: "开始分析" }).click({ timeout: 10_000 });

    const statusHeading = page.getByTestId("task-status").getByRole("heading");
    await expect(statusHeading).toHaveText("分析完成", { timeout: 120_000 });
    await expect(page.getByTestId("analysis-result")).toBeVisible();
    const completionWarning = page.getByTestId("completion-warning");
    await expect(completionWarning).toContainText("交付未完成", { timeout: 30_000 });
    await expect(completionWarning).toContainText("系统将在重试窗口内继续发送");
    await expect(page.getByText("等待重试", { exact: true })).toBeVisible();
    await expect(page.getByText("Provider 已接收", { exact: true })).toHaveCount(0);
    await expect(page.locator("pre")).toHaveCount(0);

    const taskId = new URL(page.url()).searchParams.get("task");
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i);
    const taskResponse = await request.get(`/api/product/api/v2/tasks/${taskId}`);
    expect(taskResponse.ok()).toBe(true);
    const task = productTaskSchema.parse(await taskResponse.json());
    expect(task).toMatchObject({
      task_id: taskId,
      status: "succeeded",
      completion_scope: {
        analysis: "complete",
        notification: "retrying",
      },
      warnings: ["notification_delivery_retrying"],
    });
    expect(task.artifact?.status).toBe("committed");
    expect(task.artifact?.provenance).toMatchObject({
      market_provider: "controlled_dependency",
      search_provider: "controlled_dependency_test",
      search_parser_version: "controlled-dependency-v1",
      model_provider: "controlled_dependency",
      model_name: "controlled-dependency-test",
      model_endpoint_host: null,
    });
    expect(task.market_snapshot?.source_level).toBe("controlled_dependency");
    expect(task.web_evidence).toHaveLength(1);
    expect(task.web_evidence[0]).toMatchObject({
      source: "controlled_dependency_test",
      parser_version: "controlled-dependency-v1",
      evidence_relation: "controlled_dependency",
    });
    expect(task.errors).toEqual([]);

    const notificationResponse = await request.get(
      `/api/product/api/v2/tasks/${taskId}/notifications`,
    );
    expect(notificationResponse.ok()).toBe(true);
    const notifications = notificationListSchema.parse(
      await notificationResponse.json(),
    );
    expect(notifications.task_id).toBe(taskId);
    expect(notifications.items).toHaveLength(1);
    expect(notifications.items[0]).toMatchObject({
      task_id: taskId,
      channel: "bark",
      status: "failed_retryable",
      attempt_count: 1,
    });
    expect(notifications.items[0].attempts).toHaveLength(1);
    expect(notifications.items[0].attempts[0]).toMatchObject({
      attempt_number: 1,
      result: "failed_retryable",
      error_code: "injected_notification_failure",
      provider_receipt: null,
    });

    const libraryResponse = await request.get("/api/product/api/v2/artifacts?limit=100");
    expect(libraryResponse.ok()).toBe(true);
    const library = artifactLibrarySchema.parse(await libraryResponse.json());
    expect(library.items.some((item) => item.task_id === taskId)).toBe(true);

    await assertProductSurfaceQuality(page);
    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
    expect(failedResponses).toEqual([]);
    expect(failedRequests.filter((failure) => !isExpectedStreamAbort(failure))).toEqual([]);
    await saveScreenshot(page, testInfo, "notification_failure");
  } finally {
    if (destinationEnabled) {
      const disabledDestination = await request.patch(
        "/api/product/api/v2/settings/notifications",
        { data: { enabled: false } },
      );
      expect(disabledDestination.ok()).toBe(true);
      expect(await disabledDestination.json()).toMatchObject({
        channel: "bark",
        enabled: false,
        configured: true,
      });
    }
    const latest = await request.get(scenarioPath, { headers: controlHeaders });
    expect(latest.ok()).toBe(true);
    const latestSnapshot = await latest.json() as {
      generation: string;
      scenario: string;
    };
    expect(latestSnapshot.scenario).toBe("notification_failure");
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
  ) {
    throw new Error(
      "failure-injection projects require V2_E2E_PROFILE=failure-injection and FAILURE_INJECTION_ENABLED=1",
    );
  }
  if (!process.env.FAILURE_INJECTION_CONTROL_TOKEN) {
    throw new Error("failure-injection projects require an injected control token");
  }
}

async function setFailureScenario(request: APIRequestContext, scenario: string) {
  const controlHeaders = failureScenarioControlHeaders();
  const current = await request.get(scenarioPath, { headers: controlHeaders });
  expect(current.ok()).toBe(true);
  const currentSnapshot = await current.json() as { generation: string };
  const configured = await request.put(scenarioPath, {
    headers: controlHeaders,
    data: {
      scenario,
      expected_generation: currentSnapshot.generation,
    },
  });
  expect(configured.ok()).toBe(true);
  const configuredSnapshot = await configured.json() as {
    generation: string;
    scenario: string;
  };
  expect(configuredSnapshot.scenario).toBe(scenario);
  return configuredSnapshot.generation;
}

async function resetFailureScenario(
  request: APIRequestContext,
  expectedScenario: string,
  configuredGeneration: string,
) {
  const controlHeaders = failureScenarioControlHeaders();
  const latest = await request.get(scenarioPath, { headers: controlHeaders });
  expect(latest.ok()).toBe(true);
  const latestSnapshot = await latest.json() as {
    generation: string;
    scenario: string;
  };
  expect(latestSnapshot.scenario).toBe(expectedScenario);
  expect(latestSnapshot.generation).toBe(configuredGeneration);
  const reset = await request.delete(scenarioPath, {
    headers: {
      ...controlHeaders,
      "X-Failure-Injection-Generation": latestSnapshot.generation,
    },
  });
  expect(reset.ok()).toBe(true);
}

function failureScenarioControlHeaders() {
  return {
    "X-Failure-Injection-Control-Token": process.env.FAILURE_INJECTION_CONTROL_TOKEN ?? "",
  };
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

function isExpectedStreamAbort(failure: { method: string; pathname: string; error: string }) {
  return failure.method === "POST"
    && /^\/api\/agent\/threads\/[0-9a-f-]{36}\/stream\/events$/i.test(failure.pathname)
    && /(?:ERR_ABORTED|NS_BINDING_ABORTED)/i.test(failure.error);
}

async function saveScreenshot(page: Page, testInfo: TestInfo, scenario: string) {
  const directory = path.resolve(process.cwd(), "artifacts", "playwright-real");
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, `provider-failure-${scenario}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}
