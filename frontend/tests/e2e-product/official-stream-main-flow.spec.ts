import {
  expect,
  test,
  type Page,
  type Request as PlaywrightRequest,
  type Response as PlaywrightResponse,
  type TestInfo,
} from "@playwright/test";
import { isIP } from "node:net";

const productAnalysisPath = "/api/product/api/v2/analysis";
const uuidSource = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const uuidPattern = new RegExp(`^${uuidSource}$`, "i");
const productTaskPathPattern = new RegExp(
  `^/api/product/api/v2/tasks/(${uuidSource})$`,
  "i",
);
const officialAgentReadPattern = new RegExp(
  `^/api/agent/threads/(${uuidSource})/(state|history|stream/events)$`,
  "i",
);
const settledStatusPattern = /^(?:分析完成|分析失败|等待人工确认)$/;
const productStatuses = new Set([
  "queued",
  "running",
  "waiting_human",
  "succeeded",
  "blocked",
  "failed",
  "cancelled",
]);
const terminalProductStatuses = new Set(["succeeded", "blocked", "failed", "cancelled"]);
const settledProductStatuses = new Set([...terminalProductStatuses, "waiting_human"]);
const productStageNames = new Set([
  "market_snapshot",
  "web_evidence",
  "analysis",
  "evidence_verdict",
  "risk_verdict",
  "artifact",
  "notification",
  "run",
]);
const productStageStatuses = new Set([
  "committed",
  "planned",
  "succeeded",
  "blocked",
  "failed",
  "cancelled",
]);
const productStageLabels = new Map([
  ["market_snapshot", "市场快照"],
  ["web_evidence", "Web 证据"],
  ["analysis", "分析判断"],
  ["evidence_verdict", "证据门禁"],
  ["risk_verdict", "风险门禁"],
  ["artifact", "分析报告"],
  ["notification", "通知发送"],
  ["run", "执行阶段"],
]);
const officialEvidenceProviders = new Set([
  "openai_builtin_web_search",
  "tavily",
  "ddgs_metasearch",
]);
const expectedDeviceProjects: Record<string, { width: number; height: number }> = {
  "fixture-desktop": { width: 1440, height: 1000 },
  "fixture-pixel-7": { width: 412, height: 915 },
};

test.skip(
  process.env.REAL_PRODUCT_E2E !== "1",
  "set REAL_PRODUCT_E2E=1 to run the real Product API chain",
);

