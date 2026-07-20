import {
  expect,
  test,
  type APIResponse,
  type Locator,
  type Page,
  type Request,
  type Response,
  type TestInfo,
} from "@playwright/test";
import axe from "axe-core";
import fs from "node:fs/promises";
import path from "node:path";

import {
  createMonitorRequestSchema,
  monitorListSchema,
  monitorSchema,
  monitorTriggerListSchema,
  type Monitor,
} from "../../src/lib/schemas/monitor-api";
import { artifactDetailSchema } from "../../src/lib/schemas/product-api";


const monitorApiRoot = "/api/product/api/v2/monitors";
const evidenceRoot = process.env.PLAYWRIGHT_EVIDENCE_DIR?.trim() ?? "";
const evidenceDirectory = path.join(evidenceRoot, "visual");
const realEnvironmentReady =
  process.env.V2_E2E_PROFILE === "real-monitor"
  && process.env.REAL_MONITOR_E2E === "1"
  && path.isAbsolute(evidenceRoot);
const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

type RuntimeObserver = {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: string[];
  serverErrors: string[];
  writes: Request[];
};

test.skip(
  !realEnvironmentReady,
  "requires V2_E2E_PROFILE=real-monitor, REAL_MONITOR_E2E=1, an absolute PLAYWRIGHT_EVIDENCE_DIR, a committed Artifact, and live Product/Monitor workers",
);

