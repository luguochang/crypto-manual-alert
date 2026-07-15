import { expect, test, type Page, type TestInfo } from "@playwright/test";
import axe from "axe-core";
import fs from "node:fs/promises";
import path from "node:path";

const fixtureCreatedAt = new Date().toISOString();
const queuedTask = taskProjection("queued");
const pollNetworkFailure = { fixture: "network-failure" } as const;
const frontendOrigin = new URL(
  process.env.PLAYWRIGHT_FRONTEND_BASE_URL ?? "http://127.0.0.1:3101",
).origin;

test("renders the normal Product projection from queue through success", async ({ page }, testInfo) => {
  const requests = await installProductFixture(page, [
    taskProjection("running"),
    succeededTask(),
  ]);

  await page.goto("/manual-run");
  await expect(page).toHaveURL(/\/work$/);

  await page.getByRole("radio", { name: "ETH" }).check();
  await page.getByLabel("分析周期").selectOption("4h");
  await page.getByLabel("分析问题").fill("评估 ETH 在本轮宏观事件前的方向和风险边界");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("已排队");
  await expect(page.getByTestId("task-status")).toContainText("分析中");
  await expect(page.getByTestId("analysis-result")).toBeVisible();
  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  await expect(page.getByText("开多", { exact: true })).toBeVisible();
  await expect(page.getByText("67,250.50")).toBeVisible();
  await expect(page.getByText("68%", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Risk" })).toBeVisible();
  const analysisResult = page.getByTestId("analysis-result");
  await expect(analysisResult.getByRole("link", { name: /ETH market structure/ })).toHaveAttribute(
    "href",
    "https://example.com/market/eth",
  );
  const matchedSource = analysisResult.locator('.source-list li[data-evidence-matched="true"]');
  await expect(matchedSource).toContainText("OpenAI Web Search");
  await expect(matchedSource).toContainText("支持判断");
  await expect(matchedSource).toContainText("发布时间");
  await expect(matchedSource).toContainText("抓取时间");
  const unmatchedSource = analysisResult.locator('.source-list li[data-evidence-matched="false"]');
  await expect(unmatchedSource).toContainText("未匹配本次 Web 证据，仅按报告引用展示。");
  await expect(unmatchedSource).not.toContainText("Provider");
  await expect(analysisResult.getByText(/^来源 \d+$/)).toHaveCount(0);

  expect(requests.some((request) => request.pathname.endsWith("/api/v2/analysis"))).toBe(true);
  expect(requests.every((request) => request.origin === frontendOrigin)).toBe(true);
  expect(requests[0]?.body).toMatchObject({
    symbol: "ETH-USDT-SWAP",
    horizon: "4h",
    query_text: "评估 ETH 在本轮宏观事件前的方向和风险边界",
  });

  await assertNoRawPayload(page);
  await assertAccessible(page);
  await assertLayoutIntegrity(page);
  await saveScreenshot(page, testInfo, "work-success");
});

test("renders provider failure details without replacing them with success", async ({ page }, testInfo) => {
  await installProductFixture(page, [
    {
      ...taskProjection("failed"),
      errors: [
        {
          code: "search_timeout",
          message: "搜索服务在 20 秒内未返回结果，请稍后重试。",
          retryable: true,
        },
      ],
    },
  ]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 BTC 当前方向");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("分析失败");
  await expect(page.getByRole("heading", { name: "信息检索失败" })).toBeVisible();
  await expect(page.getByText("搜索服务在 20 秒内未返回结果，请稍后重试。"))
    .toBeVisible();
  await expect(page.getByRole("button", { name: "重新分析" })).toBeVisible();
  await expect(page.getByText("可重试", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("analysis-result")).toHaveCount(0);

  await assertNoRawPayload(page);
  await assertAccessible(page);
  await assertLayoutIntegrity(page);
  await saveScreenshot(page, testInfo, "work-failure");
});

test("renders only allowlisted research failure diagnostics", async ({ page }) => {
  const rawProviderFailure = {
    code: "research_unavailable",
    message: "检索服务没有返回可验证来源，当前未生成分析结果。",
    retryable: true,
    provider: "builtin_web_search",
    error_type: "UnverifiedServerToolCall",
    attempt: 3,
    raw_response: "fixture-private-raw-response",
    authorization: "Bearer fixture-private-token",
    endpoint: "https://private.example.test/responses",
    correlation_id: "fixture-private-correlation-id",
  };
  const {
    code,
    message,
    retryable,
    provider,
    error_type,
    attempt,
  } = rawProviderFailure;

  await installProductFixture(page, [{
    ...taskProjection("failed"),
    errors: [{ code, message, retryable, provider, error_type, attempt }],
  }]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 BTC 研究检索失败原因");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("分析失败");
  const diagnostics = page.getByLabel("失败诊断");
  await expect(diagnostics).toContainText("builtin_web_search");
  await expect(diagnostics).toContainText("UnverifiedServerToolCall");
  await expect(diagnostics).toContainText("第 3 次尝试");

  const visibleText = await page.locator("body").innerText();
  for (const forbiddenText of [
    "raw_response",
    "authorization",
    "endpoint",
    "correlation_id",
    rawProviderFailure.raw_response,
    rawProviderFailure.authorization,
    rawProviderFailure.endpoint,
    rawProviderFailure.correlation_id,
  ]) {
    expect(visibleText).not.toContain(forbiddenText);
  }

  await assertNoRawPayload(page);
  await assertLayoutIntegrity(page);
});

test("retry creates one new Product Task with a fresh idempotency key", async ({ page }) => {
  const originalTaskId = "task-retry-original";
  const retryTaskId = "task-retry-new";
  const retryableFailure = {
    ...taskProjection("failed"),
    task_id: originalTaskId,
    symbol: "SOL-USDT-SWAP",
    horizon: "1h",
    errors: [{
      code: "search_timeout",
      message: "搜索服务超时。",
      retryable: true,
    }],
  };
  const retrySuccess = {
    ...succeededTask(),
    task_id: retryTaskId,
    symbol: "SOL-USDT-SWAP",
    horizon: "1h",
    artifact: {
      ...succeededTask().artifact,
      analysis: {
        ...succeededTask().artifact.analysis,
        instrument: "SOL-USDT-SWAP",
        horizon: "1h",
      },
    },
  };
  const requests = await installProductFixture(
    page,
    [retryableFailure, retrySuccess],
    [
      { ...taskProjection("queued"), task_id: originalTaskId, symbol: "SOL-USDT-SWAP", horizon: "1h" },
      { ...taskProjection("queued"), task_id: retryTaskId, symbol: "SOL-USDT-SWAP", horizon: "1h" },
    ],
  );

  await page.goto("/work");
  await page.getByRole("radio", { name: "SOL" }).check();
  await page.getByLabel("分析周期").selectOption("1h");
  await page.getByLabel("分析问题").fill("重新检查 SOL 的事件窗口风险");
  await page.getByRole("button", { name: "开始分析" }).click();

  const retryButton = page.getByRole("button", { name: "重新分析" });
  await expect(retryButton).toBeVisible();
  await retryButton.evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });

  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  const postRequests = requests.filter((request) => request.method === "POST");
  expect(postRequests).toHaveLength(2);
  expect(postRequests[1]?.body).toMatchObject({
    symbol: "SOL-USDT-SWAP",
    horizon: "1h",
    query_text: "重新检查 SOL 的事件窗口风险",
  });
  expect(postRequests[0]?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/i);
  expect(postRequests[1]?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/i);
  expect(postRequests[1]?.idempotencyKey).not.toBe(postRequests[0]?.idempotencyKey);
  expect(requests.filter((request) => request.method === "GET").map((request) => request.pathname)).toEqual([
    `/api/product/api/v2/tasks/${originalTaskId}`,
    `/api/product/api/v2/tasks/${retryTaskId}`,
  ]);
});

test("recovers polling the same task after one transient read failure", async ({ page }) => {
  const requests = await installProductFixture(page, [
    pollNetworkFailure,
    taskProjection("running"),
    succeededTask(),
  ]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 BTC 当前方向");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByRole("heading", { name: "请求未完成" })).toBeVisible();
  await expect(page.getByTestId("task-status")).toContainText("已排队");
  await expect(page.getByRole("button", { name: "恢复读取" })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始分析" })).toBeEnabled();
  await assertAccessible(page);
  await assertLayoutIntegrity(page);

  await page.getByRole("button", { name: "恢复读取" }).click();

  await expect(page.getByRole("heading", { name: "请求未完成" })).toHaveCount(0);
  await expect(page.getByTestId("task-status")).toContainText("分析中");
  await expect(page.getByTestId("task-status")).toContainText("分析完成");

  const postRequests = requests.filter((request) => request.method === "POST");
  const getRequests = requests.filter((request) => request.method === "GET");
  expect(postRequests).toHaveLength(1);
  expect(getRequests).toHaveLength(3);
  expect(getRequests.every((request) => request.pathname.endsWith("/api/v2/tasks/task-fixture-1"))).toBe(true);
});

test("recovers the Product task from the URL after a full page refresh", async ({ page }) => {
  const taskId = "b6fc3c72-0de4-45e8-a236-f12e6c1a5444";
  const recoveredSuccess = {
    ...succeededTask(),
    task_id: taskId,
    completed_at: new Date().toISOString(),
  };
  const requests = await installProductFixture(page, [
    { ...taskProjection("running"), task_id: taskId },
    recoveredSuccess,
  ]);

  await page.goto(`/work?task=${taskId}`);

  await expect(page.getByTestId("task-status")).toContainText("分析中");
  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  await expect(page).toHaveURL(new RegExp(`/work\\?task=${taskId}$`));
  expect(requests.filter((request) => request.method === "POST")).toHaveLength(0);
  expect(requests.filter((request) => request.method === "GET")).toHaveLength(2);

  await page.reload();
  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  expect(requests.filter((request) => request.method === "POST")).toHaveLength(0);
});

test("shows a recovery state instead of a false empty state during a slow URL read", async ({ page }) => {
  const taskId = "a1c43cf1-2c64-44ba-80ab-36d83307e72d";
  await page.route("**/api/product/api/v2/tasks/**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...succeededTask(),
        task_id: taskId,
        completed_at: new Date().toISOString(),
      }),
    });
  });

  await page.goto(`/work?task=${taskId}`);

  await expect(page.getByRole("heading", { name: "正在恢复分析" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "等待新的分析请求" })).toHaveCount(0);
  await expect(page.getByTestId("task-status")).toContainText("分析完成");
});