test("observes the official stream main flow without browser-side commands", async ({ page }, testInfo) => {
  test.setTimeout(360_000);
  assertDeviceCoverage(page, testInfo);

  const observer = installFlowObserver(page);

  await page.goto("/work");
  await page.getByLabel("分析问题").fill(
    "使用真实交易所行情和实时 Web Search 分析 BTC；宏观证据不足时必须返回 no_trade，所有事实必须引用来源。",
  );
  await page.getByRole("button", { name: "开始分析" }).click();
  await assertOfficialLiveStreamDom(page);

  const taskUrl = new URL(page.url());
  const taskId = taskUrl.searchParams.get("task");
  expect(taskUrl.pathname).toBe("/work");
  expect(taskId).not.toBeNull();
  expect(taskId ?? "").toMatch(uuidPattern);
  const resolvedTaskId = taskId ?? "";

  const runningProjection = await waitForRunningDurableProjection(
    page,
    observer,
    resolvedTaskId,
  );
  await assertPersistedStagesVisible(page, runningProjection.stageNames);
  await settleProductResponseInspections(observer);
  assertRunningReloadStillEligible(observer, runningProjection);
  const productPostsBeforeRunningReload = productAnalysisRequests(observer).length;
  const projectionCountBeforeRunningReload = observer.productProjections.length;

  await page.reload();

  await expect(page).toHaveURL(taskUrl.toString());
  const recoveredRunningProjection = await waitForFirstTaskProjection(
    page,
    observer,
    resolvedTaskId,
    projectionCountBeforeRunningReload,
  );
  expect(recoveredRunningProjection.taskId).toBe(runningProjection.taskId);
  expect(recoveredRunningProjection.binding).toEqual(runningProjection.binding);
  expect(recoveredRunningProjection.stageNames).toEqual(
    expect.arrayContaining(runningProjection.stageNames),
  );
  await assertPersistedStagesVisible(page, runningProjection.stageNames);
  expect(productAnalysisRequests(observer)).toHaveLength(productPostsBeforeRunningReload);
  expect(productAnalysisRequests(observer)).toHaveLength(1);

  const statusHeading = page.getByTestId("task-status").getByRole("heading");
  await expect(statusHeading).toHaveText(settledStatusPattern, { timeout: 300_000 });
  const settledStatus = (await statusHeading.innerText()).trim();
  let visibleFailure: string | null = null;

  const settledProgressBeforeReload = await assertSettledProgressDom(page, settledStatus);
  if (settledStatus === "分析完成") {
    await assertNaturalLanguageSuccess(page);
  } else if (settledStatus === "分析失败") {
    visibleFailure = await reportVisibleFailure(page, testInfo);
  } else {
    await assertHumanReviewReady(page);
  }

  await settleProductResponseInspections(observer);
  assertRequestBoundary(observer);
  assertOfficialStreamObservation(observer);
  await assertNoRawPayload(page);
  await assertPageQuality(page);
  await testInfo.attach("terminal-full-page", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  const initialSettledProjection = settledProjectionForTask(observer, resolvedTaskId);
  expect(initialSettledProjection.status).toBe(
    settledStatus === "分析完成"
      ? "succeeded"
      : settledStatus === "分析失败" ? "failed" : "waiting_human",
  );

  const productPostsBeforeReload = productAnalysisRequests(observer).length;
  const forbiddenRequestsBeforeReload = forbiddenBrowserRequests(observer);
  const projectionCountBeforeReload = observer.productProjections.length;

  await page.reload();

  await expect(page).toHaveURL(taskUrl.toString());
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    settledStatus,
    { timeout: 30_000 },
  );
  const settledProgressAfterReload = await assertSettledProgressDom(page, settledStatus);
  expect(settledProgressAfterReload).toEqual(
    expect.arrayContaining(settledProgressBeforeReload),
  );
  if (settledStatus === "等待人工确认") {
    await assertHumanReviewReady(page);
  }
  const refreshedFailure = settledStatus === "分析失败"
    ? await reportVisibleFailure(page, testInfo, "after-reload")
    : null;
  await settleProductResponseInspections(observer);

  expect(productAnalysisRequests(observer)).toHaveLength(productPostsBeforeReload);
  expect(productAnalysisRequests(observer)).toHaveLength(1);
  expect(forbiddenBrowserRequests(observer)).toEqual(forbiddenRequestsBeforeReload);
  expect(forbiddenBrowserRequests(observer)).toEqual([]);
  assertRequestBoundary(observer);
  assertOfficialStreamObservation(observer);
  await assertNoRawPayload(page);
  await assertPageQuality(page);

  const refreshedSettledProjection = settledProjectionForTask(
    observer,
    resolvedTaskId,
    projectionCountBeforeReload,
  );
  expect(refreshedSettledProjection.status).toBe(initialSettledProjection.status);
  expect(refreshedSettledProjection.binding).toEqual(initialSettledProjection.binding);
  expect(refreshedSettledProjection.stageSignature).toBe(
    initialSettledProjection.stageSignature,
  );

  if (visibleFailure !== null) {
    expect(refreshedFailure).toBe(visibleFailure);
    expect(refreshedSettledProjection.errorSignature).toBe(
      initialSettledProjection.errorSignature,
    );
    throw new Error(`Real Product flow failed: ${visibleFailure}`);
  }
});

interface ObservedRequest {
  method: string;
  pathname: string;
}

