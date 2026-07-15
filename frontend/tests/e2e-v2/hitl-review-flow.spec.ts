import {
  expect,
  test,
  type Page,
  type Request as PlaywrightRequest,
  type Response as PlaywrightResponse,
  type TestInfo,
} from "@playwright/test";

import {
  productTaskSchema,
  type PendingInterrupt,
  type ProductTask,
} from "../../src/lib/schemas/product-api";

type AnalysisArtifact = NonNullable<ProductTask["artifact"]>;

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const expectedProjects: Record<string, {
  taskEnvironmentVariable: "HITL_TASK_ID_DESKTOP" | "HITL_TASK_ID_MOBILE";
  viewport: { width: number; height: number };
}> = {
  "fixture-desktop": {
    taskEnvironmentVariable: "HITL_TASK_ID_DESKTOP",
    viewport: { width: 1440, height: 1000 },
  },
  "fixture-pixel-7": {
    taskEnvironmentVariable: "HITL_TASK_ID_MOBILE",
    viewport: { width: 412, height: 915 },
  },
};

const reviewActionLabels: Record<string, string> = {
  open_long: "开多",
  open_short: "开空",
  hold_long: "持有多单",
  hold_short: "持有空单",
  close_long: "平多",
  close_short: "平空",
  flip_long_to_short: "多转空",
  flip_short_to_long: "空转多",
  trigger_long: "条件触发多单",
  trigger_short: "条件触发空单",
  no_trade: "不交易",
};

const resultActionLabels: Record<string, string> = {
  open_long: "开多",
  open_short: "开空",
  hold_long: "持有多单",
  hold_short: "持有空单",
  close_long: "平多",
  close_short: "平空",
  flip_long_to_short: "由多转空",
  flip_short_to_long: "由空转多",
  trigger_long: "条件触发做多",
  trigger_short: "条件触发做空",
  no_trade: "暂不操作",
};

const positionLabels: Record<string, string> = {
  light: "轻仓",
  standard: "标准仓位",
  heavy: "重仓",
  none: "不建仓",
};

test.skip(
  process.env.REAL_PRODUCT_E2E !== "1",
  "set REAL_PRODUCT_E2E=1 to run the real Product API HITL chain",
);

test("approves a real Product HITL review and persists the committed artifact", async ({ page }, testInfo) => {
  test.setTimeout(300_000);

  const taskId = taskIdForProject(page, testInfo);
  const taskPath = `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}`;
  const observer = installBrowserObserver(page);
  const initialProjectionResponse = page.waitForResponse(
    (response) => isTaskReadResponse(response, taskPath),
    { timeout: 30_000 },
  );

  await page.goto(`/work?task=${encodeURIComponent(taskId)}`);
  const waitingTask = await parseProductTaskResponse(await initialProjectionResponse);
  const interrupt = assertWaitingReviewProjection(waitingTask, taskId);
  const respondPath = `${taskPath}/interrupts/${encodeURIComponent(interrupt.interrupt_id)}/respond`;

  await assertReadablePendingReview(page, interrupt);
  await assertNoRawPayload(page);
  await assertPageQuality(page, "waiting_human review");

  const panel = page.locator("section.hitl-review-panel");
  const approve = panel.getByRole("group", { name: "审核决定" })
    .getByRole("button", { name: "批准", exact: true });
  await expect(approve).toBeEnabled();
  await approve.click();

  await expect(panel.getByRole("heading", { name: "确认批准这份分析？", exact: true })).toBeVisible();
  await expect(panel.getByText("批准后，Agent 将恢复运行并提交最终报告。", { exact: true })).toBeVisible();
  const approvalComment = `Playwright ${testInfo.project.name} Product HITL approve`;
  await panel.getByLabel("审核备注（可选）").fill(approvalComment);

  const respondResponsePromise = page.waitForResponse(
    (response) => isResponseFor(response, "POST", respondPath),
    { timeout: 30_000 },
  );
  const succeededResponsePromise = page.waitForResponse(
    (response) => isSucceededTaskRead(response, taskPath, taskId),
    { timeout: 240_000 },
  );

  await panel.getByRole("button", { name: "确认批准", exact: true }).click();
  const respondResponse = await respondResponsePromise;

  expect(respondResponse.status()).toBe(202);
  assertRespondRequest(
    respondResponse.request(),
    respondPath,
    interrupt.response_version,
    approvalComment,
  );

  const respondingTask = await parseProductTaskResponse(respondResponse);
  assertRespondingProjection(respondingTask, taskId, interrupt, approvalComment);
  await assertNoRawPayload(page);

  const succeededTask = await parseProductTaskResponse(await succeededResponsePromise);
  const committedArtifact = assertSucceededProjection(succeededTask, taskId);
  await assertReadableCommittedArtifact(page, committedArtifact);
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "分析草稿待人工确认", exact: true })).toHaveCount(0);
  await assertNoRawPayload(page);
  await assertPageQuality(page, "succeeded artifact");
  assertExactlyOneRespondWrite(observer, respondPath);

  const taskUrl = new URL(page.url());
  expect(taskUrl.pathname).toBe("/work");
  expect(taskUrl.searchParams.get("task")).toBe(taskId);
  expect(taskUrl.searchParams.get("run")).toBeNull();

  const refreshedProjectionResponse = page.waitForResponse(
    (response) => isTaskReadResponse(response, taskPath),
    { timeout: 30_000 },
  );
  await page.reload();
  await expect(page).toHaveURL(taskUrl.toString());

  const refreshedTask = await parseProductTaskResponse(await refreshedProjectionResponse);
  const refreshedArtifact = assertSucceededProjection(refreshedTask, taskId);
  expect(refreshedArtifact).toEqual(committedArtifact);
  await assertReadableCommittedArtifact(page, refreshedArtifact);
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "审核决定" })).toHaveCount(0);
  await assertNoRawPayload(page);
  await assertPageQuality(page, "refreshed succeeded artifact");
  assertExactlyOneRespondWrite(observer, respondPath);
  await attachDeepScrollScreenshot(page, testInfo);

  expect(observer.consoleErrors).toEqual([]);
  expect(observer.pageErrors).toEqual([]);
  expect(observer.serverErrors).toEqual([]);
});