test("does not offer an infinite read retry for a missing URL task", async ({ page }) => {
  const taskId = "d3b07384-d9a0-4dc8-99bd-560984a778ef";
  await page.route("**/api/product/api/v2/tasks/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Task not found" }),
    });
  });

  await page.goto(`/work?task=${taskId}`);

  await expect(page.getByRole("heading", { name: "请求未完成" })).toBeVisible();
  await expect(page.getByRole("button", { name: "恢复读取" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "等待新的分析请求" })).toHaveCount(0);
});

test("does not attach the Thread head stream while viewing historical Run output", async ({ page }) => {
  const taskId = "4f425521-6b4a-4ff6-8246-68f1a7d94d99";
  const productRunId = "57870ca4-44a1-4d5e-93a9-35cbf581494a";
  let agentRequests = 0;
  const selectedProductRuns: Array<string | null> = [];
  await page.route("**/api/product/api/v2/tasks/**", async (route) => {
    selectedProductRuns.push(new URL(route.request().url()).searchParams.get("run_id"));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...succeededTask(),
        task_id: taskId,
        completed_at: new Date().toISOString(),
        agent_stream: {
          protocol: "langgraph-v2",
          assistant_id: "crypto_analysis",
          thread_id: "7dd818c3-3425-44a0-99db-8b13bf5c9d65",
          run_id: "de2809e8-9af3-4361-a1c4-1b1dbf47525d",
        },
      }),
    });
  });
  await page.route("**/api/agent/**", async (route) => {
    agentRequests += 1;
    await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
  });

  await page.goto(`/work?task=${taskId}&run=${productRunId}`);
  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  await page.waitForTimeout(1_300);

  expect(agentRequests).toBe(0);
  expect(selectedProductRuns).toEqual([productRunId]);
});