interface FlowObserver {
  requests: ObservedRequest[];
  consoleErrors: string[];
  pageErrors: string[];
  serverErrors: string[];
  productResponseErrors: string[];
  productResponseInspections: Set<Promise<void>>;
  productProjections: ProductProjectionObservation[];
  sawAgentStream: boolean;
  agentStreamBindings: Map<string, AgentStreamBinding>;
}

interface AgentStreamBinding {
  assistantId: string;
  threadId: string;
  runId: string;
}

interface ProductProjectionObservation {
  taskId: string;
  status: string;
  binding: AgentStreamBinding | null;
  errorSignature: string | null;
  stageSignature: string | null;
  stageNames: string[];
}

interface OfficialAgentRead {
  kind: "state" | "history" | "events";
  threadId: string;
}

function assertDeviceCoverage(page: Page, testInfo: TestInfo) {
  const expectedViewport = expectedDeviceProjects[testInfo.project.name];
  if (expectedViewport === undefined) {
    throw new Error(
      `real Product contract must run in Desktop and Pixel 7 projects, received ${testInfo.project.name}`,
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
    productResponseInspections: new Set(),
    productProjections: [],
    sawAgentStream: false,
    agentStreamBindings: new Map(),
  };

  page.on("request", (request) => {
    observer.requests.push(observedRequest(request));
  });
  page.on("console", (message) => {
    if (message.type() === "error") observer.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => {
    observer.pageErrors.push(error.message);
  });
  page.on("response", (response) => {
    const request = observedRequest(response.request());
    if (response.status() >= 500) {
      observer.serverErrors.push(`${response.status()} ${request.method} ${request.pathname}`);
    }
    if (!isProductProjectionResponse(response, request.pathname)) return;

    const inspection = inspectProductProjection(response, observer)
      .catch((error: unknown) => {
        observer.productResponseErrors.push(
          `${request.method} ${request.pathname}: ${readErrorMessage(error)}`,
        );
      });
    observer.productResponseInspections.add(inspection);
    void inspection.then(() => observer.productResponseInspections.delete(inspection));
  });

  return observer;
}

function observedRequest(request: PlaywrightRequest): ObservedRequest {
  return {
    method: request.method().toUpperCase(),
    pathname: new URL(request.url()).pathname,
  };
}

function isProductProjectionResponse(response: PlaywrightResponse, pathname: string) {
  if (!response.ok()) return false;
  if (pathname !== productAnalysisPath && !productTaskPathPattern.test(pathname)) return false;
  return response.headers()["content-type"]?.includes("application/json") ?? false;
}

async function inspectProductProjection(
  response: PlaywrightResponse,
  observer: FlowObserver,
) {
  const projection: unknown = await response.json();
  if (!isRecord(projection)) {
    throw new Error("Product projection must be an object");
  }

  const taskId = requiredUuid(projection.task_id, "task_id");
  const status = requiredString(projection.status, "status");
  if (!productStatuses.has(status)) {
    throw new Error(`status must be a typed Product status, received ${JSON.stringify(status)}`);
  }

  const binding = inspectAgentStreamBinding(projection.agent_stream);
  if (terminalProductStatuses.has(status) && binding === null) {
    throw new Error(`terminal Product projection ${status} must contain agent_stream binding`);
  }
  if (binding !== null) {
    observer.sawAgentStream = true;
    observer.agentStreamBindings.set(binding.runId, binding);
  }

  if (status === "succeeded") {
    assertOfficialWebEvidence(projection.web_evidence);
  }
  const errorSignature = status === "failed"
    ? failureErrorSignature(projection.errors)
    : null;
  const stageHistory = inspectStageHistory(projection.stage_history, status);

  observer.productProjections.push({
    taskId,
    status,
    binding,
    errorSignature,
    stageSignature: stageHistory?.signature ?? null,
    stageNames: stageHistory?.stageNames ?? [],
  });
}

async function settleProductResponseInspections(observer: FlowObserver) {
  while (observer.productResponseInspections.size > 0) {
    await Promise.all([...observer.productResponseInspections]);
  }
  expect(observer.productResponseErrors).toEqual([]);
}

function inspectAgentStreamBinding(value: unknown): AgentStreamBinding | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new Error("agent_stream must be an object");
  }
  if (value.protocol !== "langgraph-v2") {
    throw new Error("agent_stream.protocol must be langgraph-v2");
  }
  return {
    assistantId: requiredUuid(value.assistant_id, "agent_stream.assistant_id"),
    threadId: requiredUuid(value.thread_id, "agent_stream.thread_id"),
    runId: requiredUuid(value.run_id, "agent_stream.run_id"),
  };
}

