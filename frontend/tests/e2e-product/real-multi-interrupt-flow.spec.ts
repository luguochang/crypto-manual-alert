import {
  expect,
  test,
  type Page,
  type Request,
  type Response,
  type TestInfo,
} from "@playwright/test";
import axe from "axe-core";

import { reviewItemIdentity } from "../../src/features/work/human-review-panel";
import {
  productTaskSchema,
  respondAllInterruptsSchema,
  type ProductTask,
} from "../../src/lib/schemas/product-api";

const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const projects: Record<string, {
  taskEnvironmentVariable: "MULTI_INTERRUPT_TASK_ID_DESKTOP" | "MULTI_INTERRUPT_TASK_ID_MOBILE";
  viewport: { width: number; height: number };
}> = {
  "fixture-desktop": {
    taskEnvironmentVariable: "MULTI_INTERRUPT_TASK_ID_DESKTOP",
    viewport: { width: 1440, height: 1000 },
  },
  "fixture-pixel-7": {
    taskEnvironmentVariable: "MULTI_INTERRUPT_TASK_ID_MOBILE",
    viewport: { width: 412, height: 915 },
  },
};

test.skip(
  process.env.REAL_MULTI_INTERRUPT_E2E !== "1",
  "set REAL_MULTI_INTERRUPT_E2E=1 to run the real aggregate HITL chain",
);