test("rejects rapid duplicate submits before React state commits", async ({ page }) => {
  const requests = await installProductFixture(page, [succeededTask()]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 BTC 当前方向");
  await page.locator("form").evaluate((form) => {
    const submitter = form.querySelector<HTMLButtonElement>('button[type="submit"]');
    if (!submitter) throw new Error("Missing submit button");
    const submit = () => form.dispatchEvent(new SubmitEvent("submit", {
      bubbles: true,
      cancelable: true,
      submitter,
    }));
    submit();
    submit();
  });

  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  expect(requests.filter((request) => request.method === "POST")).toHaveLength(1);
});

test("continues polling from waiting-human to the terminal projection", async ({ page }) => {
  const requests = await installProductFixture(page, [
    taskProjection("waiting_human"),
    taskProjection("blocked"),
  ]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("评估 SOL 的事件窗口风险");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("等待人工确认");
  await expect(page.getByRole("button", { name: "开始分析" })).toBeEnabled();
  await page.waitForTimeout(1_100);

  expect(requests.filter((request) => request.method === "GET")).toHaveLength(2);
  await expect(page.getByTestId("task-status")).toContainText("已被风险门禁阻断");
});

test("a new submission invalidates an older poll loop", async ({ page }) => {
  const oldQueuedTask = { ...taskProjection("queued"), task_id: "task-old" };
  const newQueuedTask = { ...taskProjection("queued"), task_id: "task-new" };
  const oldRunningTask = { ...taskProjection("running"), task_id: "task-old" };
  const staleOldTask = {
    ...taskProjection("failed"),
    task_id: "task-old",
    symbol: "ETH-USDT-SWAP",
    errors: [{ code: "stale", message: "旧任务不应覆盖新任务。", retryable: false }],
  };
  const newWaitingTask = {
    ...taskProjection("waiting_human"),
    task_id: "task-new",
    symbol: "SOL-USDT-SWAP",
  };
  const requests = await installProductFixture(
    page,
    [oldRunningTask, staleOldTask, newWaitingTask],
    [oldQueuedTask, newQueuedTask],
  );

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 BTC 当前方向");
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByTestId("task-status")).toContainText("分析中");
  await expect.poll(
    () => requests.filter((request) => request.method === "GET").length,
    { timeout: 3_000 },
  ).toBe(2);

  await page.locator("form").evaluate((form) => {
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
  });

  await expect(page.getByTestId("task-status")).toContainText("等待人工确认");
  await expect(page.getByTestId("task-status")).toContainText("SOL");
  await expect(page.getByText("旧任务不应覆盖新任务。")).toHaveCount(0);
  expect(requests.filter((request) => request.method === "POST")).toHaveLength(2);
});

async function installProductFixture(
  page: Page,
  pollSequence: unknown[],
  submissionSequence: unknown[] = [queuedTask],
) {
  const requests: Array<{
    method: string;
    origin: string;
    pathname: string;
    body: unknown;
    idempotencyKey: string | null;
  }> = [];
  let pollIndex = 0;
  let submissionIndex = 0;

  await page.route("**/api/product/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.method() === "POST" ? request.postDataJSON() : null;
    requests.push({
      method: request.method(),
      origin: url.origin,
      pathname: url.pathname,
      body,
      idempotencyKey: request.headers()["idempotency-key"] ?? null,
    });

    if (request.method() === "POST" && url.pathname.endsWith("/api/v2/analysis")) {
      const projection = submissionSequence[Math.min(submissionIndex, submissionSequence.length - 1)];
      submissionIndex += 1;
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(projection) });
      return;
    }

    if (request.method() === "GET" && url.pathname.includes("/api/v2/tasks/")) {
      const projection = pollSequence[Math.min(pollIndex, pollSequence.length - 1)];
      pollIndex += 1;
      if (isPollNetworkFailure(projection)) {
        await route.abort("connectionfailed");
        return;
      }
      if (pollIndex > 1) {
        await new Promise((resolve) => setTimeout(resolve, 650));
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projection) });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unexpected fixture route" }),
    });
  });

  return requests;
}