interface ObservedRequest {
  method: string;
  pathname: string;
}

interface BrowserObserver {
  writes: ObservedRequest[];
  consoleErrors: string[];
  pageErrors: string[];
  serverErrors: string[];
}

function taskIdForProject(page: Page, testInfo: TestInfo) {
  const project = expectedProjects[testInfo.project.name];
  if (project === undefined) {
    throw new Error(
      `Product HITL E2E must run in fixture-desktop or fixture-pixel-7, received ${testInfo.project.name}`,
    );
  }
  expect(page.viewportSize()).toEqual(project.viewport);

  const dedicatedTaskId = process.env[project.taskEnvironmentVariable]?.trim();
  const fallbackTaskId = process.env.HITL_TASK_ID?.trim();
  const taskId = dedicatedTaskId || fallbackTaskId;
  if (!taskId) {
    throw new Error(
      `set ${project.taskEnvironmentVariable} (or fallback HITL_TASK_ID) to a fresh waiting_human task`,
    );
  }
  if (!uuidPattern.test(taskId)) {
    throw new Error(`${project.taskEnvironmentVariable} must contain a Product task UUID`);
  }
  return taskId.toLowerCase();
}

function installBrowserObserver(page: Page): BrowserObserver {
  const observer: BrowserObserver = {
    writes: [],
    consoleErrors: [],
    pageErrors: [],
    serverErrors: [],
  };

  page.on("request", (request) => {
    const observed = observedRequest(request);
    if (writeMethods.has(observed.method)) observer.writes.push(observed);
  });
  page.on("console", (message) => {
    if (message.type() === "error") observer.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => observer.pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      const request = observedRequest(response.request());
      observer.serverErrors.push(`${response.status()} ${request.method} ${request.pathname}`);
    }
  });

  return observer;
}

function observedRequest(request: PlaywrightRequest): ObservedRequest {
  return {
    method: request.method().toUpperCase(),
    pathname: new URL(request.url()).pathname,
  };
}

function isResponseFor(response: PlaywrightResponse, method: string, pathname: string) {
  const request = observedRequest(response.request());
  return request.method === method && request.pathname === pathname;
}

function isTaskReadResponse(response: PlaywrightResponse, taskPath: string) {
  return response.ok() && isResponseFor(response, "GET", taskPath);
}