test("submits one Product command for a real two-member fixture pause", async ({ page }, testInfo) => {
  test.setTimeout(300_000);
  testInfo.annotations.push({
    type: "scope",
    description: "Validates the real Product/API/browser chain against the multi-interrupt fixture; it is not canonical provider-graph provenance.",
  });
  const project = projects[testInfo.project.name];
  if (project === undefined) {
    throw new Error(`aggregate HITL E2E does not support ${testInfo.project.name}`);
  }
  expect(page.viewportSize()).toEqual(project.viewport);
  const taskId = process.env[project.taskEnvironmentVariable];
  if (!taskId || !uuidPattern.test(taskId)) {
    throw new Error(`${project.taskEnvironmentVariable} must contain a real Product task UUID`);
  }

  const observer = installObserver(page);
  const taskPath = `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}`;
  const respondPath = `${taskPath}/interrupts/respond-all`;
  const initialResponse = page.waitForResponse(
    (response) => isTaskRead(response, taskPath),
    { timeout: 30_000 },
  );
  await page.goto(`/work?task=${encodeURIComponent(taskId)}`);

  const waitingTask = await parseTask(await initialResponse);
  expect(waitingTask.status).toBe("waiting_human");
  const runtimeIdentity = waitingTask.agent_stream;
  if (runtimeIdentity === null) {
    throw new Error("real fixture task must expose its official Agent runtime identity");
  }
  testInfo.annotations.push({
    type: "runtime-evidence-boundary",
    description: "The gate verifies the official current ThreadState metadata, active root/nested tasks, and interrupt IDs through the read-only same-origin Agent BFF. Child checkpoint-map lineage remains covered by the backend fixed-version Runtime integration test.",
  });
  expect(runtimeIdentity.assistant_id).toMatch(uuidPattern);
  expect(runtimeIdentity.thread_id).toMatch(uuidPattern);
  expect(runtimeIdentity.run_id).toMatch(uuidPattern);
  const pause = waitingTask.pending_interrupts;
  if (pause === null) throw new Error("real task did not project its interrupt pause");
  expect(pause.status).toBe("pending");
  expect(pause.members).toHaveLength(2);
  expect(new Set(pause.members.map((member) => member.interrupt_id)).size).toBe(2);
  expect(pause.members.some((member) => member.payload.artifact.status !== "draft")).toBe(false);
  assertNoRuntimeCoordinates(pause);
  const officialStateResponse = await page.request.get(
    `/api/agent/threads/${encodeURIComponent(runtimeIdentity.thread_id)}/state`,
  );
  expect(officialStateResponse.ok()).toBe(true);
  const officialEvidence = assertOfficialMultiInterruptState(
    await officialStateResponse.json(),
    {
      taskId,
      runId: runtimeIdentity.run_id,
      interruptIds: pause.members.map((member) => member.interrupt_id),
    },
  );
  await testInfo.attach("official-runtime-state-evidence", {
    body: Buffer.from(JSON.stringify({
      assistant_id: runtimeIdentity.assistant_id,
      thread_id: runtimeIdentity.thread_id,
      run_id: runtimeIdentity.run_id,
      ...officialEvidence,
    }, null, 2)),
    contentType: "application/json",
  });

  const panels = page.locator("section.hitl-review-panel");
  await expect(panels).toHaveCount(2);
  const reviewIdentities = pause.members.map((member, index) => reviewItemIdentity(
    member,
    { index: index + 1, total: pause.members.length },
  ));
  expect(new Set(reviewIdentities).size).toBe(reviewIdentities.length);
  for (const identity of reviewIdentities) {
    await expect(page.getByRole("region", {
      name: `分析草稿待人工确认：${identity}`,
      exact: true,
    })).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "提交整组审核决定", exact: true })).toBeVisible();
  const batchSubmit = page.getByRole("button", { name: "确认提交 2 项决定", exact: true });
  await expect(batchSubmit).toBeDisabled();
  await assertPageQuality(page, "pending aggregate", true);

  const comments = pause.members.map((_, index) =>
    `Playwright ${testInfo.project.name} aggregate approval ${index + 1}`);
  const chooseApprovalWithKeyboard = async (index: number, draftedCount: number) => {
    const identity = reviewIdentities[index]!;
    const panel = page.getByRole("region", {
      name: `分析草稿待人工确认：${identity}`,
      exact: true,
    });
    const approveTrigger = panel.getByRole("button", {
      name: `${identity}：批准`,
      exact: true,
    });
    await expect(panel.getByRole("group", {
      name: `${identity}的审核决定`,
      exact: true,
    })).toBeVisible();
    await approveTrigger.focus();
    await expect(approveTrigger).toBeFocused();
    await page.keyboard.press(index === 0 ? "Enter" : "Space");
    await expect(panel.getByRole("heading", { name: "确认批准这份分析？", exact: true }))
      .toBeVisible();
    await expect(panel.getByText(
      "在本页选择后仍需提交整组决定，Agent 才会恢复运行。",
      { exact: true },
    )).toBeVisible();
    await panel.getByRole("textbox", {
      name: `${identity}：审核备注（可选）`,
      exact: true,
    }).fill(comments[index]!);
    const selectApproval = panel.getByRole("button", {
      name: `${identity}：在本页选择批准`,
      exact: true,
    });
    await selectApproval.focus();
    await page.keyboard.press(index === 0 ? "Enter" : "Space");
    await expect(approveTrigger).toBeFocused();
    await expect(panel.getByText(
      "已在本页选择批准，尚未提交到服务端；可继续修改。",
      { exact: true },
    )).toBeVisible();
    await expect(page.getByText(
      `本页已选择 ${draftedCount} / ${pause.members.length} 项决定；全部完成后可一次提交。`,
      { exact: true },
    )).toHaveAttribute("aria-live", "polite");
    expect(observer.writes.filter((item) => item.pathname === respondPath)).toEqual([]);
  };

  await chooseApprovalWithKeyboard(0, 1);
  expect(await dispatchSyntheticBeforeUnload(page)).toEqual({
    cancelled: true,
    defaultPrevented: true,
  });

  await page.evaluate(() => {
    const url = new URL(window.location.href);
    url.hash = "draft-navigation-test";
    window.history.pushState(window.history.state, "", url);
  });
  const popstateTaskRead = page.waitForResponse(
    (response) => isTaskRead(response, taskPath),
    { timeout: 30_000 },
  );
  await page.goBack();
  await parseTask(await popstateTaskRead);
  await expect(panels).toHaveCount(2);
  await expect(page.getByText(
    "本页已选择 0 / 2 项决定；全部完成后可一次提交。",
    { exact: true },
  )).toBeVisible();
  await expect(page.getByText(
    "已在本页选择批准，尚未提交到服务端；可继续修改。",
    { exact: true },
  )).toHaveCount(0);
  await expect(batchSubmit).toBeDisabled();
  expect(await dispatchSyntheticBeforeUnload(page)).toEqual({
    cancelled: false,
    defaultPrevented: false,
  });
  expect(observer.writes.filter((item) => item.pathname === respondPath)).toEqual([]);

  await chooseApprovalWithKeyboard(0, 1);
  await chooseApprovalWithKeyboard(1, 2);

  await expect(batchSubmit).toBeEnabled();
  await expect(page.getByText("本页已选择 2 / 2 项决定；全部完成后可一次提交。", { exact: true }))
    .toBeVisible();
  await expect(page.locator('[data-state="auth_error"], [data-state="invalid_request"], [data-state="network_error"]'))
    .toHaveCount(0);
  const aggregateMarkup = await page.locator(".hitl-review-stack").evaluate((element) => element.outerHTML);
  expect(aggregateMarkup).not.toMatch(/(?:checkpoint_id|checkpoint_map|namespace|projection_id)/i);
  await attachAggregateScreenshot(page, testInfo, "prepared");
  await assertPageQuality(page, "prepared aggregate", true);

  const respondResponsePromise = page.waitForResponse(
    (response) => observed(response.request()).method === "POST"
      && observed(response.request()).pathname === respondPath,
    { timeout: 30_000 },
  );
  const succeededResponsePromise = page.waitForResponse(
    (response) => isSucceededTaskRead(response, taskPath, taskId),
    { timeout: 240_000 },
  );
  await batchSubmit.focus();
  await expect(batchSubmit).toBeFocused();
  await page.keyboard.press("Enter");

  const respondResponse = await respondResponsePromise;
  expect(respondResponse.status()).toBe(202);
  const request = respondResponse.request();
  expect(request.headers()["idempotency-key"]).toMatch(uuidPattern);
  const submission = respondAllInterruptsSchema.parse(request.postDataJSON());
  expect(submission.pause_id).toBe(pause.pause_id);
  expect(submission.pause_version).toBe(pause.pause_version);
  expect(submission.responses).toHaveLength(2);
  expect(new Set(submission.responses.map((item) => item.interrupt_id))).toEqual(
    new Set(pause.members.map((member) => member.interrupt_id)),
  );
  expect(submission.responses.map((item) => item.response.comment)).toEqual(comments);
  expect(submission.responses.every((item) => item.response.action === "approve")).toBe(true);
  assertNoRuntimeCoordinates(submission);

  const respondingTask = await parseTask(respondResponse);
  expect(respondingTask.pending_interrupts?.status).toBe("responding");
  expect(respondingTask.pending_interrupts?.members).toHaveLength(2);
  expect(respondingTask.pending_interrupts?.members.every(
    (member) => member.status === "responding" && member.response?.action === "approve",
  )).toBe(true);

  const succeededTask = await parseTask(await succeededResponsePromise);
  expect(succeededTask.status).toBe("succeeded");
  expect(succeededTask.pending_interrupts).toBeNull();
  expect(succeededTask.artifact?.status).toBe("committed");
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText("分析完成", {
    timeout: 30_000,
  });
  await expect(panels).toHaveCount(0);
  await assertPageQuality(page, "completed aggregate", true);
  await attachAggregateScreenshot(page, testInfo, "completed");

  expect(observer.writes.filter((item) => item.pathname === respondPath)).toEqual([
    { method: "POST", pathname: respondPath },
  ]);
  expect(observer.writes.filter((item) =>
    item.pathname.startsWith("/api/product/") && item.pathname !== respondPath)).toEqual([]);
  expect(observer.writes.filter((item) =>
    item.pathname.startsWith("/api/agent/")
    && !item.pathname.endsWith("/stream/events")
    && !item.pathname.endsWith("/history"))).toEqual([]);
  expect(observer.consoleErrors).toEqual([]);
  expect(observer.pageErrors).toEqual([]);
  expect(observer.serverErrors).toEqual([]);
});

