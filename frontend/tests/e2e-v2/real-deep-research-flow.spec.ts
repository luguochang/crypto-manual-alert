import {
  expect,
  test,
  type Page,
  type Request as PlaywrightRequest,
  type Response as PlaywrightResponse,
  type TestInfo,
} from "@playwright/test";
import axe from "axe-core";
import { isIP } from "node:net";
import path from "node:path";

import {
  productTaskSchema,
  type DeepResearchArtifact,
  type ProductTask,
} from "../../src/lib/schemas/product-api";

const admissionPath = "/api/product/api/v2/deep-research";
const uuidSource =
  "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const uuidPattern = new RegExp(`^${uuidSource}$`, "i");
const taskProjectionPathPattern = new RegExp(
  `^/api/product/api/v2/tasks/(${uuidSource})(?:/interrupts/respond-all)?$`,
  "i",
);
const officialAgentReadPattern = new RegExp(
  `^/api/agent/threads/(${uuidSource})/(state|history|stream/events)$`,
  "i",
);
const mutationMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const approvedResearchProviders = new Set([
  "openai_builtin_web_search",
  "tavily",
]);
const terminalStatuses = new Set([
  "succeeded",
  "blocked",
  "failed",
  "cancelled",
]);
const expectedViewports: Record<string, { width: number; height: number }> = {
  "fixture-desktop": { width: 1440, height: 1000 },
  "fixture-pixel-7": { width: 412, height: 915 },
};
const realDeepResearchAdmissionTimeoutMs = 300_000;

const editedSummary =
  "截至本次人工复核，BTC 的宏观流动性、监管进展与现货/衍生品市场结构信号仍需联合解读；结论仅保留可由下列真实来源验证的部分。";
const editedSectionSummary =
  "人工复核保留原有引文，并明确区分已验证事实、推断与反证。";
const editedRiskNote = "未来 7 天宏观数据和监管公告可能迅速改变结论。";
const editedEvidenceGap =
  "尚缺少跨交易所逐笔订单流与场外市场的同步可验证数据。";

const evidenceDirectory = process.env.PLAYWRIGHT_EVIDENCE_DIR?.trim() ?? "";
const realEnvironmentReady =
  process.env.V2_E2E_PROFILE === "real-deep-research" &&
  process.env.REAL_PRODUCT_E2E === "1" &&
  process.env.REAL_DEEP_RESEARCH_E2E === "1" &&
  evidenceDirectory.length > 0 &&
  path.isAbsolute(evidenceDirectory);

test.skip(
  !realEnvironmentReady,
  "requires V2_E2E_PROFILE=real-deep-research, REAL_PRODUCT_E2E=1, REAL_DEEP_RESEARCH_E2E=1, and an absolute PLAYWRIGHT_EVIDENCE_DIR",
);

