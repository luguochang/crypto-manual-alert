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
const terminalStatusPattern = /^(?:分析完成|分析失败)$/;
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
const officialEvidenceProviders = new Set(["openai_builtin_web_search", "tavily"]);
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

  const statusHeading = page.getByTestId("task-status").getByRole("heading");
  await expect(statusHeading).toHaveText(terminalStatusPattern, { timeout: 300_000 });
  const terminalStatus = (await statusHeading.innerText()).trim();
  let visibleFailure: string | null = null;

  if (terminalStatus === "分析完成") {
    await assertNaturalLanguageSuccess(page);
  } else {
    visibleFailure = await reportVisibleFailure(page, testInfo);
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

  const taskUrl = new URL(page.url());
  const taskId = taskUrl.searchParams.get("task");
  expect(taskUrl.pathname).toBe("/work");
  expect(taskId).not.toBeNull();
  expect(taskId ?? "").toMatch(uuidPattern);
  const resolvedTaskId = taskId ?? "";
  const initialTerminalProjection = terminalProjectionForTask(observer, resolvedTaskId);
  expect(initialTerminalProjection.status).toBe(
    terminalStatus === "分析完成" ? "succeeded" : "failed",
  );

  const productPostsBeforeReload = productAnalysisRequests(observer).length;
  const forbiddenRequestsBeforeReload = forbiddenBrowserRequests(observer);
  const projectionCountBeforeReload = observer.productProjections.length;

  await page.reload();

  await expect(page).toHaveURL(taskUrl.toString());
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText(
    terminalStatus,
    { timeout: 30_000 },
  );
  const refreshedFailure = terminalStatus === "分析失败"
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

  const refreshedTerminalProjection = terminalProjectionForTask(
    observer,
    resolvedTaskId,
    projectionCountBeforeReload,
  );
  expect(refreshedTerminalProjection.status).toBe(initialTerminalProjection.status);
  expect(refreshedTerminalProjection.binding).toEqual(initialTerminalProjection.binding);

  if (visibleFailure !== null) {
    expect(refreshedFailure).toBe(visibleFailure);
    expect(refreshedTerminalProjection.errorSignature).toBe(
      initialTerminalProjection.errorSignature,
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

  observer.productProjections.push({
    taskId,
    status,
    binding,
    errorSignature,
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
        `${path}.source must be openai_builtin_web_search or tavily; fixture/test providers are forbidden`,
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

function terminalProjectionForTask(
  observer: FlowObserver,
  taskId: string,
  startIndex = 0,
) {
  const projections = observer.productProjections
    .slice(startIndex)
    .filter((projection) =>
      projection.taskId === taskId && terminalProductStatuses.has(projection.status));
  const projection = projections[projections.length - 1];
  if (projection === undefined) {
    throw new Error(`no terminal Product projection observed for task ${taskId}`);
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

async function assertNaturalLanguageSuccess(page: Page) {
  const result = page.getByTestId("analysis-result");
  await expect(result).toBeVisible();
  await expect(result.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await expect(result.getByRole("heading", { name: "Risk" })).toBeVisible();
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