async function isSucceededTaskRead(
  response: PlaywrightResponse,
  taskPath: string,
  taskId: string,
) {
  if (!isTaskReadResponse(response, taskPath)) return false;
  try {
    const parsed = productTaskSchema.safeParse(await response.json());
    return parsed.success
      && parsed.data.task_id === taskId
      && parsed.data.status === "succeeded";
  } catch {
    return false;
  }
}

async function parseProductTaskResponse(response: PlaywrightResponse): Promise<ProductTask> {
  const contentType = response.headers()["content-type"] ?? "";
  expect(contentType).toContain("application/json");
  const parsed = productTaskSchema.safeParse(await response.json());
  if (!parsed.success) {
    throw new Error(`Product task response violated its schema: ${parsed.error.message}`);
  }
  return parsed.data;
}

function assertWaitingReviewProjection(task: ProductTask, taskId: string): PendingInterrupt {
  expect(task.task_id).toBe(taskId);
  expect(task.status).toBe("waiting_human");
  expect(task.pending_interrupts).toHaveLength(1);
  const interrupt = task.pending_interrupts[0];
  if (interrupt === undefined) throw new Error("waiting_human task has no review interrupt");

  expect(interrupt.task_id).toBe(taskId);
  expect(interrupt.status).toBe("pending");
  expect(interrupt.response).toBeNull();
  expect(interrupt.responded_at).toBeNull();
  expect(interrupt.payload.kind).toBe("artifact_review");
  expect(interrupt.payload.schema_version).toBe("1.0");
  expect(interrupt.payload.allowed_actions).toEqual(["approve", "reject", "edit"]);
  expect(interrupt.payload.artifact.status).toBe("draft");
  expect(interrupt.payload.artifact.evidence_verdict.sufficient).toBe(true);
  expect(interrupt.payload.artifact.risk_verdict.allowed).toBe(true);
  return interrupt;
}

async function assertReadablePendingReview(page: Page, interrupt: PendingInterrupt) {
  const panel = page.locator("section.hitl-review-panel");
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText("等待人工确认");
  await expect(panel).toHaveCount(1);
  await expect(panel.getByRole("heading", { name: "分析草稿待人工确认", exact: true })).toBeVisible();
  const pendingBadge = panel.locator('.hitl-review-state[aria-live="off"]');
  await expect(pendingBadge).not.toHaveAttribute("role", "status");
  await expect(pendingBadge).toHaveText(
    /^(?:等待决定|剩余 \d{2}:\d{2}(?::\d{2})?)$/,
  );

  const analysis = interrupt.payload.artifact.analysis;
  const summary = panel.getByLabel("待审核决策摘要");
  await expect(summary).toBeVisible();
  const metrics = await summary.locator(":scope > div").evaluateAll((nodes) => nodes.map((node) => ({
    label: node.querySelector("span")?.textContent?.trim() ?? "",
    value: node.querySelector("strong")?.textContent?.trim() ?? "",
  })));
  expect(metrics).toEqual([
    { label: "建议动作", value: reviewActionLabels[analysis.main_action] ?? analysis.main_action },
    { label: "主观概率", value: `${Math.round(analysis.probability * 100)}%` },
    { label: "仓位等级", value: positionLabels[analysis.position_size_class] ?? analysis.position_size_class },
    { label: "最大杠杆", value: `${analysis.max_leverage}x` },
    { label: "风险比例", value: `${formatPercent(analysis.risk_pct)}%` },
  ]);

  expect(await panel.locator(".hitl-cause-list li").allTextContents()).toEqual(
    analysis.root_cause_chain,
  );
  const notes = await panel.locator(".hitl-review-notes > div").evaluateAll((nodes) => nodes.map((node) => ({
    label: node.querySelector("dt")?.textContent?.trim() ?? "",
    value: node.querySelector("dd")?.textContent?.trim() ?? "",
  })));
  expect(notes).toEqual([
    { label: "不选择反向的原因", value: analysis.why_not_opposite },
    { label: "失效条件", value: analysis.invalidation },
  ]);
  expect(await panel.locator(".hitl-gate-row strong").allTextContents()).toEqual([
    "证据满足门禁",
    "风险策略允许",
  ]);
  const sources = panel.locator(".hitl-review-sources");
  await expect(sources.getByRole("heading", { name: "分析来源", exact: true })).toBeVisible();
  await expect(sources.getByRole("link")).toHaveCount(
    interrupt.payload.artifact.source_references.length,
  );
  for (const reference of interrupt.payload.artifact.source_references) {
    await expect(sources.getByRole("link", { name: reference })).toHaveAttribute(
      "href",
      new URL(reference).toString(),
    );
  }
  await expect(panel.getByRole("group", { name: "审核决定" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "批准", exact: true })).toBeEnabled();
  await expect(panel.getByRole("button", { name: "拒绝", exact: true })).toBeEnabled();
  await expect(panel.getByRole("button", { name: "修改后重审", exact: true })).toBeEnabled();
}