test("runs real Deep Research admission, recovery, edit, second review, and approval", async ({
  page,
}, testInfo) => {
  test.setTimeout(900_000);
  page.setDefaultTimeout(30_000);
  assertExecutionEnvironment(page, testInfo);

  const observer = installFlowObserver(page);
  const currentDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const researchQuestion = [
    `截至 ${currentDate}，研究 BTC 未来 7 天的当前状态：`,
    "宏观流动性与关键数据、美国及全球监管进展、现货与衍生品市场结构。",
    "请区分已验证事实、推断和反证，说明证据缺口，并仅引用可核验的真实 HTTPS 来源。",
  ].join("");

  await page.goto("/work");
  await page.getByRole("radio", { name: "深度研究", exact: true }).check();
  await page.getByLabel("研究范围").selectOption("7d");
  await page.getByLabel("研究问题", { exact: true }).fill(researchQuestion);
  await expect(
    page.getByRole("button", { name: "开始深度研究", exact: true }),
  ).toBeEnabled();

  const admissionResponsePromise = page.waitForResponse(
    (response) => isResponseFor(response, "POST", admissionPath),
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: "开始深度研究", exact: true }).click();

  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.status()).toBe(202);
  const admittedTask = await parseTask(admissionResponse);
  assertResearchTaskIdentity(admittedTask, {
    query: researchQuestion,
    status: ["queued", "running", "waiting_human"],
  });
  const taskId = admittedTask.task_id.toLowerCase();
  const taskPath = `/api/product/api/v2/tasks/${taskId}`;
  const respondPath = `${taskPath}/interrupts/respond-all`;

  await expect
    .poll(() => new URL(page.url()).searchParams.get("task"), {
      timeout: 30_000,
    })
    .toBe(taskId);
  expect(new URL(page.url()).pathname).toBe("/work");
  assertAdmissionRequest(observer, researchQuestion);

  const pendingTask = await waitForTaskOutcome(
    page,
    observer,
    taskId,
    (task) =>
      isReloadablePreApprovalState(task) &&
      task.agent_stream !== null &&
      task.stage_history !== null &&
      task.stage_history !== undefined &&
      task.stage_history.stages.length > 0,
    realDeepResearchAdmissionTimeoutMs,
  );
  await failOnUnexpectedTerminal(
    page,
    observer,
    pendingTask,
    "before-pending-reload",
    testInfo,
  );
  if (!isReloadablePreApprovalState(pendingTask)) {
    await failWithUnexpectedProjection(
      page,
      observer,
      pendingTask,
      "invalid-state-before-reload",
      testInfo,
    );
  }
  const pendingRuntime = requireRuntimeIdentity(pendingTask);
  const pendingProductRunId = requireProductRunIdentity(pendingTask);
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    /^(?:研究已排队|深度研究进行中|等待人工确认)$/,
    { timeout: 30_000 },
  );
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    recoveryCheckpointLabel("before-reload", pendingTask),
    pendingTask,
  );

  await settleProjectionInspections(observer);
  const reloadCandidate = latestProjectionForTask(observer, taskId);
  if (reloadCandidate === undefined) {
    throw new Error(
      `no Product projection remained available for pending reload of ${taskId}`,
    );
  }
  await failOnUnexpectedTerminal(
    page,
    observer,
    reloadCandidate,
    "immediately-before-pending-reload",
    testInfo,
  );
  if (!isReloadablePreApprovalState(reloadCandidate)) {
    await failWithUnexpectedProjection(
      page,
      observer,
      reloadCandidate,
      "invalid-state-immediately-before-reload",
      testInfo,
    );
  }
  expect(requireRuntimeIdentity(reloadCandidate)).toEqual(pendingRuntime);
  expect(requireProductRunIdentity(reloadCandidate)).toBe(pendingProductRunId);

  const taskUrl = page.url();
  const recoveryProjectionStart = observer.productProjections.length;
  const admissionCountBeforeReload = admissionRequests(observer).length;
  await page.reload();
  await expect(page).toHaveURL(taskUrl);

  const recoveredTask = await waitForTaskOutcome(
    page,
    observer,
    taskId,
    (task) =>
      isReloadablePreApprovalState(task) &&
      task.agent_stream !== null &&
      task.stage_history !== null &&
      task.stage_history !== undefined &&
      task.stage_history.stages.length > 0,
    30_000,
    recoveryProjectionStart,
  );
  await failOnUnexpectedTerminal(
    page,
    observer,
    recoveredTask,
    "during-pending-recovery",
    testInfo,
  );
  expect(recoveredTask.task_id.toLowerCase()).toBe(taskId);
  expect(requireRuntimeIdentity(recoveredTask)).toEqual(pendingRuntime);
  expect(requireProductRunIdentity(recoveredTask)).toBe(pendingProductRunId);
  if (!isReloadablePreApprovalState(recoveredTask)) {
    await failWithUnexpectedProjection(
      page,
      observer,
      recoveredTask,
      "invalid-state-after-reload",
      testInfo,
    );
  }
  expect(admissionRequests(observer)).toHaveLength(admissionCountBeforeReload);
  expect(admissionRequests(observer)).toHaveLength(1);
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    recoveryCheckpointLabel("recovered", recoveredTask),
    recoveredTask,
  );

  const firstReview = await waitForTaskOutcome(
    page,
    observer,
    taskId,
    (task) => reviewIteration(task) === 1,
    480_000,
  );
  await requireExpectedStatus(
    page,
    observer,
    firstReview,
    "waiting_human",
    "first-review",
    testInfo,
  );
  const firstArtifact = assertReviewProjection(firstReview, taskId, 1);
  const sourceSignature = researchSourceSignature(firstArtifact);
  await assertReviewDom(page, firstArtifact);
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    "review-round-1",
    firstReview,
  );

  await page.getByRole("button", { name: "修改后重审", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "修改研究报告", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "执行摘要", exact: true })
    .fill(editedSummary);
  const firstSectionEditor = page.getByRole("region", {
    name: "研究章节 1",
    exact: true,
  });
  await firstSectionEditor
    .getByRole("textbox", { name: "章节摘要", exact: true })
    .fill(editedSectionSummary);
  await page
    .getByRole("textbox", { name: "风险提示（每行一项）", exact: true })
    .fill(editedRiskNote);
  await page
    .getByRole("textbox", { name: "证据缺口（每行一项）", exact: true })
    .fill(editedEvidenceGap);
  await page
    .getByRole("textbox", { name: "修改说明（可选）", exact: true })
    .fill("收窄结论，保留原始来源目录和引用关系，并明确风险与证据缺口。");
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    "report-edit-prepared",
    firstReview,
  );

  const editResponsePromise = page.waitForResponse(
    (response) => isResponseFor(response, "POST", respondPath),
    { timeout: 30_000 },
  );
  const secondReviewProjectionStart = observer.productProjections.length;
  await page
    .getByRole("button", { name: "提交修改并重审", exact: true })
    .click();
  expect((await editResponsePromise).status()).toBe(202);

  const secondReview = await waitForTaskOutcome(
    page,
    observer,
    taskId,
    (task) => reviewIteration(task) === 2,
    240_000,
    secondReviewProjectionStart,
  );
  await requireExpectedStatus(
    page,
    observer,
    secondReview,
    "waiting_human",
    "second-review",
    testInfo,
  );
  const secondArtifact = assertReviewProjection(secondReview, taskId, 2);
  expect(researchSourceSignature(secondArtifact)).toBe(sourceSignature);
  assertEditedReport(secondArtifact);
  await assertReviewDom(page, secondArtifact);
  await expect(page.getByText(editedSummary, { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    "review-round-2",
    secondReview,
  );

  await page.getByRole("button", { name: "批准", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "确认批准这份研究报告？",
      exact: true,
    }),
  ).toBeVisible();
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    "approval-confirmation",
    secondReview,
  );

  const approvalResponsePromise = page.waitForResponse(
    (response) => isResponseFor(response, "POST", respondPath),
    { timeout: 30_000 },
  );
  const succeededProjectionStart = observer.productProjections.length;
  await page.getByRole("button", { name: "确认批准", exact: true }).click();
  expect((await approvalResponsePromise).status()).toBe(202);

  const succeededTask = await waitForTaskOutcome(
    page,
    observer,
    taskId,
    (task) => task.status === "succeeded",
    240_000,
    succeededProjectionStart,
  );
  await requireExpectedStatus(
    page,
    observer,
    succeededTask,
    "succeeded",
    "committed-report",
    testInfo,
  );
  const committedArtifact = succeededTask.deep_research_artifact;
  if (committedArtifact === null) {
    throw new Error(
      "succeeded Deep Research Task did not contain a committed report",
    );
  }
  expect(committedArtifact.status).toBe("committed");
  expect(committedArtifact.harness_mode).toBe("deepagents");
  expect(researchSourceSignature(committedArtifact)).toBe(sourceSignature);
  assertEditedReport(committedArtifact);
  assertRealResearchSources(committedArtifact);
  assertRealWebEvidence(succeededTask.web_evidence, "task.web_evidence");

  await expect(
    page.getByRole("heading", {
      name: "深度研究已完成",
      exact: true,
    }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
  await expect(page.getByText(editedSummary, { exact: true })).toBeVisible();
  await assertCommittedReportDom(page, committedArtifact);
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    "committed-report",
    succeededTask,
  );

  const committedRuntime = requireRuntimeIdentity(succeededTask);
  const committedProductRunId = requireProductRunIdentity(succeededTask);
  const terminalProjectionStart = observer.productProjections.length;
  const terminalUrl = page.url();
  await page.reload();
  await expect(page).toHaveURL(terminalUrl);
  const reloadedTask = await waitForTaskOutcome(
    page,
    observer,
    taskId,
    (task) => task.status === "succeeded",
    30_000,
    terminalProjectionStart,
  );
  expect(reloadedTask.deep_research_artifact).toEqual(committedArtifact);
  expect(requireRuntimeIdentity(reloadedTask)).toEqual(committedRuntime);
  expect(requireProductRunIdentity(reloadedTask)).toBe(committedProductRunId);
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
  await expect(page.getByText(editedSummary, { exact: true })).toBeVisible();
  await assertCommittedReportDom(page, committedArtifact);
  await captureCheckpoint(
    page,
    observer,
    testInfo,
    "committed-report-reloaded",
    reloadedTask,
  );

  assertReviewRequests(observer, respondPath);
  assertBrowserRequestBoundary(
    observer,
    admissionPath,
    respondPath,
    pendingRuntime.thread_id,
  );
});