function isPollNetworkFailure(value: unknown): value is typeof pollNetworkFailure {
  return typeof value === "object" && value !== null && "fixture" in value && value.fixture === "network-failure";
}

function taskProjection(status: string) {
  return {
    task_id: "task-fixture-1",
    status,
    symbol: "ETH-USDT-SWAP",
    horizon: "4h",
    created_at: fixtureCreatedAt,
    artifact: null,
    errors: [],
  };
}

function succeededTask() {
  return {
    ...taskProjection("succeeded"),
    web_evidence: [{
      query: "ETH market structure",
      final_url: "https://example.com/market/eth",
      redirect_chain: [],
      http_status: 200,
      fetched_at: fixtureCreatedAt,
      published_at: fixtureCreatedAt,
      content_hash: "a".repeat(64),
      parser_version: "openai-responses-citation-v1",
      title: "ETH market structure confirms momentum",
      author: "Markets desk",
      source: "openai_builtin_web_search",
      excerpt: "Spot and derivatives structure support the current directional read.",
      evidence_relation: "supports",
    }],
    artifact: {
      artifact_type: "analysis_report",
      schema_version: "1.0",
      content_version: 1,
      status: "committed",
      analysis: {
        regime: "risk_on",
        factor_scores: { momentum: 2, macro: 1 },
        total_score: 3,
        main_action: "open_long",
        instrument: "ETH-USDT-SWAP",
        horizon: "4h",
        reference_price: "67250.5",
        entry_trigger: "67400",
        stop_price: "65800",
        target_1: "68800",
        target_2: "70100",
        probability: 0.68,
        position_size_class: "light",
        max_leverage: 2,
        risk_pct: "0.01",
        root_cause_chain: ["Momentum improved", "Macro event risk is contained"],
        why_not_opposite: "Short momentum lacks confirmation.",
        invalidation: "A 4h close below 65800 invalidates the setup.",
        unavailable_data: [],
        manual_execution_required: true,
        expires_in_seconds: 14400,
      },
      evidence_verdict: {
        sufficient: true,
        confidence_cap: 0.72,
        missing_required: [],
        missing_optional: ["options_skew"],
        warnings: ["美股现金盘尚未开盘。"],
      },
      risk_verdict: {
        allowed: true,
        blocked_reasons: [],
        warnings: ["事件前保持轻仓。"],
        confidence_cap: 0.7,
      },
      source_references: [
        "https://example.com/market/eth",
        "https://example.com/macro/fed",
      ],
    },
  };
}