test("real Monitor workflow persists and controls a committed Artifact monitor", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  assertSupportedViewport(page, testInfo);
  const observer = observeRuntime(page);
  const monitorName = uniqueMonitorName(testInfo);
  let expectedRunTaskType: Monitor["run_task_type"] | null = null;
  let latestMonitor: Monitor | null = null;
  let cleanupRequired = false;

  try {
    await test.step("open a committed Artifact from the real Library", async () => {
      await page.goto("/library");
      await expect(page.getByRole("heading", { name: "报告资料库", exact: true })).toBeVisible();

      const report = page.locator(".run-row.library-row[data-status='committed']").first();
      await expect(report, "the workspace needs at least one committed Artifact").toBeVisible();
      const reportHref = await report.getAttribute("href");
      expect(reportHref).toMatch(/^\/artifacts\/[0-9a-f-]{36}\?version_number=\d+$/i);
      const reportUrl = new URL(reportHref!, page.url());
      const artifactId = reportUrl.pathname.split("/").at(-1) ?? "";
      const versionNumber = Number(reportUrl.searchParams.get("version_number"));
      expect(artifactId).toMatch(uuidPattern);
      expect(versionNumber).toBeGreaterThan(0);

      const artifactResponsePromise = waitForProductResponse(
        page,
        "GET",
        `/api/product/api/v2/artifacts/${artifactId}`,
      );
      await report.click();
      const artifactResponse = await artifactResponsePromise;
      expect(artifactResponse.status()).toBe(200);
      const artifact = artifactDetailSchema.parse(await artifactResponse.json());
      expect(artifact.artifact_id).toBe(artifactId);
      expect(artifact.selected_version?.version_number).toBe(versionNumber);
      expect(artifact.selected_version?.status).toBe("committed");
      expectedRunTaskType = artifact.artifact_type === "deep_research_report"
        ? "deep_research"
        : "market_analysis";

      await expect(page).toHaveURL(new RegExp(`/artifacts/${artifactId}\\?version_number=${versionNumber}$`));
      const createLink = page.getByRole("link", { name: "持续关注", exact: true });
      await expect(createLink).toBeVisible();
      const createHref = await createLink.getAttribute("href");
      expect(createHref).not.toBeNull();
      const createUrl = new URL(createHref!, page.url());
      expect(createUrl.pathname).toBe("/monitors/new");
      expect(createUrl.searchParams.get("artifact_id")).toBe(artifactId);
      expect(createUrl.searchParams.get("artifact_version_id"))
        .toBe(artifact.selected_version?.artifact_version_id);
      expect(createUrl.searchParams.get("version_number")).toBe(String(versionNumber));

      const sourceResponsePromise = waitForProductResponse(
        page,
        "GET",
        `/api/product/api/v2/artifacts/${artifactId}`,
      );
      await createLink.click();
      const sourceResponse = await sourceResponsePromise;
      expect(sourceResponse.status()).toBe(200);
      const verifiedSource = artifactDetailSchema.parse(await sourceResponse.json());
      expect(verifiedSource.selected_version?.status).toBe("committed");
      expect(verifiedSource.selected_version?.artifact_version_id)
        .toBe(artifact.selected_version?.artifact_version_id);
    });

    await test.step("create a real scheduled Monitor through the rendered form", async () => {
      await expect(page.getByRole("heading", { name: "创建持续监控", exact: true })).toBeVisible();
      await expect(page.getByText(/已提交版本 v\d+/)).toBeVisible();
      await page.getByLabel("名称", { exact: true }).fill(monitorName);
      await expect(page.getByLabel("条件类型", { exact: true })).toHaveText("定期复核");
      await page.getByRole("combobox", { name: "频率", exact: true }).selectOption("0 */4 * * *");
      await page.getByRole("combobox", { name: "时区", exact: true }).selectOption("Asia/Shanghai");
      await captureCheckpoint(page, observer, testInfo, "create-ready");

      const responsePromise = waitForProductResponse(page, "POST", monitorApiRoot);
      await page.getByRole("button", { name: "创建持续监控", exact: true }).click();
      const response = await responsePromise;
      expect(response.status()).toBe(202);

      const request = response.request();
      expectIdempotencyKey(request);
      const submission = createMonitorRequestSchema.parse(request.postDataJSON());
      expect(submission).toMatchObject({
        name: monitorName,
        run_task_type: expectedRunTaskType,
        condition: { kind: "scheduled_review" },
        schedule: "0 */4 * * *",
        timezone: "Asia/Shanghai",
        quiet_hours: null,
        destination_ids: [],
      });
      expect(Date.parse(submission.expires_at)).toBeGreaterThan(Date.now());

      latestMonitor = monitorSchema.parse(await response.json());
      cleanupRequired = true;
      expect(latestMonitor).toMatchObject({
        name: monitorName,
        run_task_type: submission.run_task_type,
        artifact_id: submission.artifact_id,
        artifact_version_id: submission.artifact_version_id,
        condition: submission.condition,
        schedule: submission.schedule,
        timezone: submission.timezone,
      });
      expect(["draft", "active"]).toContain(latestMonitor.status);
      await expect(page).toHaveURL(/\/monitors\?status=running$/);
      await expect(monitorRow(page, monitorName)).toBeVisible();
    });

    await test.step("refresh and rejoin the scheduler-activated Monitor", async () => {
      latestMonitor = await waitForSchedulerActivation(page, latestMonitor!);
      await page.reload();
      await expect(page.getByRole("heading", { name: "持续监控", exact: true })).toBeVisible();
      await page.getByRole("link", { name: "全部", exact: true }).click();
      await expect(page).toHaveURL(/\/monitors\?status=all$/);

      const row = monitorRow(page, monitorName);
      await expect(row).toBeVisible();
      await expect(row).toHaveAttribute("data-status", "active");
      await expect(row).toContainText("运行中");
      await expect(row).toContainText("按计划复核报告结论");
      await expect(row.getByRole("button", { name: "暂停", exact: true })).toBeEnabled();
      await expect(row.getByRole("button", { name: "立即检查", exact: true })).toBeEnabled();
      await captureCheckpoint(page, observer, testInfo, "rejoined-active");
    });

    await test.step("read trigger history and pause the Monitor", async () => {
      const row = monitorRow(page, monitorName);
      const historyResponsePromise = waitForProductResponse(
        page,
        "GET",
        `${monitorApiRoot}/${latestMonitor!.id}/triggers`,
      );
      await row.getByRole("button", { name: "触发记录", exact: true }).click();
      const historyResponse = await historyResponsePromise;
      expect(historyResponse.status()).toBe(200);
      monitorTriggerListSchema.parse(await historyResponse.json());
      const historyButton = row.getByRole("button", { name: "触发记录", exact: true });
      await expect(historyButton).toHaveAttribute("aria-expanded", "true");
      await expect(row.getByText(/暂无触发记录|已接收|已抑制|已准入|触发失败/).first()).toBeVisible();

      const paused = await clickForMonitorMutation(
        page,
        row.getByRole("button", { name: "暂停", exact: true }),
        "POST",
        `${monitorApiRoot}/${latestMonitor!.id}/pause`,
        latestMonitor!.version,
      );
      const activeVersion = latestMonitor!.version;
      latestMonitor = paused;
      expect(paused.status).toBe("paused");
      expect(paused.version).toBeGreaterThan(activeVersion);
      await expect(row).toHaveAttribute("data-status", "paused");
      await expect(row).toContainText("已暂停");
      await expect(row.getByRole("button", { name: "恢复", exact: true })).toBeEnabled();
    });

    await test.step("resume and manually trigger the Monitor", async () => {
      const row = monitorRow(page, monitorName);
      const resumed = await clickForMonitorMutation(
        page,
        row.getByRole("button", { name: "恢复", exact: true }),
        "POST",
        `${monitorApiRoot}/${latestMonitor!.id}/resume`,
        latestMonitor!.version,
      );
      const pausedVersion = latestMonitor!.version;
      latestMonitor = resumed;
      expect(resumed.status).toBe("active");
      expect(resumed.version).toBeGreaterThan(pausedVersion);
      await expect(row).toHaveAttribute("data-status", "active");
      await expect(row.getByRole("button", { name: "立即检查", exact: true })).toBeEnabled();

      const historyResponsePromise = waitForProductResponse(
        page,
        "GET",
        `${monitorApiRoot}/${latestMonitor.id}/triggers`,
      );
      const triggered = await clickForMonitorMutation(
        page,
        row.getByRole("button", { name: "立即检查", exact: true }),
        "POST",
        `${monitorApiRoot}/${latestMonitor.id}/trigger`,
        null,
      );
      const historyResponse = await historyResponsePromise;
      expect(historyResponse.status()).toBe(200);
      const history = monitorTriggerListSchema.parse(await historyResponse.json());

      expect(triggered.latest_trigger).toMatchObject({
        trigger_kind: "manual",
        status: "admitted",
      });
      expect(triggered.latest_trigger?.task_id).toMatch(uuidPattern);
      latestMonitor = triggered;
      const manualTrigger = history.items.find(
        (item) => item.id === triggered.latest_trigger?.id,
      );
      expect(manualTrigger).toMatchObject({
        trigger_kind: "manual",
        status: "admitted",
        task_id: triggered.latest_trigger?.task_id,
      });
      await expect(row.getByText("已准入", { exact: true }).first()).toBeVisible();
      await expect(row.getByRole("link", { name: "打开任务", exact: true }).first()).toHaveAttribute(
        "href",
        `/work?task=${triggered.latest_trigger?.task_id}`,
      );
      await captureCheckpoint(page, observer, testInfo, "manual-trigger-history");
    });

    await test.step("delete the Monitor while retaining its trigger history", async () => {
      const row = monitorRow(page, monitorName);
      let confirmationMessage = "";
      page.once("dialog", (dialog) => {
        confirmationMessage = dialog.message();
        void dialog.accept();
      });
      const responsePromise = waitForProductResponse(
        page,
        "DELETE",
        `${monitorApiRoot}/${latestMonitor!.id}`,
      );
      await row.getByRole("button", { name: "关闭", exact: true }).click();
      const response = await responsePromise;
      expect(response.status()).toBe(202);
      expect(confirmationMessage).toBe(`关闭“${monitorName}”？历史触发记录会保留。`);
      expectIdempotencyKey(response.request());
      expect(response.request().postDataJSON()).toEqual({ expected_version: latestMonitor!.version });

      const disabled = monitorSchema.parse(await response.json());
      expect(disabled.status).toBe("disabled");
      expect(disabled.version).toBeGreaterThan(latestMonitor!.version);
      expect(disabled.latest_trigger?.id).toBe(latestMonitor!.latest_trigger?.id);
      latestMonitor = disabled;
      cleanupRequired = false;

      await expect(row).toHaveAttribute("data-status", "disabled");
      await expect(row).toContainText("已关闭");
      await expect(row).toContainText("已停止调度");
      await expect(row.getByRole("button", { name: "关闭", exact: true })).toHaveCount(0);
      await expect(row.getByRole("button", { name: "触发记录", exact: true }))
        .toHaveAttribute("aria-expanded", "true");
      await expect(row.getByText("已准入", { exact: true }).first()).toBeVisible();
      await captureCheckpoint(page, observer, testInfo, "deleted-history-retained");
    });

    assertExpectedMonitorWrites(observer, latestMonitor!.id);
    assertRuntimeClean(observer, "completed Monitor lifecycle");
  } finally {
    if (cleanupRequired && latestMonitor !== null) {
      await bestEffortDisable(page, latestMonitor, testInfo);
    }
  }
});