interface ObservedRequest {
  method: string;
  pathname: string;
  body: unknown;
}

interface ProductProjectionObservation {
  method: string;
  pathname: string;
  task: ProductTask;
}

interface FlowObserver {
  requests: ObservedRequest[];
  consoleErrors: string[];
  pageErrors: string[];
  serverErrors: string[];
  productResponseErrors: string[];
  projectionInspections: Set<Promise<void>>;
  productProjections: ProductProjectionObservation[];
}

function assertExecutionEnvironment(page: Page, testInfo: TestInfo) {
  expect(process.env.V2_E2E_PROFILE).toBe("real-deep-research");
  expect(process.env.REAL_PRODUCT_E2E).toBe("1");
  expect(process.env.REAL_DEEP_RESEARCH_E2E).toBe("1");
  expect(evidenceDirectory.length).toBeGreaterThan(0);
  expect(path.isAbsolute(evidenceDirectory)).toBe(true);

  const expectedViewport = expectedViewports[testInfo.project.name];
  if (expectedViewport === undefined) {
    throw new Error(
      `real Deep Research must run in both configured viewport projects; unsupported project ${testInfo.project.name}`,
    );
  }
  expect(page.viewportSize()).toEqual(expectedViewport);
}

function installFlowObserver(page: Page): FlowObserver {
  const observer: FlowObserver = {
    requests: [],
    consoleErrors: [],
    pageErrors: [],
    serverErrors: [],
    productResponseErrors: [],
    projectionInspections: new Set(),
    productProjections: [],
  };

  page.on("request", (request) => {
    observer.requests.push(observedRequest(request));
  });
  page.on("console", (message) => {
    if (message.type() === "error") observer.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => observer.pageErrors.push(error.message));
  page.on("response", (response) => {
    const request = observedRequest(response.request());
    if (response.status() >= 500) {
      observer.serverErrors.push(
        `${response.status()} ${request.method} ${request.pathname}`,
      );
    }
    if (!isProductProjectionResponse(response, request.pathname)) return;

    const inspection = inspectProductProjection(
      response,
      request,
      observer,
    ).catch((error: unknown) => {
      observer.productResponseErrors.push(
        `${request.method} ${request.pathname}: ${readErrorMessage(error)}`,
      );
    });
    observer.projectionInspections.add(inspection);
    void inspection.then(() =>
      observer.projectionInspections.delete(inspection),
    );
  });

  return observer;
}

function observedRequest(request: PlaywrightRequest): ObservedRequest {
  let body: unknown = null;
  if (request.postData() !== null) {
    try {
      body = request.postDataJSON();
    } catch {
      body = request.postData();
    }
  }
  return {
    method: request.method().toUpperCase(),
    pathname: new URL(request.url()).pathname,
    body,
  };
}

function isProductProjectionResponse(
  response: PlaywrightResponse,
  pathname: string,
) {
  if (!response.ok()) return false;
  if (pathname !== admissionPath && !taskProjectionPathPattern.test(pathname))
    return false;
  return (
    response.headers()["content-type"]?.includes("application/json") ?? false
  );
}

async function inspectProductProjection(
  response: PlaywrightResponse,
  request: ObservedRequest,
  observer: FlowObserver,
) {
  const task = productTaskSchema.parse(await response.json());
  observer.productProjections.push({
    method: request.method,
    pathname: request.pathname,
    task,
  });
}

async function settleProjectionInspections(observer: FlowObserver) {
  while (observer.projectionInspections.size > 0) {
    await Promise.all([...observer.projectionInspections]);
  }
}

async function parseTask(response: PlaywrightResponse) {
  return productTaskSchema.parse(await response.json());
}

function isResponseFor(
  response: PlaywrightResponse,
  method: string,
  pathname: string,
) {
  const request = response.request();
  return (
    request.method().toUpperCase() === method &&
    new URL(request.url()).pathname === pathname
  );
}

async function waitForTaskOutcome(
  page: Page,
  observer: FlowObserver,
  taskId: string,
  expected: (task: ProductTask) => boolean,
  timeoutMs: number,
  startIndex = 0,
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await settleProjectionInspections(observer);
    expect(observer.productResponseErrors).toEqual([]);
    const observations = observer.productProjections
      .slice(startIndex)
      .filter((item) => item.task.task_id.toLowerCase() === taskId);
    const latest = observations.at(-1);
    if (latest !== undefined && terminalStatuses.has(latest.task.status)) {
      return latest.task;
    }
    if (latest !== undefined && expected(latest.task)) return latest.task;
    await page.waitForTimeout(200);
  }

  const last = observer.productProjections.findLast(
    (item) => item.task.task_id.toLowerCase() === taskId,
  )?.task;
  throw new Error(
    `timed out waiting for real Deep Research Task ${taskId}; last status was ${last?.status ?? "unobserved"}`,
  );
}