async function assertNoRawPayload(page: Page) {
  await expect(page.locator("pre")).toHaveCount(0);
  const visibleText = await page.locator("body").innerText();
  expect(visibleText).not.toContain('"task_id"');
  expect(visibleText).not.toContain('"artifact"');
  expect(visibleText).not.toContain("Raw JSON");
}

async function assertAccessible(page: Page) {
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const axeRuntime = (window as typeof window & {
      axe: {
        run: () => Promise<{
          violations: Array<{ id: string; help: string; nodes: Array<{ target: string[] }> }>;
        }>;
      };
    }).axe;
    const result = await axeRuntime.run();
    return result.violations.map(({ id, help, nodes }) => ({ id, help, targets: nodes.map((node) => node.target) }));
  });

  expect(violations).toEqual([]);
}

async function assertLayoutIntegrity(page: Page) {
  const audit = await page.evaluate(() => {
    const viewportOverflow = document.documentElement.scrollWidth - window.innerWidth;
    const elements = Array.from(
      document.querySelectorAll<HTMLElement>(
        "a[href], button, select, textarea, input:not([type='hidden']):not([type='radio'])",
      ),
    ).filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 1 && rect.height > 1 && style.visibility !== "hidden" && style.display !== "none";
    });
    const overlaps: string[] = [];

    for (let firstIndex = 0; firstIndex < elements.length; firstIndex += 1) {
      for (let secondIndex = firstIndex + 1; secondIndex < elements.length; secondIndex += 1) {
        const first = elements[firstIndex];
        const second = elements[secondIndex];
        if (!first || !second || first.contains(second) || second.contains(first)) continue;
        const a = first.getBoundingClientRect();
        const b = second.getBoundingClientRect();
        const xOverlap = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const yOverlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (xOverlap > 1 && yOverlap > 1) {
          overlaps.push(`${first.tagName}:${first.textContent?.trim()} <> ${second.tagName}:${second.textContent?.trim()}`);
        }
      }
    }

    return { viewportOverflow, overlaps };
  });

  expect(audit.viewportOverflow).toBeLessThanOrEqual(0);
  expect(audit.overlaps).toEqual([]);
}