interface Observer {
  writes: Array<{ method: string; pathname: string }>;
  consoleErrors: string[];
  pageErrors: string[];
  serverErrors: string[];
}

function installObserver(page: Page): Observer {
  const observer: Observer = { writes: [], consoleErrors: [], pageErrors: [], serverErrors: [] };
  page.on("request", (request) => {
    const item = observed(request);
    if (writeMethods.has(item.method)) observer.writes.push(item);
  });
  page.on("console", (message) => {
    if (message.type() === "error") observer.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => observer.pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      const item = observed(response.request());
      observer.serverErrors.push(`${response.status()} ${item.method} ${item.pathname}`);
    }
  });
  return observer;
}

function observed(request: Request) {
  return { method: request.method().toUpperCase(), pathname: new URL(request.url()).pathname };
}

function isTaskRead(response: Response, taskPath: string) {
  const item = observed(response.request());
  return response.ok()
    && item.method === "GET"
    && item.pathname === taskPath
    && (response.headers()["content-type"] ?? "").includes("application/json");
}

async function isSucceededTaskRead(response: Response, taskPath: string, taskId: string) {
  if (!isTaskRead(response, taskPath)) return false;
  try {
    const task = productTaskSchema.parse(await response.json());
    return task.task_id === taskId && task.status === "succeeded";
  } catch {
    return false;
  }
}