function assertResearchTaskIdentity(
  task: ProductTask,
  expected: { query: string; status: ProductTask["status"][] },
) {
  expect(task.task_id).toMatch(uuidPattern);
  expect(task.correlation_id).toMatch(uuidPattern);
  expect(task.task_type).toBe("deep_research");
  expect(task.symbol).toBe("BTC-USDT-SWAP");
  expect(task.horizon).toBe("7d");
  expect(task.query_text).toBe(expected.query);
  expect(expected.status).toContain(task.status);
}

function requireRuntimeIdentity(task: ProductTask) {
  const binding = task.agent_stream;
  if (binding === null) {
    throw new Error(
      `Task ${task.task_id} ${task.status} projection has no official Run identity`,
    );
  }
  expect(binding.protocol).toBe("langgraph-v2");
  expect(binding.assistant_id).toMatch(uuidPattern);
  expect(binding.thread_id).toMatch(uuidPattern);
  expect(binding.run_id).toMatch(uuidPattern);
  return binding;
}

function requireProductRunIdentity(task: ProductTask) {
  const history = task.stage_history;
  if (
    history === null ||
    history === undefined ||
    history.stages.length === 0
  ) {
    throw new Error(
      `Task ${task.task_id} ${task.status} projection has no durable Run history`,
    );
  }
  expect(history.run_id).toMatch(uuidPattern);
  return history.run_id.toLowerCase();
}

function reviewIteration(task: ProductTask) {
  if (task.status !== "waiting_human") return null;
  const member = task.pending_interrupts?.members[0];
  return member?.payload.kind === "deep_research_review"
    ? member.payload.review_iteration
    : null;
}

function isPendingExecution(task: ProductTask) {
  return task.status === "queued" || task.status === "running";
}

function isReloadablePreApprovalState(task: ProductTask) {
  return isPendingExecution(task) || reviewIteration(task) === 1;
}

function recoveryCheckpointLabel(
  phase: "before-reload" | "recovered",
  task: ProductTask,
) {
  return `${isPendingExecution(task) ? "pending" : "review-round-1"}-${phase}`;
}

