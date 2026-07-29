import { expect, test, type Page, type Request, type Response, type TestInfo } from "@playwright/test";
import axe from "axe-core";

import {
  inboxViewSchema,
  productTaskSchema,
  type InboxItem,
} from "../../src/lib/schemas/product-api";

type AnalysisInboxItem = InboxItem & {
  payload: Extract<InboxItem["payload"], { kind: "artifact_review" }>;
};

const inboxPath = "/api/product/api/v2/inbox";
const expectedTaskId = process.env.REAL_INBOX_TASK_ID?.trim().toLowerCase() ?? "";
const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const expectedProjects: Record<string, { width: number; height: number }> = {
  "fixture-desktop": { width: 1440, height: 1000 },
  "fixture-pixel-7": { width: 412, height: 915 },
};

test.skip(
  process.env.REAL_PRODUCT_E2E !== "1",
  "set REAL_PRODUCT_E2E=1 to run the real Product Inbox chain",
);

test("opens a persisted Inbox review without browser-side writes", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  expect(expectedTaskId).toMatch(uuidPattern);
  expect(page.viewportSize()).toEqual(expectedViewport(testInfo));

  const observer = installBrowserObserver(page);
  const inboxResponsePromise = page.waitForResponse(isActiveInboxResponse, { timeout: 30_000 });
  await page.goto("/inbox");

  const rawInbox: unknown = await (await inboxResponsePromise).json();
  assertNoRuntimeProjectionFields(rawInbox);
  const inbox = inboxViewSchema.parse(rawInbox);
  const pendingItem = requirePendingItem(inbox.items, expectedTaskId);
  const taskHref = `/work?task=${encodeURIComponent(pendingItem.task_id)}`;
  const card = page.locator(".inbox-item", {
    has: page.locator(`a[href="${taskHref}"]`),
  });

  await expect(page.getByRole("heading", { name: "审核收件箱", exact: true })).toBeVisible();
  await expect(card).toHaveAttribute("data-status", "pending");
  await expect(card.getByText("待审核", { exact: true }).first()).toBeVisible();
  await expect(card.getByText(pendingItem.horizon, { exact: true })).toBeVisible();
  await expect(card.getByRole("link", { name: "打开任务", exact: true })).toHaveAttribute(
    "href",
    taskHref,
  );
  for (const statement of pendingItem.payload.artifact.analysis.root_cause_chain.slice(0, 2)) {
    await expect(card.getByText(statement, { exact: false })).toBeVisible();
  }
  await assertNoInternalRuntimeText(page, pendingItem);
  await assertPageQuality(page, "Inbox", true);
  expect(observer.writes).toEqual([]);

  const resolvedResponsePromise = page.waitForResponse(
    (response) => isInboxResponseForStatus(response, "resolved"),
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: "已解决", exact: true }).click();
  const rawResolvedInbox: unknown = await (await resolvedResponsePromise).json();
  assertNoRuntimeProjectionFields(rawResolvedInbox);
  await expect(page).toHaveURL(/\/inbox\?status=resolved$/);
  await expect(page.getByRole("button", { name: "已解决", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  const refreshedResolvedResponsePromise = page.waitForResponse(
    (response) => isInboxResponseForStatus(response, "resolved"),
    { timeout: 30_000 },
  );
  await page.reload();
  assertNoRuntimeProjectionFields(await (await refreshedResolvedResponsePromise).json());
  await expect(page).toHaveURL(/\/inbox\?status=resolved$/);
  await expect(page.getByRole("button", { name: "已解决", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  const activeResponsePromise = page.waitForResponse(isActiveInboxResponse, { timeout: 30_000 });
  await page.getByRole("button", { name: "待处理", exact: true }).click();
  const refreshedActiveInbox = inboxViewSchema.parse(await (await activeResponsePromise).json());
  expect(refreshedActiveInbox.items.some((item) => item.task_id === pendingItem.task_id)).toBe(true);
  await expect(page).toHaveURL(/\/inbox$/);
  await expect(card).toBeVisible();
  expect(observer.writes).toEqual([]);

  const taskPath = `/api/product/api/v2/tasks/${encodeURIComponent(pendingItem.task_id)}`;
  const taskResponsePromise = page.waitForResponse(
    (response) => isJsonReadResponse(response, taskPath),
    { timeout: 30_000 },
  );
  await card.getByRole("link", { name: "打开任务", exact: true }).click();

  const task = productTaskSchema.parse(await (await taskResponsePromise).json());
  expect(task.task_id).toBe(pendingItem.task_id);
  expect(task.status).toBe("waiting_human");
  expect(task.pending_interrupts?.status).toBe("pending");
  expect(task.pending_interrupts?.members).toHaveLength(pendingItem.member_count);
  expect(task.pending_interrupts?.members[0]?.status).toBe("pending");
  expect(task.pending_interrupts?.members[0]?.payload).toEqual(pendingItem.payload);

  await expect(page).toHaveURL(new RegExp(`/work\\?task=${pendingItem.task_id}$`));
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText("等待人工确认");
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "分析草稿待人工确认", exact: true })).toBeVisible();
  await assertNoInternalRuntimeText(page, pendingItem);
  await assertPageQuality(page, "opened review", true);
  expect(observer.writes).toEqual([]);

  const refreshedTaskResponsePromise = page.waitForResponse(
    (response) => isJsonReadResponse(response, taskPath),
    { timeout: 30_000 },
  );
  await page.reload();
  const refreshedTask = productTaskSchema.parse(await (await refreshedTaskResponsePromise).json());

  expect(refreshedTask.task_id).toBe(pendingItem.task_id);
  expect(refreshedTask.status).toBe("waiting_human");
  expect(refreshedTask.pending_interrupts?.status).toBe("pending");
  expect(refreshedTask.pending_interrupts?.members[0]?.status).toBe("pending");
  expect(refreshedTask.pending_interrupts?.members[0]?.payload).toEqual(pendingItem.payload);
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(1);
  await assertNoInternalRuntimeText(page, pendingItem);
  await assertPageQuality(page, "refreshed review", true);
  expect(observer.writes).toEqual([]);

  await attachDeepScrollScreenshot(page, testInfo);
  expect(observer.consoleErrors).toEqual([]);
  expect(observer.pageErrors).toEqual([]);
  expect(observer.serverErrors).toEqual([]);
});

interface BrowserObserver {
  writes: Array<{ method: string; pathname: string }>;
  consoleErrors: string[];
  pageErrors: string[];
  serverErrors: string[];
}

function expectedViewport(testInfo: TestInfo) {
  const viewport = expectedProjects[testInfo.project.name];
  if (viewport === undefined) {
    throw new Error(
      `Product Inbox E2E must run in Desktop and Pixel 7 projects, received ${testInfo.project.name}`,
    );
  }
  return viewport;
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

function observedRequest(request: Request) {
  return {
    method: request.method().toUpperCase(),
    pathname: new URL(request.url()).pathname,
  };
}

function isActiveInboxResponse(response: Response) {
  return isInboxResponseForStatus(response, "active");
}

function isInboxResponseForStatus(response: Response, status: "active" | "resolved") {
  if (!isJsonReadResponse(response, inboxPath)) return false;
  const url = new URL(response.url());
  return url.searchParams.get("status") === status && url.searchParams.get("limit") === "20";
}

function isJsonReadResponse(response: Response, pathname: string) {
  const request = observedRequest(response.request());
  return response.ok()
    && request.method === "GET"
    && request.pathname === pathname
    && (response.headers()["content-type"] ?? "").includes("application/json");
}

function requirePendingItem(items: InboxItem[], taskId: string): AnalysisInboxItem {
  const pendingItem = items.find((item) =>
    item.status === "pending" && item.task_id.toLowerCase() === taskId);
  if (pendingItem === undefined) {
    throw new Error(`real Product Inbox must contain pending seeded Task ${taskId}`);
  }
  if (!isAnalysisInboxItem(pendingItem)) {
    throw new Error(`real Product Inbox Task ${taskId} must be an analysis review`);
  }
  expect(pendingItem.payload.artifact.status).toBe("draft");
  expect(pendingItem.payload.artifact.analysis.root_cause_chain.length).toBeGreaterThan(0);
  expect(pendingItem.member_count).toBeGreaterThan(0);
  expect(pendingItem.responded_at).toBeNull();
  return pendingItem;
}

function isAnalysisInboxItem(item: InboxItem): item is AnalysisInboxItem {
  return item.payload.kind === "artifact_review";
}

async function assertNoInternalRuntimeText(page: Page, item: InboxItem) {
  await expect(page.locator("pre")).toHaveCount(0);
  const visibleText = await page.locator("body").innerText();
  expect(visibleText).not.toMatch(/raw json/i);
  expect(visibleText).not.toMatch(
    /"(?:task_id|run_id|interrupt_id|checkpoint_id|namespace|response_version)"\s*:/,
  );
  for (const internalValue of [
    item.task_id,
  ]) {
    if (internalValue) expect(visibleText).not.toContain(internalValue);
  }
}

function assertNoRuntimeProjectionFields(value: unknown) {
  const forbidden = new Set([
    "checkpoint_id",
    "interrupt_id",
    "namespace",
    "projection_id",
    "response_version",
    "run_id",
  ]);
  const discovered: string[] = [];
  visit(value, "$");
  expect(discovered, "Inbox API exposed internal Runtime projection fields").toEqual([]);

  function visit(candidate: unknown, path: string) {
    if (Array.isArray(candidate)) {
      candidate.forEach((item, index) => visit(item, `${path}[${index}]`));
      return;
    }
    if (candidate === null || typeof candidate !== "object") return;
    for (const [key, nested] of Object.entries(candidate)) {
      if (forbidden.has(key)) discovered.push(`${path}.${key}`);
      visit(nested, `${path}.${key}`);
    }
  }
}

async function assertPageQuality(page: Page, phase: string, runAxe: boolean) {
  if (runAxe) {
    await page.addScriptTag({ content: axe.source });
    const violations = await page.evaluate(async () => {
      const axeRuntime = (window as typeof window & {
        axe: { run: () => Promise<{ violations: Array<{ id: string; impact: string | null }> }> };
      }).axe;
      return (await axeRuntime.run()).violations.map(({ id, impact }) => ({ id, impact }));
    });
    expect(violations, `${phase} has accessibility violations`).toEqual([]);
  }

  const audit = await page.evaluate(() => {
    const root = document.documentElement;
    const horizontalOverflow = Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0)
      - root.clientWidth;
    const visibleControls = Array.from(document.querySelectorAll<HTMLElement>(
      "button, a[href], input:not([type='hidden']), select, textarea",
    )).filter(isVisible);
    const unnamedControls = visibleControls
      .filter((element) => accessibleControlName(element).length === 0)
      .map(describeElement);
    const horizontallyClippedControls = visibleControls
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -0.5 || rect.right > root.clientWidth + 0.5;
      })
      .map(describeElement);
    const overflowingSurfaces = Array.from(document.querySelectorAll<HTMLElement>(
      ".inbox-toolbar, .inbox-panel, .inbox-item, .hitl-review-panel",
    )).filter((element) => element.scrollWidth - element.clientWidth > 1).map(describeElement);

    return {
      horizontalOverflow,
      horizontallyClippedControls,
      overflowingSurfaces,
      unnamedControls,
    };

    function isVisible(element: HTMLElement) {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return element.getClientRects().length > 0
        && rect.width > 0
        && rect.height > 0
        && style.display !== "none"
        && style.visibility !== "hidden";
    }

    function describeElement(element: HTMLElement) {
      const className = typeof element.className === "string" && element.className
        ? `.${element.className.trim().replace(/\s+/g, ".")}`
        : "";
      return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${className}`;
    }

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
  expect(audit.horizontallyClippedControls, `${phase} has clipped controls`).toEqual([]);
  expect(audit.overflowingSurfaces, `${phase} has overflowing surfaces`).toEqual([]);
  expect(audit.unnamedControls, `${phase} has unnamed interactive controls`).toEqual([]);
}

async function attachDeepScrollScreenshot(page: Page, testInfo: TestInfo) {
  const target = page.locator("section.hitl-review-panel").getByRole("group", { name: "审核决定" });
  await page.evaluate(() => window.scrollTo({
    behavior: "instant",
    left: 0,
    top: document.documentElement.scrollHeight,
  }));
  const position = await page.evaluate(() => ({
    maximumScrollY: Math.max(0, document.documentElement.scrollHeight - window.innerHeight),
    scrollY: window.scrollY,
  }));
  expect(position.maximumScrollY).toBeGreaterThan(0);
  expect(position.scrollY).toBeGreaterThan(0);
  await target.scrollIntoViewIfNeeded();
  await expect(target).toBeInViewport();
  await testInfo.attach(`real-inbox-review-${testInfo.project.name}`, {
    body: await page.screenshot({ animations: "disabled" }),
    contentType: "image/png",
  });
}