async function parseTask(response: Response): Promise<ProductTask> {
  expect(response.headers()["content-type"] ?? "").toContain("application/json");
  return productTaskSchema.parse(await response.json());
}

async function dispatchSyntheticBeforeUnload(page: Page) {
  return page.evaluate(() => {
    const event = new Event("beforeunload", { cancelable: true });
    const dispatched = window.dispatchEvent(event);
    return {
      cancelled: !dispatched,
      defaultPrevented: event.defaultPrevented,
    };
  });
}

function assertNoRuntimeCoordinates(value: unknown) {
  const forbidden = new Set(["checkpoint_id", "checkpoint_map", "namespace", "projection_id", "run_id"]);
  const found: string[] = [];
  visit(value, "$");
  expect(found, "public aggregate contract exposed Runtime coordinates").toEqual([]);

  function visit(candidate: unknown, path: string) {
    if (Array.isArray(candidate)) {
      candidate.forEach((item, index) => visit(item, `${path}[${index}]`));
      return;
    }
    if (candidate === null || typeof candidate !== "object") return;
    for (const [key, nested] of Object.entries(candidate)) {
      if (forbidden.has(key)) found.push(`${path}.${key}`);
      visit(nested, `${path}.${key}`);
    }
  }
}

function assertOfficialMultiInterruptState(
  value: unknown,
  expected: Readonly<{ taskId: string; runId: string; interruptIds: string[] }>,
) {
  const state = requiredRecord(value, "official ThreadState");
  const metadata = requiredRecord(state.metadata, "official ThreadState metadata");
  expect(metadata.fixture_kind).toBe("multi_interrupt");
  expect(metadata.task_id).toBe(expected.taskId);
  expect(metadata.run_id).toBe(expected.runId);
  const next = requiredStringArray(state.next, "official ThreadState next");
  expect(new Set(next)).toEqual(new Set(["root_interrupt", "nested_review"]));
  const tasks = requiredArray(state.tasks, "official ThreadState tasks").map((candidate) =>
    requiredRecord(candidate, "official ThreadState task"));
  const activeTasks = tasks.filter((task) =>
    task.name === "root_interrupt" || task.name === "nested_review");
  expect(activeTasks).toHaveLength(2);
  const officialInterruptIds = activeTasks.flatMap((task) =>
    requiredArray(task.interrupts, "official task interrupts").map((candidate) => {
      const interrupt = requiredRecord(candidate, "official task interrupt");
      if (typeof interrupt.id !== "string" || interrupt.id.length === 0) {
        throw new Error("official task interrupt has no stable ID");
      }
      return interrupt.id;
    }));
  expect(new Set(officialInterruptIds)).toEqual(new Set(expected.interruptIds));
  return {
    fixture_kind: metadata.fixture_kind,
    checkpoint_run_id: metadata.run_id,
    active_tasks: activeTasks.map((task) => task.name),
    official_interrupt_ids: officialInterruptIds,
    same_superstep_verified: true,
  };
}