function assertReviewProjection(
  task: ProductTask,
  taskId: string,
  iteration: number,
) {
  expect(task.task_id.toLowerCase()).toBe(taskId);
  expect(task.task_type).toBe("deep_research");
  expect(task.status).toBe("waiting_human");
  expect(task.symbol).toBe("BTC-USDT-SWAP");
  expect(task.horizon).toBe("7d");
  requireRuntimeIdentity(task);

  const pause = task.pending_interrupts;
  if (pause === null || pause === undefined) {
    throw new Error(
      `review round ${iteration} did not contain an active Product pause`,
    );
  }
  expect(pause.status).toBe("pending");
  expect(pause.members).toHaveLength(1);
  const member = pause.members[0];
  if (member === undefined || member.payload.kind !== "deep_research_review") {
    throw new Error(
      `review round ${iteration} did not contain a Deep Research review`,
    );
  }
  expect(member.status).toBe("pending");
  expect(member.payload.review_iteration).toBe(iteration);
  expect(member.payload.symbol).toBe("BTC-USDT-SWAP");
  expect(member.payload.horizon).toBe("7d");
  expect(member.payload.artifact.status).toBe("draft");
  expect(member.payload.artifact.harness_mode).toBe("deepagents");
  assertRealResearchSources(member.payload.artifact);
  assertRealWebEvidence(task.web_evidence, "task.web_evidence");
  return member.payload.artifact;
}

function assertRealResearchSources(artifact: DeepResearchArtifact) {
  expect(artifact.sources.length).toBeGreaterThan(0);
  expect(artifact.sources.map((source) => source.index)).toEqual(
    artifact.sources.map((_, index) => index + 1),
  );
  assertRealWebEvidence(
    artifact.sources.map((source) => source.evidence),
    "deep_research_artifact.sources",
  );
}

function assertRealWebEvidence(
  evidenceItems: ProductTask["web_evidence"],
  pathLabel: string,
) {
  expect(
    evidenceItems.length,
    `${pathLabel} must not be empty`,
  ).toBeGreaterThan(0);
  for (const [index, evidence] of evidenceItems.entries()) {
    const itemPath = `${pathLabel}[${index}]`;
    expect(
      approvedResearchProviders.has(evidence.source),
      `${itemPath}.source must be openai_builtin_web_search or tavily`,
    ).toBe(true);
    expect(
      isPublicHttpsUrl(evidence.final_url),
      `${itemPath}.final_url must be real public HTTPS`,
    ).toBe(true);
    expect(
      evidence.title.trim().length,
      `${itemPath}.title must be non-empty`,
    ).toBeGreaterThan(0);
    expect(
      evidence.excerpt.trim().length,
      `${itemPath}.excerpt must be non-empty`,
    ).toBeGreaterThan(0);
    expect(
      evidence.content_hash.trim().length,
      `${itemPath}.content_hash must be non-empty`,
    ).toBeGreaterThan(0);
  }
}

function researchSourceSignature(artifact: DeepResearchArtifact) {
  return JSON.stringify(
    artifact.sources.map((source) => ({
      index: source.index,
      title: source.evidence.title,
      final_url: source.evidence.final_url,
      source: source.evidence.source,
      content_hash: source.evidence.content_hash,
    })),
  );
}

function assertEditedReport(artifact: DeepResearchArtifact) {
  expect(artifact.report.executive_summary).toBe(editedSummary);
  expect(artifact.report.sections[0]?.summary).toBe(editedSectionSummary);
  expect(artifact.report.risk_notes).toEqual([editedRiskNote]);
  expect(artifact.report.evidence_gaps).toEqual([editedEvidenceGap]);
}

async function assertReviewDom(page: Page, artifact: DeepResearchArtifact) {
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    "等待人工确认",
    { timeout: 30_000 },
  );
  const panel = page.locator("section.hitl-review-panel");
  await expect(panel).toHaveCount(1);
  await expect(panel.getByRole("heading", { level: 2 })).toContainText(
    "研究报告草稿待人工确认",
  );
  await expect(panel.getByText("Deep Agents", { exact: true })).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "批准", exact: true }),
  ).toBeEnabled();
  await expect(
    panel.getByRole("button", { name: "拒绝", exact: true }),
  ).toBeEnabled();
  await expect(
    panel.getByRole("button", { name: "修改后重审", exact: true }),
  ).toBeEnabled();

  const sourceLinks = panel.locator(".hitl-review-sources a[href]");
  await expect(sourceLinks).toHaveCount(artifact.sources.length);
  for (let index = 0; index < artifact.sources.length; index += 1) {
    const href = await sourceLinks.nth(index).getAttribute("href");
    expect(href).not.toBeNull();
    expect(isPublicHttpsUrl(href ?? "")).toBe(true);
  }
}

async function assertCommittedReportDom(
  page: Page,
  artifact: DeepResearchArtifact,
) {
  const report = page.locator("article.deep-research-report");
  await expect(report).toBeVisible();
  await expect(
    report.getByRole("heading", { name: "研究结论", exact: true }),
  ).toBeVisible();
  await expect(report.getByText("Deep Agents", { exact: true })).toBeVisible();
  const sources = report.locator(".deep-research-sources a[href]");
  await expect(sources).toHaveCount(artifact.sources.length);
  for (const [index, source] of artifact.sources.entries()) {
    await expect(sources.nth(index)).toHaveAttribute(
      "href",
      source.evidence.final_url,
    );
  }
}