function assertSupportedViewport(page: Page, testInfo: TestInfo) {
  const projectName = testInfo.project.name;
  if (projectName.endsWith("desktop")) {
    expect(page.viewportSize()).toEqual({ width: 1440, height: 1000 });
    expect(Boolean(testInfo.project.use.isMobile)).toBe(false);
    return;
  }
  if (projectName.endsWith("pixel-7")) {
    expect(page.viewportSize()).toEqual({ width: 412, height: 915 });
    expect(Boolean(testInfo.project.use.isMobile)).toBe(true);
    return;
  }
  throw new Error(`real Monitor E2E does not support project ${projectName}`);
}

function uniqueMonitorName(testInfo: TestInfo): string {
  const project = testInfo.project.name.endsWith("pixel-7") ? "pixel-7" : "desktop";
  return `Monitor E2E ${project} ${Date.now().toString(36)}`;
}

function observeRuntime(page: Page): RuntimeObserver {
  const observer: RuntimeObserver = {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    serverErrors: [],
    writes: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") observer.consoleErrors.push(redactDiagnostic(message.text()));
  });
  page.on("pageerror", (error) => observer.pageErrors.push(redactDiagnostic(error.message)));
  page.on("requestfailed", (request) => {
    observer.failedRequests.push(
      `${request.method()} ${safePathname(request.url())} ${redactDiagnostic(request.failure()?.errorText ?? "unknown")}`,
    );
  });
  page.on("response", (response) => {
    if (response.status() >= 500) {
      observer.serverErrors.push(
        `${response.status()} ${response.request().method()} ${safePathname(response.url())}`,
      );
    }
  });
  page.on("request", (request) => {
    if (writeMethods.has(request.method()) && isSameOriginProductRequest(request.url())) {
      observer.writes.push(request);
    }
  });
  return observer;
}