function assertOfficialWebEvidence(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error("succeeded Product projection must contain typed web_evidence");
  }

  for (const [index, item] of value.entries()) {
    const path = `web_evidence[${index}]`;
    if (!isRecord(item)) {
      throw new Error(`${path} must be an object`);
    }

    const provider = requiredString(item.source, `${path}.source`);
    if (!officialEvidenceProviders.has(provider)) {
      throw new Error(
        `${path}.source must be an approved real search provider; fixture/test providers are forbidden`,
      );
    }
    requiredString(item.title, `${path}.title`);

    const finalUrl = requiredString(item.final_url, `${path}.final_url`);
    if (!isPublicHttpsUrl(finalUrl)) {
      throw new Error(`${path}.final_url must be a public HTTPS URL`);
    }

    const fetchedAt = requiredTimestamp(item.fetched_at, `${path}.fetched_at`);
    if (fetchedAt > Date.now() + 10 * 60_000) {
      throw new Error(`${path}.fetched_at must not be in the future`);
    }

    if (!Object.prototype.hasOwnProperty.call(item, "published_at")) {
      throw new Error(`${path}.published_at must be present and may be null`);
    }
    if (item.published_at !== null) {
      const publishedAt = requiredTimestamp(item.published_at, `${path}.published_at`);
      if (publishedAt > fetchedAt) {
        throw new Error(`${path}.published_at must not be later than fetched_at`);
      }
      if (publishedAt === fetchedAt) {
        throw new Error(`${path}.published_at must not be fabricated from fetched_at`);
      }
    }
  }
}

function failureErrorSignature(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error("failed Product projection must contain a typed honest error");
  }
  const errors = value.map((item, index) => {
    if (!isRecord(item)) {
      throw new Error(`errors[${index}] must be an object`);
    }
    if (typeof item.retryable !== "boolean") {
      throw new Error(`errors[${index}].retryable must be a boolean`);
    }
    return {
      code: requiredString(item.code, `errors[${index}].code`),
      message: requiredString(item.message, `errors[${index}].message`),
      retryable: item.retryable,
    };
  });
  return JSON.stringify(errors);
}