async function requireExpectedStatus(
  page: Page,
  observer: FlowObserver,
  task: ProductTask,
  expected: ProductTask["status"],
  phase: string,
  testInfo: TestInfo,
) {
  if (task.status === expected) return;
  if (task.status === "failed") {
    await failWithTypedProductFailure(page, observer, task, phase, testInfo);
  }
  await failWithUnexpectedProjection(page, observer, task, phase, testInfo);
}

async function failOnUnexpectedTerminal(
  page: Page,
  observer: FlowObserver,
  task: ProductTask,
  phase: string,
  testInfo: TestInfo,
) {
  if (!terminalStatuses.has(task.status)) return;
  if (task.status === "failed") {
    await failWithTypedProductFailure(page, observer, task, phase, testInfo);
  }
  await failWithUnexpectedProjection(page, observer, task, phase, testInfo);
}

async function failWithTypedProductFailure(
  page: Page,
  observer: FlowObserver,
  task: ProductTask,
  phase: string,
  testInfo: TestInfo,
): Promise<never> {
  expect(task.status).toBe("failed");
  expect(task.errors.length).toBeGreaterThan(0);
  const failurePanel = page.locator("section.failure-panel[role='alert']");
  await expect(failurePanel).toBeVisible({ timeout: 30_000 });
  await expect(
    failurePanel.getByRole("heading", { name: "研究报告未生成", exact: true }),
  ).toBeVisible();
  const firstError = task.errors[0];
  if (firstError === undefined)
    throw new Error("failed Product Task has no typed error");
  await expect(
    failurePanel.getByText(firstError.message, { exact: true }),
  ).toBeVisible();
  const disclosure = failurePanel.locator(
    "details.failure-diagnostics-disclosure",
  );
  if (!(await disclosure.getAttribute("open"))) {
    await disclosure.getByText("查看失败诊断", { exact: true }).click();
  }
  await expect(
    failurePanel.getByText(firstError.code, { exact: true }),
  ).toBeVisible();
  const visibleFailure = (await failurePanel.innerText())
    .replace(/\s+/g, " ")
    .trim();

  await settleProjectionInspections(observer);
  const lastProjection =
    latestProjectionForTask(observer, task.task_id) ?? task;
  await testInfo.attach(`typed-visible-failure-${phase}`, {
    body: Buffer.from(
      JSON.stringify(
        {
          task_id: task.task_id,
          status: task.status,
          correlation_id: task.correlation_id,
          visible_failure: visibleFailure,
          errors: task.errors,
        },
        null,
        2,
      ),
    ),
    contentType: "application/json",
  });
  await testInfo.attach(`last-product-projection-${phase}`, {
    body: Buffer.from(JSON.stringify(lastProjection, null, 2)),
    contentType: "application/json",
  });

  let qualityFailure: string | null = null;
  try {
    await captureCheckpoint(page, observer, testInfo, `failed-${phase}`, task);
  } catch (error) {
    qualityFailure = readErrorMessage(error);
  }
  throw new Error(
    `Real Deep Research failed during ${phase}: ${visibleFailure}${
      qualityFailure === null ? "" : `; quality scan: ${qualityFailure}`
    }`,
  );
}

async function failWithUnexpectedProjection(
  page: Page,
  observer: FlowObserver,
  task: ProductTask,
  phase: string,
  testInfo: TestInfo,
): Promise<never> {
  await testInfo.attach(`unexpected-product-projection-${phase}`, {
    body: Buffer.from(JSON.stringify(task, null, 2)),
    contentType: "application/json",
  });
  let qualityFailure: string | null = null;
  try {
    await captureCheckpoint(
      page,
      observer,
      testInfo,
      `unexpected-${phase}`,
      task,
    );
  } catch (error) {
    qualityFailure = readErrorMessage(error);
  }
  throw new Error(
    `Real Deep Research reached unexpected status ${task.status} during ${phase}${
      qualityFailure === null ? "" : `; quality scan: ${qualityFailure}`
    }`,
  );
}

function latestProjectionForTask(observer: FlowObserver, taskId: string) {
  return observer.productProjections.findLast(
    (item) => item.task.task_id.toLowerCase() === taskId.toLowerCase(),
  )?.task;
}