function monitorRow(page: Page, name: string): Locator {
  return page.locator("article").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
}

async function waitForProductResponse(
  page: Page,
  method: string,
  pathname: string,
): Promise<Response> {
  return page.waitForResponse((response) => {
    return response.request().method() === method
      && safePathname(response.url()) === pathname;
  });
}

async function clickForMonitorMutation(
  page: Page,
  button: Locator,
  method: "POST" | "DELETE",
  pathname: string,
  expectedVersion: number | null,
): Promise<Monitor> {
  const responsePromise = waitForProductResponse(page, method, pathname);
  await button.click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  expectIdempotencyKey(response.request());
  if (expectedVersion === null) {
    expect(response.request().postData()).toBeNull();
  } else {
    expect(response.request().postDataJSON()).toEqual({ expected_version: expectedVersion });
  }
  return monitorSchema.parse(await response.json());
}

function expectIdempotencyKey(request: Request) {
  const key = request.headers()["idempotency-key"] ?? "";
  expect(key).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/);
}

async function waitForSchedulerActivation(page: Page, created: Monitor): Promise<Monitor> {
  let latest = created;
  await expect.poll(async () => {
    const response = await page.request.get(`${monitorApiRoot}?status=all`, {
      headers: { accept: "application/json" },
      failOnStatusCode: false,
    });
    expect(response.status(), "Monitor scheduler readiness request").toBe(200);
    const list = monitorListSchema.parse(await response.json());
    const persisted = list.items.find((item) => item.id === created.id);
    expect(persisted, "created Monitor disappeared before scheduler activation").toBeDefined();
    latest = persisted!;
    return `${latest.status}:${latest.cron_configured}`;
  }, {
    message: "Monitor worker did not configure and activate the persisted schedule",
    timeout: 90_000,
    intervals: [500, 1_000, 2_000, 5_000],
  }).toBe("active:true");
  return latest;
}