function inspectStageHistory(value: unknown, taskStatus: string) {
  if (value === null || value === undefined) {
    if (terminalProductStatuses.has(taskStatus)) {
      throw new Error(`terminal Product projection ${taskStatus} must contain stage_history`);
    }
    return null;
  }
  if (!isRecord(value)) throw new Error("stage_history must be an object");

  requiredUuid(value.run_id, "stage_history.run_id");
  if (!Array.isArray(value.stages)) throw new Error("stage_history.stages must be an array");

  let previousSequence = 0;
  const stages = value.stages.map((item, index) => {
    const path = `stage_history.stages[${index}]`;
    if (!isRecord(item)) throw new Error(`${path} must be an object`);
    const allowedKeys = new Set(["sequence", "stage", "status", "recorded_at", "source"]);
    const unsafeKey = Object.keys(item).find((key) => !allowedKeys.has(key));
    if (unsafeKey !== undefined) throw new Error(`${path}.${unsafeKey} is not public`);
    if (!Number.isInteger(item.sequence) || (item.sequence as number) <= previousSequence) {
      throw new Error(`${path}.sequence must be positive, unique, and ascending`);
    }
    previousSequence = item.sequence as number;
    const stage = requiredString(item.stage, `${path}.stage`);
    const status = requiredString(item.status, `${path}.status`);
    if (!productStageNames.has(stage)) throw new Error(`${path}.stage is unsupported`);
    if (!productStageStatuses.has(status)) throw new Error(`${path}.status is unsupported`);
    requiredTimestamp(item.recorded_at, `${path}.recorded_at`);
    if (item.source !== "official_stream" && item.source !== "product_projection") {
      throw new Error(`${path}.source is unsupported`);
    }
    return { sequence: previousSequence, stage, status, source: item.source };
  });

  const expectedCursor = stages.length === 0 ? null : previousSequence;
  if (value.product_event_cursor !== expectedCursor) {
    throw new Error("stage_history.product_event_cursor must identify the last stage");
  }
  const hasOfficialCursor = typeof value.official_stream_cursor === "string"
    && value.official_stream_cursor.trim().length > 0;
  const hasOfficialCursorAt = typeof value.official_stream_cursor_at === "string"
    && Number.isFinite(Date.parse(value.official_stream_cursor_at));
  if (hasOfficialCursor !== hasOfficialCursorAt) {
    throw new Error("stage_history official cursor and timestamp must be paired");
  }

  if (terminalProductStatuses.has(taskStatus)) {
    const terminal = stages.findLast((stage) => stage.stage === "run");
    if (terminal?.status !== taskStatus) {
      throw new Error("terminal Product projection must contain its persisted run stage");
    }
  }
  return {
    signature: JSON.stringify(stages),
    stageNames: [...new Set(stages.map((stage) => stage.stage))],
  };
}

async function waitForRunningDurableProjection(
  page: Page,
  observer: FlowObserver,
  taskId: string,
) {
  const deadline = Date.now() + 60_000;
  let inspected = 0;
  while (Date.now() < deadline) {
    await settleProductResponseInspections(observer);
    const projections = observer.productProjections.slice(inspected);
    inspected = observer.productProjections.length;
    for (const projection of projections) {
      if (projection.taskId !== taskId) continue;
      if (terminalProductStatuses.has(projection.status)) {
        throw new Error(
          "real flow reached terminal status before a non-terminal persisted stage could be reloaded",
        );
      }
      if (projection.stageNames.length > 0) {
        if (projection.binding === null) {
          throw new Error("non-terminal persisted stage must retain its official stream binding");
        }
        return projection;
      }
    }
    await page.waitForTimeout(100);
  }
  throw new Error(
    "timed out before observing stage_history with a queued/running/waiting_human status",
  );
}

function assertRunningReloadStillEligible(
  observer: FlowObserver,
  expected: ProductProjectionObservation,
) {
  const latest = observer.productProjections.findLast(
    (projection) => projection.taskId === expected.taskId,
  );
  if (
    latest === undefined
    || terminalProductStatuses.has(latest.status)
    || latest.stageNames.length === 0
  ) {
    throw new Error(
      "real flow became terminal before the running-stage reload; refusing terminal fallback",
    );
  }
  expect(latest.binding).toEqual(expected.binding);
}

async function waitForFirstTaskProjection(
  page: Page,
  observer: FlowObserver,
  taskId: string,
  startIndex: number,
) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    await settleProductResponseInspections(observer);
    const projection = observer.productProjections
      .slice(startIndex)
      .find((candidate) => candidate.taskId === taskId);
    if (projection !== undefined) return projection;
    await page.waitForTimeout(100);
  }
  throw new Error("reload did not recover the same Product Task projection");
}

function settledProjectionForTask(
  observer: FlowObserver,
  taskId: string,
  startIndex = 0,
) {
  const projections = observer.productProjections
    .slice(startIndex)
    .filter((projection) =>
      projection.taskId === taskId && settledProductStatuses.has(projection.status));
  const projection = projections[projections.length - 1];
  if (projection === undefined) {
    throw new Error(`no settled Product projection observed for task ${taskId}`);
  }
  return projection;
}