async function captureCheckpoint(
  page: Page,
  observer: FlowObserver,
  testInfo: TestInfo,
  label: string,
  task: ProductTask,
) {
  await settleProjectionInspections(observer);
  if (!(await page.evaluate(() => "axe" in window))) {
    await page.addScriptTag({ content: axe.source });
  }
  const audit = await page.evaluate(async () => {
    const result = await (
      window as typeof window & { axe: typeof axe }
    ).axe.run();
    const ids = Array.from(document.querySelectorAll<HTMLElement>("[id]"))
      .map((element) => element.id)
      .filter(Boolean);
    const idCounts = new Map<string, number>();
    for (const id of ids) idCounts.set(id, (idCounts.get(id) ?? 0) + 1);

    const controls = Array.from(
      document.querySelectorAll<HTMLElement>(
        "button, a[href], input:not([type='hidden']), select, textarea",
      ),
    ).filter((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        element.getClientRects().length > 0 &&
        rect.width > 0 &&
        rect.height > 0 &&
        style.display !== "none" &&
        style.visibility !== "hidden"
      );
    });
    const unnamedControls = controls
      .filter((element) => {
        const labelledBy = (element.getAttribute("aria-labelledby") ?? "")
          .split(/\s+/)
          .filter(Boolean)
          .map((id) => document.getElementById(id)?.textContent ?? "")
          .join(" ");
        const labels =
          "labels" in element
            ? Array.from((element as HTMLInputElement).labels ?? [])
                .map((item) => item.textContent ?? "")
                .join(" ")
            : "";
        return ![
          element.getAttribute("aria-label"),
          labelledBy,
          labels,
          element.getAttribute("title"),
          element.getAttribute("alt"),
          element.textContent,
        ].some((value) => (value ?? "").trim().length > 0);
      })
      .map((element) => element.outerHTML.slice(0, 240));
    const root = document.documentElement;
    const visibleText = document.body.innerText;

    return {
      violations: result.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        nodes: violation.nodes.map((node) => ({
          target: node.target,
          failureSummary: node.failureSummary,
        })),
      })),
      duplicateIds: [...idCounts.entries()]
        .filter(([, count]) => count > 1)
        .map(([id]) => id),
      unnamedControls,
      horizontalOverflow:
        Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0) -
        root.clientWidth,
      rawJson:
        document.querySelectorAll("pre").length > 0 ||
        visibleText.includes("Raw JSON") ||
        /"(?:task_id|deep_research_artifact|artifact_type|source_indexes|agent_stream)"\s*:/.test(
          visibleText,
        ),
    };
  });
  const diagnostics = {
    ...audit,
    consoleErrors: [...observer.consoleErrors],
    pageErrors: [...observer.pageErrors],
    serverErrors: [...observer.serverErrors],
    productResponseErrors: [...observer.productResponseErrors],
  };

  await testInfo.attach(`${label}-full-page`, {
    body: await page.screenshot({ fullPage: true, animations: "disabled" }),
    contentType: "image/png",
  });
  await testInfo.attach(`${label}-task-identity`, {
    body: Buffer.from(JSON.stringify(taskIdentityEvidence(task), null, 2)),
    contentType: "application/json",
  });
  await testInfo.attach(`${label}-quality-scan`, {
    body: Buffer.from(JSON.stringify(diagnostics, null, 2)),
    contentType: "application/json",
  });

  expect(audit.violations, `${label} axe violations`).toEqual([]);
  expect(audit.duplicateIds, `${label} duplicate IDs`).toEqual([]);
  expect(audit.unnamedControls, `${label} unnamed controls`).toEqual([]);
  expect(
    audit.horizontalOverflow,
    `${label} horizontal overflow`,
  ).toBeLessThanOrEqual(0);
  expect(audit.rawJson, `${label} exposed raw JSON`).toBe(false);
  expect(observer.consoleErrors, `${label} console errors`).toEqual([]);
  expect(observer.pageErrors, `${label} page errors`).toEqual([]);
  expect(observer.serverErrors, `${label} HTTP 5xx responses`).toEqual([]);
  expect(
    observer.productResponseErrors,
    `${label} invalid Product projections`,
  ).toEqual([]);
}

function taskIdentityEvidence(task: ProductTask) {
  const member = task.pending_interrupts?.members[0];
  const researchPayload =
    member?.payload.kind === "deep_research_review" ? member.payload : null;
  const artifact =
    task.deep_research_artifact ?? researchPayload?.artifact ?? null;
  return {
    task_id: task.task_id,
    correlation_id: task.correlation_id,
    task_type: task.task_type,
    status: task.status,
    symbol: task.symbol,
    horizon: task.horizon,
    agent_stream: task.agent_stream,
    stage_run_id: task.stage_history?.run_id ?? null,
    projection_scope: task.projection_scope,
    pause_id: task.pending_interrupts?.pause_id ?? null,
    pause_version: task.pending_interrupts?.pause_version ?? null,
    review_iteration: researchPayload?.review_iteration ?? null,
    artifact_status: artifact?.status ?? null,
    harness_mode: artifact?.harness_mode ?? null,
    sources:
      artifact?.sources.map((source) => ({
        index: source.index,
        source: source.evidence.source,
        final_url: source.evidence.final_url,
      })) ?? [],
  };
}

function assertAdmissionRequest(observer: FlowObserver, query: string) {
  const admissions = admissionRequests(observer);
  expect(admissions).toHaveLength(1);
  expect(admissions[0]?.body).toEqual({
    task_type: "deep_research",
    symbol: "BTC-USDT-SWAP",
    horizon: "7d",
    query_text: query,
  });
}

function admissionRequests(observer: FlowObserver) {
  return observer.requests.filter(
    (request) =>
      request.method === "POST" && request.pathname === admissionPath,
  );
}