function assertRespondRequest(
  request: PlaywrightRequest,
  respondPath: string,
  responseVersion: number,
  approvalComment: string,
) {
  expect(observedRequest(request)).toEqual({ method: "POST", pathname: respondPath });
  const headers = request.headers();
  expect(headers.accept).toContain("application/json");
  expect(headers["content-type"]).toContain("application/json");
  expect(headers["idempotency-key"]).toMatch(uuidPattern);
  expect(request.postDataJSON()).toEqual({
    response_version: responseVersion,
    action: "approve",
    comment: approvalComment,
    edits: null,
  });
}

function assertRespondingProjection(
  task: ProductTask,
  taskId: string,
  pendingInterrupt: PendingInterrupt,
  approvalComment: string,
) {
  expect(task.task_id).toBe(taskId);
  expect(task.status).toBe("waiting_human");
  expect(task.pending_interrupts).toHaveLength(1);
  const respondingInterrupt = task.pending_interrupts[0];
  if (respondingInterrupt === undefined) {
    throw new Error("respond endpoint did not return its responding interrupt");
  }
  expect(respondingInterrupt.interrupt_id).toBe(pendingInterrupt.interrupt_id);
  expect(respondingInterrupt.response_version).toBe(pendingInterrupt.response_version);
  expect(respondingInterrupt.status).toBe("responding");
  expect(respondingInterrupt.response).toEqual({
    action: "approve",
    comment: approvalComment,
  });
  expect(respondingInterrupt.responded_at).not.toBeNull();
}

function assertSucceededProjection(task: ProductTask, taskId: string): AnalysisArtifact {
  expect(task.task_id).toBe(taskId);
  expect(task.status).toBe("succeeded");
  expect(task.pending_interrupts).toEqual([]);
  if (task.artifact === null) throw new Error("succeeded Product task has no artifact");
  expect(task.artifact.status).toBe("committed");
  expect(task.artifact.evidence_verdict.sufficient).toBe(true);
  expect(task.artifact.risk_verdict.allowed).toBe(true);
  assertReadableAnalysis(task.artifact);
  return task.artifact;
}