function officialAgentRead(request: ObservedRequest): OfficialAgentRead | null {
  const match = officialAgentReadPattern.exec(request.pathname);
  const threadId = match?.[1];
  const endpoint = match?.[2];
  if (threadId === undefined || endpoint === undefined) return null;

  const method = endpoint === "state" ? "GET" : "POST";
  if (request.method !== method) return null;
  return {
    kind: endpoint === "stream/events" ? "events" : endpoint as "state" | "history",
    threadId: threadId.toLowerCase(),
  };
}

function requiredString(value: unknown, path: string) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${path} must be a non-empty string`);
  }
  return value.trim();
}

function requiredUuid(value: unknown, path: string) {
  const parsed = requiredString(value, path);
  if (!uuidPattern.test(parsed)) {
    throw new Error(`${path} must be a UUID`);
  }
  return parsed.toLowerCase();
}

function requiredTimestamp(value: unknown, path: string) {
  const parsed = requiredString(value, path);
  const timestamp = Date.parse(parsed);
  if (!Number.isFinite(timestamp)) {
    throw new Error(`${path} must be a valid timestamp`);
  }
  return timestamp;
}

function isPublicHttpsUrl(value: string) {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.protocol !== "https:" || url.username || url.password) return false;

  const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (!hostname || reservedHostname(hostname)) return false;
  const ipVersion = isIP(hostname);
  if (ipVersion === 4) return isPublicIpv4(hostname);
  if (ipVersion === 6) {
    return /^[23]/i.test(hostname) && !hostname.startsWith("2001:db8:");
  }
  return hostname.includes(".");
}

function reservedHostname(hostname: string) {
  if (["example.com", "example.net", "example.org"].includes(hostname)) return true;
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
  ].some((suffix) => hostname === suffix.replace(/^\./, "") || hostname.endsWith(suffix));
}

function isPublicIpv4(hostname: string) {
  const [first = 0, second = 0, third = 0] = hostname.split(".").map(Number);
  if (first === 0 || first === 10 || first === 127 || first >= 224) return false;
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

function assertRequestBoundary(observer: FlowObserver) {
  expect(productAnalysisRequests(observer)).toHaveLength(1);
  expect(
    forbiddenBrowserRequests(observer),
  ).toEqual([]);
  expect(observer.serverErrors).toEqual([]);
  expect(observer.consoleErrors).toEqual([]);
  expect(observer.pageErrors).toEqual([]);
}

function productAnalysisRequests(observer: FlowObserver) {
  return observer.requests.filter(
    (request) => request.method === "POST" && request.pathname === productAnalysisPath,
  );
}

function forbiddenBrowserRequests(observer: FlowObserver) {
  return observer.requests
    .filter((request) => {
      if (/(?:^|\/)(?:commands|runs)(?:\/|$)/.test(request.pathname)) return true;
      if (/^\/api\/agent\/(?:assistants|store)(?:\/|$)/.test(request.pathname)) return true;
      if (/^\/threads(?:\/|$)/.test(request.pathname)) return true;
      if (!/^\/api\/agent(?:\/|$)/.test(request.pathname)) return false;
      return officialAgentRead(request) === null;
    })
    .map((request) => `${request.method} ${request.pathname}`);
}

function assertOfficialStreamObservation(observer: FlowObserver) {
  expect(observer.sawAgentStream).toBe(true);
  const bindings = [...observer.agentStreamBindings.values()];
  expect(bindings.length).toBeGreaterThan(0);
  for (const binding of bindings) {
    expect(binding.assistantId).toMatch(uuidPattern);
    expect(binding.threadId).toMatch(uuidPattern);
    expect(binding.runId).toMatch(uuidPattern);
  }

  const officialReads = observer.requests.flatMap((request) => {
    const read = officialAgentRead(request);
    return read === null ? [] : [read];
  });
  expect(officialReads.filter((request) => request.kind === "state").length).toBeGreaterThan(0);
  expect(officialReads.filter((request) => request.kind === "history").length).toBeGreaterThan(0);
  expect(officialReads.filter((request) => request.kind === "events").length).toBeGreaterThan(0);
  expect(
    officialReads.every((request) =>
      bindings.some((binding) => binding.threadId === request.threadId)),
  ).toBe(true);
}

async function assertOfficialLiveStreamDom(page: Page) {
  const stream = page.getByTestId("official-run-stream");
  await expect(stream).toBeVisible({ timeout: 30_000 });
  await expect(stream.getByRole("heading", { name: "官方执行进度" })).toBeVisible();
  await expect(stream.locator(".official-stream-status")).toHaveText(
    /^(?:正在连接|实时同步中)$/,
    { timeout: 30_000 },
  );
  await expect(stream.locator(".official-progress-list")).toBeVisible();
  await expect(stream.getByText("执行阶段", { exact: true })).toBeVisible();
}

async function assertPersistedStagesVisible(page: Page, stageNames: readonly string[]) {
  expect(stageNames.length).toBeGreaterThan(0);
  const progress = page.getByTestId("official-run-stream");
  await expect(progress).toBeVisible({ timeout: 30_000 });
  for (const stageName of stageNames) {
    const label = productStageLabels.get(stageName);
    if (label === undefined) throw new Error(`missing UI label for persisted stage ${stageName}`);
    await expect(
      progress.locator(".official-progress-list").getByText(label, { exact: true }),
    ).toBeVisible();
  }
}

async function assertDurableProgressDom(page: Page) {
  const progress = page.getByTestId("durable-run-progress");
  await expect(progress).toBeVisible({ timeout: 30_000 });
  await expect(progress.getByRole("heading", { name: "执行进度" })).toBeVisible();
  await expect(progress.locator(".official-stream-status")).toHaveText("已保存");
  await expect(progress.locator(".official-progress-list")).toBeVisible();

  const stages = (await progress.locator(".official-progress-list > li").allTextContents())
    .map((stage) => stage.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  expect(stages.length).toBeGreaterThan(0);
  expect(stages.some((stage) => stage.includes("执行阶段"))).toBe(true);
  expect(await progress.innerText()).not.toMatch(
    /(?:product_event_cursor|official_stream_cursor|run_id|opaque-stream-event)/,
  );
  return stages;
}

async function assertSettledProgressDom(page: Page, settledStatus: string) {
  if (settledStatus !== "等待人工确认") {
    return assertDurableProgressDom(page);
  }

  const progress = page.getByTestId("official-run-stream");
  await expect(progress).toBeVisible({ timeout: 30_000 });
  await expect(progress.getByRole("heading", { name: "官方执行进度" })).toBeVisible();
  await expect(progress.locator(".official-stream-status")).toHaveText("实时同步中");
  await expect(progress.locator(".official-progress-list")).toBeVisible();

  const stages = (await progress.locator(".official-progress-list > li strong").allTextContents())
    .map((stage) => stage.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  expect(stages.length).toBeGreaterThan(0);
  expect(stages).toContain("市场快照");
  expect(await progress.innerText()).not.toMatch(
    /(?:product_event_cursor|official_stream_cursor|run_id|opaque-stream-event)/,
  );
  return stages;
}

async function assertNaturalLanguageSuccess(page: Page) {
  const result = page.getByTestId("analysis-result");
  await expect(result).toBeVisible();
  await expect(result.getByRole("heading", { name: "证据门禁" })).toBeVisible();
  await expect(result.getByRole("heading", { name: "风险门禁" })).toBeVisible();
  await expect(result.getByRole("heading", { name: "判断依据" })).toBeVisible();

  const action = (await result.locator(".decision-summary strong").innerText()).trim();
  const conclusion = (await result.locator(".rationale-list li").first().innerText()).trim();
  expect(action.length).toBeGreaterThan(1);
  expect(action).not.toMatch(/^(?:open|hold|close|flip|trigger|no_trade)(?:_|$)/);
  expect(conclusion.length).toBeGreaterThan(3);
  expect(conclusion).toMatch(/\p{L}/u);
  expect(conclusion).not.toMatch(/^\s*[\[{]/);

  const httpsSource = result.locator('a[href^="https://"]').first();
  await expect(httpsSource).toBeVisible();
  await expect(httpsSource).toHaveAttribute("href", /^https:\/\//);
  await expect(result.locator("pre")).toHaveCount(0);
}

async function assertHumanReviewReady(page: Page) {
  const panel = page.locator("section.hitl-review-panel");
  await expect(panel).toHaveCount(1);
  await expect(
    panel.getByRole("heading", { name: "分析草稿待人工确认", exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("button", { name: "拒绝", exact: true })).toBeEnabled();
}

async function reportVisibleFailure(
  page: Page,
  testInfo: TestInfo,
  phase = "before-reload",
) {
  const failure = page.locator("section.failure-panel[role='alert']");
  await expect(failure).toBeVisible();
  await expect(failure.getByRole("heading")).not.toHaveText("");
  const paragraphs = await failure.locator("p").allTextContents();
  expect(paragraphs.length).toBeGreaterThan(0);
  expect(paragraphs.every((paragraph) => paragraph.trim().length > 0)).toBe(true);

  const visibleFailure = (await failure.innerText()).replace(/\s+/g, " ").trim();
  expect(visibleFailure.length).toBeGreaterThan(0);
  testInfo.annotations.push({
    type: "observed-product-failure",
    description: visibleFailure,
  });
  await testInfo.attach(`visible-product-failure-${phase}`, {
    body: visibleFailure,
    contentType: "text/plain",
  });
  return visibleFailure;
}

async function assertNoRawPayload(page: Page) {
  await expect(page.locator("pre")).toHaveCount(0);
  const visibleText = await page.locator("body").innerText();
  expect(visibleText).not.toContain("Raw JSON");
  expect(visibleText).not.toMatch(
    /"(?:task_id|artifact|agent_stream|root_cause_chain|source_references)"\s*:/,
  );
}

async function assertPageQuality(page: Page) {
  const audit = await page.evaluate(() => {
    const root = document.documentElement;
    const horizontalOverflow = Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0)
      - root.clientWidth;
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>(
        "button, a[href], input:not([type='hidden']), select, textarea",
      ),
    ).filter((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return element.getClientRects().length > 0
        && rect.width > 0
        && rect.height > 0
        && style.display !== "none"
        && style.visibility !== "hidden";
    });
    const unnamedControls = controls
      .filter((element) => accessibleControlName(element).length === 0)
      .map((element) => `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}`);
    const overflowingElements = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return element.getClientRects().length > 0
          && rect.width > 0
          && rect.height > 0
          && style.display !== "none"
          && style.visibility !== "hidden"
          && (
            rect.left < -1
            || rect.right > root.clientWidth + 1
            || element.scrollWidth > element.clientWidth + 1
          );
      })
      .map((element) => {
        const className = typeof element.className === "string" && element.className
          ? `.${element.className.trim().replace(/\s+/g, ".")}`
          : "";
        return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${className}`;
      })
      .slice(0, 20);

    return { horizontalOverflow, unnamedControls, overflowingElements };

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
      const imageAlts = Array.from(element.querySelectorAll<HTMLImageElement>("img[alt]"))
        .map((image) => image.alt)
        .join(" ");
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
        imageAlts,
        inputValue,
        element.getAttribute("title"),
      ].filter(Boolean).join(" ").trim();
    }
  });

  expect(audit.horizontalOverflow).toBeLessThanOrEqual(0);
  expect(audit.unnamedControls).toEqual([]);
  expect(audit.overflowingElements).toEqual([]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