function assertReviewRequests(observer: FlowObserver, respondPath: string) {
  const reviewRequests = observer.requests.filter(
    (request) => request.method === "POST" && request.pathname === respondPath,
  );
  expect(reviewRequests).toHaveLength(2);
  expect(readReviewAction(reviewRequests[0]?.body)).toBe("edit");
  expect(readReviewAction(reviewRequests[1]?.body)).toBe("approve");
}

function readReviewAction(body: unknown) {
  if (!isRecord(body) || !Array.isArray(body.responses)) return null;
  const first = body.responses[0];
  if (!isRecord(first) || !isRecord(first.response)) return null;
  return typeof first.response.action === "string"
    ? first.response.action
    : null;
}

function assertBrowserRequestBoundary(
  observer: FlowObserver,
  expectedAdmissionPath: string,
  expectedRespondPath: string,
  expectedThreadId: string,
) {
  const agentRequests = observer.requests.filter((request) =>
    request.pathname.startsWith("/api/agent/"),
  );
  const forbiddenAgentRequests = agentRequests.filter(
    (request) => officialAgentRead(request) === null,
  );
  expect(
    forbiddenAgentRequests.map(formatRequest),
    "forbidden /api/agent browser request",
  ).toEqual([]);

  const officialReads = agentRequests.flatMap((request) => {
    const read = officialAgentRead(request);
    return read === null ? [] : [read];
  });
  expect(officialReads.length).toBeGreaterThan(0);
  expect(
    officialReads.every(
      (read) => read.threadId === expectedThreadId.toLowerCase(),
    ),
  ).toBe(true);
  expect(officialReads.some((read) => read.kind === "state")).toBe(true);
  expect(officialReads.some((read) => read.kind === "history")).toBe(true);
  expect(officialReads.some((read) => read.kind === "events")).toBe(true);

  const businessMutations = observer.requests.filter(
    (request) =>
      mutationMethods.has(request.method) &&
      officialAgentRead(request) === null,
  );
  expect(
    businessMutations.every((request) =>
      request.pathname.startsWith("/api/product/"),
    ),
    "all browser business writes must use the Product BFF",
  ).toBe(true);
  expect(
    businessMutations.map((request) => `${request.method} ${request.pathname}`),
  ).toEqual([
    `POST ${expectedAdmissionPath}`,
    `POST ${expectedRespondPath}`,
    `POST ${expectedRespondPath}`,
  ]);
  expect(admissionRequests(observer)).toHaveLength(1);
  expect(observer.serverErrors).toEqual([]);
  expect(observer.consoleErrors).toEqual([]);
  expect(observer.pageErrors).toEqual([]);
  expect(observer.productResponseErrors).toEqual([]);
}

function officialAgentRead(request: ObservedRequest) {
  const match = officialAgentReadPattern.exec(request.pathname);
  const threadId = match?.[1];
  const endpoint = match?.[2];
  if (threadId === undefined || endpoint === undefined) return null;
  const expectedMethod = endpoint === "state" ? "GET" : "POST";
  if (request.method !== expectedMethod) return null;
  return {
    kind:
      endpoint === "stream/events"
        ? "events"
        : (endpoint as "state" | "history"),
    threadId: threadId.toLowerCase(),
  };
}

function formatRequest(request: ObservedRequest) {
  return `${request.method} ${request.pathname}`;
}

function isPublicHttpsUrl(value: string) {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.protocol !== "https:" || url.username || url.password) return false;

  const hostname = url.hostname
    .toLowerCase()
    .replace(/^\[|\]$/g, "")
    .replace(/\.$/, "");
  if (!hostname || reservedHostname(hostname)) return false;
  const ipVersion = isIP(hostname);
  if (ipVersion === 4) return isPublicIpv4(hostname);
  if (ipVersion === 6) {
    return /^[23]/i.test(hostname) && !hostname.startsWith("2001:db8:");
  }
  return hostname.includes(".");
}

function reservedHostname(hostname: string) {
  if (
    ["example.com", "example.net", "example.org"].some(
      (domain) => hostname === domain || hostname.endsWith(`.${domain}`),
    )
  )
    return true;
  return [
    "localhost",
    ".localhost",
    ".local",
    ".internal",
    ".test",
    ".invalid",
    ".example",
    ".home",
    ".lan",
  ].some(
    (suffix) =>
      hostname === suffix.replace(/^\./, "") || hostname.endsWith(suffix),
  );
}

function isPublicIpv4(hostname: string) {
  const [first = 0, second = 0, third = 0] = hostname.split(".").map(Number);
  if (first === 0 || first === 10 || first === 127 || first >= 224)
    return false;
  if (first === 100 && second >= 64 && second <= 127) return false;
  if (first === 169 && second === 254) return false;
  if (first === 172 && second >= 16 && second <= 31) return false;
  if (first === 192 && second === 168) return false;
  if (first === 192 && second === 0 && [0, 2].includes(third)) return false;
  if (first === 198 && [18, 19].includes(second)) return false;
  if (first === 198 && second === 51 && third === 100) return false;
  if (first === 203 && second === 0 && third === 113) return false;
  return true;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