function assertReadableAnalysis(artifact: AnalysisArtifact) {
  const analysis = artifact.analysis;
  expect(analysis.root_cause_chain.length).toBeGreaterThan(0);
  for (const statement of analysis.root_cause_chain) {
    expect(statement.trim().length).toBeGreaterThan(3);
    expect(statement).toMatch(/\p{L}/u);
    expect(statement).not.toMatch(/^\s*[\[{]/);
  }
  expect(analysis.why_not_opposite.trim().length).toBeGreaterThan(3);
  expect(analysis.why_not_opposite).toMatch(/\p{L}/u);
  expect(analysis.invalidation.trim().length).toBeGreaterThan(3);
  expect(analysis.invalidation).toMatch(/\p{L}/u);
}

async function assertReadableCommittedArtifact(page: Page, artifact: AnalysisArtifact) {
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText("分析完成", {
    timeout: 30_000,
  });
  const result = page.getByTestId("analysis-result");
  await expect(result).toBeVisible();
  await expect(result).toHaveAttribute("data-artifact-state", "committed");
  await expect(result).toHaveAttribute("data-actionable", "true");
  await expect(result.locator(".decision-summary strong")).toHaveText(
    resultActionLabels[artifact.analysis.main_action] ?? artifact.analysis.main_action,
  );
  await expect(result.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  await expect(result.getByRole("heading", { name: "Risk", exact: true })).toBeVisible();
  await expect(result.getByRole("heading", { name: "判断依据", exact: true })).toBeVisible();
  await expect(result.getByRole("heading", { name: "来源链接", exact: true })).toBeVisible();
  expect(await result.locator(".rationale-list li").allTextContents()).toEqual(
    artifact.analysis.root_cause_chain,
  );
  await expect(result.locator(".reasoning-notes .detail-item").filter({
    hasText: "反向判断",
  }).locator("strong")).toHaveText(artifact.analysis.why_not_opposite);
  await expect(result.locator(".reasoning-notes .detail-item").filter({
    hasText: "失效条件",
  }).locator("strong")).toHaveText(artifact.analysis.invalidation);
  await expect(result.getByText("必要证据完整", { exact: true })).toBeVisible();
  await expect(result.getByText("风险门禁通过", { exact: true })).toBeVisible();
}

function assertExactlyOneRespondWrite(observer: BrowserObserver, respondPath: string) {
  expect(observer.writes.filter((request) => request.pathname === respondPath)).toEqual([
    { method: "POST", pathname: respondPath },
  ]);
  expect(observer.writes.filter((request) =>
    request.pathname.startsWith("/api/product/")
    && request.pathname !== respondPath,
  )).toEqual([]);
  expect(observer.writes.filter((request) =>
    request.pathname.startsWith("/api/agent/")
    && !request.pathname.endsWith("/history"),
  )).toEqual([]);
}

async function assertNoRawPayload(page: Page) {
  await expect(page.locator("pre")).toHaveCount(0);
  const visibleText = await page.locator("body").innerText();
  expect(visibleText).not.toMatch(/raw json/i);
  expect(visibleText).not.toMatch(
    /"(?:task_id|artifact|pending_interrupts|response_version|root_cause_chain|source_references)"\s*:/,
  );
}

async function assertPageQuality(page: Page, phase: string) {
  const audit = await page.evaluate(() => {
    const root = document.documentElement;
    const horizontalOverflow = Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0)
      - root.clientWidth;
    const visibleControls = Array.from(document.querySelectorAll<HTMLElement>(
      "button, a[href], input:not([type='hidden']), select, textarea",
    )).filter((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return element.getClientRects().length > 0
        && rect.width > 0
        && rect.height > 0
        && style.display !== "none"
        && style.visibility !== "hidden";
    });
    const unnamedControls = visibleControls
      .filter((element) => accessibleControlName(element).length === 0)
      .map((element) => {
        const className = typeof element.className === "string" && element.className
          ? `.${element.className.trim().replace(/\s+/g, ".")}`
          : "";
        return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${className}`;
      });

    return { horizontalOverflow, unnamedControls };

    function accessibleControlName(element: HTMLElement) {
      const labelledBy = (element.getAttribute("aria-labelledby") ?? "")
        .split(/\s+/)
        .filter(Boolean)
        .map((id) => document.getElementById(id)?.textContent ?? "")
        .join(" ");
      const labels = "labels" in element && element.labels
        ? Array.from(element.labels as NodeListOf<HTMLLabelElement>)
            .map((label) => label.textContent ?? "")
            .join(" ")
        : "";
      const inputValue = element instanceof HTMLInputElement
        && ["button", "image", "reset", "submit"].includes(element.type)
        ? element.value
        : "";

      return [
        element.getAttribute("aria-label"),
        labelledBy,
        labels,
        element.textContent,
        element.getAttribute("alt"),
        inputValue,
        element.getAttribute("title"),
      ].filter(Boolean).join(" ").trim();
    }
  });

  expect(audit.horizontalOverflow, `${phase} has horizontal overflow`).toBeLessThanOrEqual(0);
  expect(audit.unnamedControls, `${phase} has unnamed interactive controls`).toEqual([]);
}

async function attachDeepScrollScreenshot(page: Page, testInfo: TestInfo) {
  const deepTarget = page.getByTestId("analysis-result")
    .getByRole("heading", { name: "来源链接", exact: true });
  await deepTarget.scrollIntoViewIfNeeded();
  const position = await page.evaluate(() => ({
    scrollY: window.scrollY,
    maximumScrollY: Math.max(0, document.documentElement.scrollHeight - window.innerHeight),
  }));
  expect(position.maximumScrollY).toBeGreaterThan(0);
  expect(position.scrollY).toBeGreaterThan(0);
  await expect(deepTarget).toBeInViewport();
  await testInfo.attach(`persisted-artifact-deep-scroll-${testInfo.project.name}`, {
    body: await page.screenshot({ animations: "disabled" }),
    contentType: "image/png",
  });
}

function formatPercent(value: number) {
  return (value * 100).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}