async function saveScreenshot(page: Page, testInfo: TestInfo, name: string) {
  const screenshotDirectory = path.resolve(process.cwd(), "artifacts", "playwright");
  await fs.mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDirectory, `${name}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}

test("artifact state: keeps a blocked draft out of committed advice", async ({ page }) => {
  const blockedDraft = succeededTask();
  blockedDraft.status = "blocked";
  blockedDraft.artifact.status = "draft";
  blockedDraft.artifact.evidence_verdict.sufficient = false;
  blockedDraft.artifact.evidence_verdict.confidence_cap = 0;
  (blockedDraft.artifact.evidence_verdict.missing_required as string[]).push("order_book");
  blockedDraft.artifact.risk_verdict.allowed = false;
  blockedDraft.artifact.risk_verdict.confidence_cap = 0;
  (blockedDraft.artifact.risk_verdict.blocked_reasons as string[]).push("evidence.insufficient:order_book");
  await installProductFixture(page, [blockedDraft]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 ETH 当前方向");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("已被风险门禁阻断");
  await expect(page.getByText("分析草稿未提交", { exact: false })).toBeVisible();
  await expect(page.getByText("evidence.insufficient:order_book", { exact: false })).toBeVisible();
  await expect(page.getByTestId("analysis-result")).toHaveCount(0);
  await expect(page.getByText("Committed analysis", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("交易计划")).toHaveCount(0);
  await assertNoRawPayload(page);
});

test("artifact state: marks expired committed analysis as a non-actionable snapshot", async ({ page }) => {
  const expiredTask = succeededTask();
  expiredTask.created_at = "2020-01-01T00:00:00Z";
  expiredTask.artifact.analysis.expires_in_seconds = 60;
  (expiredTask.artifact.analysis.unavailable_data as string[]).push("精确 CVD", "清算热力图");
  await installProductFixture(page, [expiredTask]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 ETH 当前方向");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("分析已过期");
  await expect(page.getByTestId("analysis-result")).toHaveAttribute("data-artifact-state", "expired");
  await expect(page.getByText("Expired analysis", { exact: true })).toBeVisible();
  await expect(page.getByText("Committed analysis", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Action", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("交易计划")).toHaveCount(0);
  await expect(page.getByLabel("已过期分析快照")).toBeVisible();
  await expect(page.getByText("60 秒", { exact: true })).toBeVisible();
  await expect(page.getByText("精确 CVD、清算热力图", { exact: true })).toBeVisible();
  await assertNoRawPayload(page);
});

test("artifact state: expires from completion time while the page remains open", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-07-13T09:00:00Z") });
  const expiringTask = {
    ...succeededTask(),
    created_at: "2026-07-13T08:59:58Z",
    completed_at: "2026-07-13T09:00:00Z",
  };
  expiringTask.artifact.analysis.expires_in_seconds = 3;
  await installProductFixture(page, [expiringTask]);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill("检查 ETH 当前方向");
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("task-status")).toContainText("已排队");
  await page.clock.fastForward(1_100);
  await expect(page.getByTestId("task-status")).toContainText("分析完成");
  await expect(page.getByTestId("analysis-result")).toHaveAttribute(
    "data-actionable",
    "true",
  );
  await expect(page.getByText("开多", { exact: true })).toBeVisible();

  await page.clock.fastForward(2_000);

  await expect(page.getByTestId("task-status")).toContainText("分析已过期");
  await expect(page.getByTestId("analysis-result")).toHaveAttribute(
    "data-actionable",
    "false",
  );
  await expect(page.getByText("Action", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("交易计划")).toHaveCount(0);
});