async function captureCheckpoint(
  page: Page,
  observer: RuntimeObserver,
  testInfo: TestInfo,
  phase: string,
) {
  if (!(await page.evaluate(() => "axe" in window))) {
    await page.addScriptTag({ content: axe.source });
  }
  const audit = await page.evaluate(async () => {
    const result = await (window as typeof window & { axe: typeof axe }).axe.run();
    const root = document.documentElement;
    const ids = Array.from(document.querySelectorAll<HTMLElement>("[id]"))
      .map((element) => element.id)
      .filter(Boolean);
    const counts = new Map<string, number>();
    ids.forEach((id) => counts.set(id, (counts.get(id) ?? 0) + 1));
    const controls = Array.from(document.querySelectorAll<HTMLElement>(
      "button, a[href], input:not([type='hidden']), select, textarea",
    )).filter(isVisible);
    const surfaces = Array.from(document.querySelectorAll<HTMLElement>(
      "main, article, form, fieldset, nav, section, [role='group']",
    )).filter(isVisible);
    const visibleText = document.body.innerText;

    return {
      violations: result.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        targets: violation.nodes.map((node) => node.target),
      })),
      mainCount: document.querySelectorAll("main").length,
      duplicateIds: [...counts.entries()].filter(([, count]) => count > 1).map(([id]) => id),
      unnamedControls: controls
        .filter((element) => accessibleControlName(element).length === 0)
        .map(describeElement),
      horizontalOverflow: Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0)
        - root.clientWidth,
      clippedControls: controls.filter(isHorizontallyClipped).map(describeElement),
      clippedSurfaces: surfaces.filter(isHorizontallyClipped).map(describeElement),
      overflowingSurfaces: surfaces
        .filter((element) => {
          const overflowX = window.getComputedStyle(element).overflowX;
          return !["auto", "scroll"].includes(overflowX)
            && element.scrollWidth > element.clientWidth + 1;
        })
        .map(describeElement),
      rawJson: document.querySelectorAll("pre").length > 0
        || /\bRaw JSON\b/i.test(visibleText)
        || /"(?:artifact_id|artifact_version_id|monitor_id|schedule_version|trigger_kind|task_id)"\s*:/.test(visibleText),
      leakedDomSentinels: /\b(?:undefined|null|\[object Object\])\b/.test(visibleText),
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

    function isHorizontallyClipped(element: HTMLElement) {
      const rect = element.getBoundingClientRect();
      return rect.left < -0.5 || rect.right > root.clientWidth + 0.5;
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

    function describeElement(element: HTMLElement) {
      const className = typeof element.className === "string" && element.className
        ? `.${element.className.trim().replace(/\s+/g, ".")}`
        : "";
      return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${className}`;
    }
  });

  await fs.mkdir(evidenceDirectory, { recursive: true });
  const screenshot = await page.screenshot({
    animations: "disabled",
    fullPage: true,
    path: path.join(
      evidenceDirectory,
      `${safeFileSegment(testInfo.project.name)}-${safeFileSegment(phase)}-retry-${testInfo.retry}.png`,
    ),
  });
  await testInfo.attach(`real-monitor-${phase}-${testInfo.project.name}`, {
    body: screenshot,
    contentType: "image/png",
  });
  await testInfo.attach(`real-monitor-${phase}-quality`, {
    body: Buffer.from(JSON.stringify({
      ...audit,
      consoleErrors: observer.consoleErrors,
      pageErrors: observer.pageErrors,
      failedRequests: observer.failedRequests,
      serverErrors: observer.serverErrors,
    }, null, 2)),
    contentType: "application/json",
  });

  expect(audit.violations, `${phase} axe violations`).toEqual([]);
  expect(audit.mainCount, `${phase} main landmark count`).toBe(1);
  expect(audit.duplicateIds, `${phase} duplicate DOM IDs`).toEqual([]);
  expect(audit.unnamedControls, `${phase} unnamed interactive controls`).toEqual([]);
  expect(audit.horizontalOverflow, `${phase} page overflow`).toBeLessThanOrEqual(0);
  expect(audit.clippedControls, `${phase} horizontally clipped controls`).toEqual([]);
  expect(audit.clippedSurfaces, `${phase} horizontally clipped surfaces`).toEqual([]);
  expect(audit.overflowingSurfaces, `${phase} overflowing surfaces`).toEqual([]);
  expect(audit.rawJson, `${phase} exposed raw JSON`).toBe(false);
  expect(audit.leakedDomSentinels, `${phase} leaked DOM sentinel values`).toBe(false);
  assertRuntimeClean(observer, phase);
}

function assertRuntimeClean(observer: RuntimeObserver, phase: string) {
  expect(observer.consoleErrors, `${phase} console errors`).toEqual([]);
  expect(observer.pageErrors, `${phase} page errors`).toEqual([]);
  expect(observer.failedRequests, `${phase} failed browser requests`).toEqual([]);
  expect(observer.serverErrors, `${phase} HTTP 5xx responses`).toEqual([]);
}

function assertExpectedMonitorWrites(observer: RuntimeObserver, monitorId: string) {
  const writes = observer.writes.map((request) => ({
    method: request.method(),
    pathname: safePathname(request.url()),
  }));
  expect(writes).toEqual([
    { method: "POST", pathname: monitorApiRoot },
    { method: "POST", pathname: `${monitorApiRoot}/${monitorId}/pause` },
    { method: "POST", pathname: `${monitorApiRoot}/${monitorId}/resume` },
    { method: "POST", pathname: `${monitorApiRoot}/${monitorId}/trigger` },
    { method: "DELETE", pathname: `${monitorApiRoot}/${monitorId}` },
  ]);
}

async function bestEffortDisable(page: Page, monitor: Monitor, testInfo: TestInfo) {
  let response: APIResponse | null = null;
  let latest = monitor;
  try {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      response = await page.request.delete(`${monitorApiRoot}/${monitor.id}`, {
        data: { expected_version: latest.version },
        headers: {
          accept: "application/json",
          "content-type": "application/json",
          "idempotency-key": `monitor-e2e-cleanup-${crypto.randomUUID()}`,
        },
        failOnStatusCode: false,
      });
      if (response.status() === 202) {
        monitorSchema.parse(await response.json());
        return;
      }
      if (response.status() !== 409) break;
      const listResponse = await page.request.get(`${monitorApiRoot}?status=all`, {
        headers: { accept: "application/json" },
        failOnStatusCode: false,
      });
      if (listResponse.status() !== 200) break;
      const persisted = monitorListSchema.parse(await listResponse.json()).items
        .find((item) => item.id === monitor.id);
      if (persisted === undefined) return;
      latest = persisted;
    }
  } catch {
    // The original test failure remains primary; cleanup status is attached below.
  }
  await testInfo.attach("real-monitor-cleanup-status", {
    body: `cleanup did not complete (status ${response?.status() ?? "request-failed"})`,
    contentType: "text/plain",
  });
}

function isSameOriginProductRequest(value: string): boolean {
  return safePathname(value).startsWith("/api/product/");
}

function safePathname(value: string): string {
  try {
    return new URL(value).pathname;
  } catch {
    return "invalid-url";
  }
}

function redactDiagnostic(value: string): string {
  return value
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, "Bearer <redacted>")
    .replace(/([?&](?:access_token|api_key|code|key|secret|signature|token)=)[^&#\s]+/gi, "$1<redacted>")
    .replace(/https?:\/\/[^\s"']+/gi, (url) => {
      try {
        const parsed = new URL(url);
        return `${parsed.origin}${parsed.pathname}`;
      } catch {
        return "<redacted-url>";
      }
    });
}

function safeFileSegment(value: string): string {
  return value.replace(/[^A-Za-z0-9._-]+/g, "-");
}