function requiredRecord(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requiredArray(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function requiredStringArray(value: unknown, label: string): string[] {
  const items = requiredArray(value, label);
  if (items.some((item) => typeof item !== "string")) {
    throw new Error(`${label} must contain only strings`);
  }
  return items as string[];
}

async function assertPageQuality(page: Page, phase: string, runAxe: boolean) {
  if (runAxe) {
    const hasAxe = await page.evaluate(() => "axe" in window);
    if (!hasAxe) await page.addScriptTag({ content: axe.source });
    const violations = await page.evaluate(async () => {
      const runtime = (window as typeof window & {
        axe: { run: () => Promise<{ violations: Array<{
          id: string;
          impact: string | null;
          nodes: Array<{ target: unknown; html: string }>;
        }> }> };
      }).axe;
      return (await runtime.run()).violations.map(({ id, impact, nodes }) => ({
        id,
        impact,
        nodes: nodes.map(({ target, html }) => ({ target, html })),
      }));
    });
    expect(violations, `${phase} has accessibility violations`).toEqual([]);
  }

  const audit = await page.evaluate(() => {
    const root = document.documentElement;
    const visibleControls = Array.from(document.querySelectorAll<HTMLElement>(
      "button, a[href], input:not([type='hidden']), select, textarea",
    )).filter((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return element.getClientRects().length > 0 && rect.width > 0 && rect.height > 0
        && style.display !== "none" && style.visibility !== "hidden";
    });
    return {
      horizontalOverflow: Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0)
        - root.clientWidth,
      clippedControls: visibleControls.filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -0.5 || rect.right > root.clientWidth + 0.5;
      }).map((element) => element.outerHTML.slice(0, 160)),
      overflowingSurfaces: Array.from(document.querySelectorAll<HTMLElement>(
        ".hitl-review-panel, .hitl-confirmation, .task-command-bar",
      )).filter((element) => element.scrollWidth - element.clientWidth > 1)
        .map((element) => element.className),
      preCount: document.querySelectorAll("pre").length,
    };
  });
  expect(audit.horizontalOverflow, `${phase} has horizontal overflow`).toBeLessThanOrEqual(0);
  expect(audit.clippedControls, `${phase} has clipped controls`).toEqual([]);
  expect(audit.overflowingSurfaces, `${phase} has overflowing surfaces`).toEqual([]);
  expect(audit.preCount, `${phase} rendered raw preformatted data`).toBe(0);
}

async function attachAggregateScreenshot(page: Page, testInfo: TestInfo, phase: string) {
  const target = phase === "prepared"
    ? page.getByRole("heading", { name: "提交整组审核决定", exact: true })
    : page.getByTestId("analysis-result");
  await target.scrollIntoViewIfNeeded();
  const scroll = await page.evaluate(() => ({
    scrollY: window.scrollY,
    maximum: Math.max(0, document.documentElement.scrollHeight - window.innerHeight),
  }));
  expect(scroll.maximum).toBeGreaterThan(0);
  expect(scroll.scrollY).toBeGreaterThan(0);
  await expect(target).toBeInViewport();
  await testInfo.attach(`real-multi-interrupt-${phase}-${testInfo.project.name}`, {
    body: await page.screenshot({ animations: "disabled" }),
    contentType: "image/png",
  });
}
