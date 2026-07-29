import {
  expect,
  test,
  type Page,
  type Request as PlaywrightRequest,
  type Response as PlaywrightResponse,
  type TestInfo,
} from "@playwright/test";
import axe from "axe-core";

import {
  productTaskSchema,
  type ProductTask,
} from "../../src/lib/schemas/product-api";

const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const editedSummary = "BTC 机构采用仍在推进，但结论已按人工审核收窄。";

const projects = {
  "fixture-desktop": {
    taskEnvironmentVariable: "DEEP_RESEARCH_HITL_TASK_ID_DESKTOP",
    viewport: { width: 1440, height: 1000 },
    action: "edit_then_approve",
  },
  "fixture-pixel-7": {
    taskEnvironmentVariable: "DEEP_RESEARCH_HITL_TASK_ID_MOBILE",
    viewport: { width: 412, height: 915 },
    action: "reject",
  },
} as const;

test.skip(
  process.env.REAL_PRODUCT_E2E !== "1"
    || process.env.CONTROLLED_DEEP_RESEARCH_HITL_E2E !== "1",
  "set REAL_PRODUCT_E2E=1 and CONTROLLED_DEEP_RESEARCH_HITL_E2E=1 to run the local controlled post-draft HITL chain",
);

test("persists Deep Research review decisions through Product and official Agent runtime", async ({ page }, testInfo) => {
  test.setTimeout(300_000);
  const project = projectConfiguration(page, testInfo);
  const taskId = requiredTaskId(project.taskEnvironmentVariable);
  const taskPath = `/api/product/api/v2/tasks/${taskId}`;
  const respondPath = `${taskPath}/interrupts/respond-all`;
  const observer = installBrowserObserver(page);
  const initialRead = page.waitForResponse((response) => isTaskRead(response, taskPath));

  await page.goto(`/work?task=${taskId}`);
  const initial = await parseTask(await initialRead);
  assertPendingResearch(initial, taskId, 1);
  await assertPendingPanel(page);
  await assertPageQuality(page, `research-review-${testInfo.project.name}-round-1`, testInfo);

  if (project.action === "edit_then_approve") {
    const secondRoundRead = page.waitForResponse(async (response) => {
      if (!isTaskRead(response, taskPath)) return false;
      const task = await safeParseTask(response);
      return task?.status === "waiting_human"
        && task.pending_interrupts?.members[0]?.payload.kind === "deep_research_review"
        && task.pending_interrupts.members[0].payload.review_iteration === 2;
    }, { timeout: 180_000 });
    const editResponse = page.waitForResponse(
      (response) => isResponseFor(response, "POST", respondPath),
      { timeout: 30_000 },
    );

    await page.getByRole("button", { name: "修改后重审", exact: true }).click();
    await page.getByRole("textbox", { name: "执行摘要", exact: true }).fill(editedSummary);
    await page.getByRole("textbox", { name: "修改说明（可选）", exact: true }).fill("收窄结论并保留原始来源目录。");
    await page.getByRole("button", { name: "提交修改并重审", exact: true }).click();
    expect((await editResponse).status()).toBe(202);

    const secondRound = await parseTask(await secondRoundRead);
    assertPendingResearch(secondRound, taskId, 2);
    await expect(page.getByText(editedSummary, { exact: true })).toBeVisible({ timeout: 30_000 });
    await assertPendingPanel(page);
    await assertPageQuality(page, "research-review-desktop-round-2", testInfo);

    const approveResponse = page.waitForResponse(
      (response) => isResponseFor(response, "POST", respondPath),
      { timeout: 30_000 },
    );
    const succeededRead = page.waitForResponse(async (response) => {
      if (!isTaskRead(response, taskPath)) return false;
      const task = await safeParseTask(response);
      return task?.status === "succeeded";
    }, { timeout: 180_000 });

    await page.getByRole("button", { name: "批准", exact: true }).click();
    await expect(page.getByRole("heading", { name: "确认批准这份研究报告？", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "确认批准", exact: true }).click();
    expect((await approveResponse).status()).toBe(202);

    const succeeded = await parseTask(await succeededRead);
    expect(succeeded.deep_research_artifact?.status).toBe("committed");
    expect(succeeded.deep_research_artifact?.report.executive_summary).toBe(editedSummary);
    await expect(page.getByRole("heading", { name: "深度研究已完成", exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(editedSummary, { exact: true })).toBeVisible();
    await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
    expect(writesTo(observer, respondPath)).toHaveLength(2);
  } else {
    const rejectResponse = page.waitForResponse(
      (response) => isResponseFor(response, "POST", respondPath),
      { timeout: 30_000 },
    );
    const blockedRead = page.waitForResponse(async (response) => {
      if (!isTaskRead(response, taskPath)) return false;
      const task = await safeParseTask(response);
      return task?.status === "blocked";
    }, { timeout: 180_000 });

    await page.getByRole("button", { name: "拒绝", exact: true }).click();
    await expect(page.getByRole("heading", { name: "确认拒绝这份研究报告？", exact: true })).toBeVisible();
    await page.getByLabel("审核备注（可选）", { exact: true }).fill("当前证据覆盖不足，不提交报告版本。");
    await page.getByRole("button", { name: "确认拒绝", exact: true }).click();
    expect((await rejectResponse).status()).toBe(202);

    const blocked = await parseTask(await blockedRead);
    expect(blocked.status).toBe("blocked");
    expect(blocked.deep_research_artifact).toBeNull();
    await expect(page.getByRole("heading", { name: "研究已阻断", exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
    expect(writesTo(observer, respondPath)).toHaveLength(1);
  }

  await assertPageQuality(page, `research-review-${testInfo.project.name}-terminal`, testInfo);
  const terminalUrl = page.url();
  await page.reload();
  await expect(page).toHaveURL(terminalUrl);
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(0);
  await assertPageQuality(page, `research-review-${testInfo.project.name}-reload`, testInfo);

  expect(observer.consoleErrors).toEqual([]);
  expect(observer.pageErrors).toEqual([]);
  expect(observer.serverErrors).toEqual([]);
});

function projectConfiguration(page: Page, testInfo: TestInfo) {
  const project = projects[testInfo.project.name as keyof typeof projects];
  if (!project) throw new Error(`unsupported project ${testInfo.project.name}`);
  expect(page.viewportSize()).toEqual(project.viewport);
  return project;
}

function requiredTaskId(environmentVariable: string) {
  const taskId = process.env[environmentVariable]?.trim().toLowerCase();
  if (!taskId || !/^[0-9a-f-]{36}$/.test(taskId)) {
    throw new Error(`${environmentVariable} must contain a Product Task UUID`);
  }
  return taskId;
}

function assertPendingResearch(task: ProductTask, taskId: string, iteration: number) {
  expect(task.task_id).toBe(taskId);
  expect(task.task_type).toBe("deep_research");
  expect(task.status).toBe("waiting_human");
  const member = task.pending_interrupts?.members[0];
  expect(member?.payload.kind).toBe("deep_research_review");
  if (member?.payload.kind !== "deep_research_review") {
    throw new Error("missing Deep Research review payload");
  }
  expect(member.payload.review_iteration).toBe(iteration);
  expect(member.payload.artifact.status).toBe("draft");
}

async function assertPendingPanel(page: Page) {
  const panel = page.locator("section.hitl-review-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: "研究报告草稿待人工确认", exact: true })).toBeVisible();
  await expect(panel.getByRole("link", { name: /Verified institutional source/ })).toBeVisible();
}

async function parseTask(response: PlaywrightResponse) {
  return productTaskSchema.parse(await response.json());
}

async function safeParseTask(response: PlaywrightResponse): Promise<ProductTask | null> {
  try {
    const parsed = productTaskSchema.safeParse(await response.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

function isTaskRead(response: PlaywrightResponse, taskPath: string) {
  return response.ok() && isResponseFor(response, "GET", taskPath);
}

function isResponseFor(response: PlaywrightResponse, method: string, pathname: string) {
  const request = response.request();
  return request.method().toUpperCase() === method && new URL(request.url()).pathname === pathname;
}

function installBrowserObserver(page: Page) {
  const observer = {
    writes: [] as Array<{ method: string; pathname: string }>,
    consoleErrors: [] as string[],
    pageErrors: [] as string[],
    serverErrors: [] as string[],
  };
  page.on("request", (request: PlaywrightRequest) => {
    const method = request.method().toUpperCase();
    if (writeMethods.has(method)) {
      observer.writes.push({ method, pathname: new URL(request.url()).pathname });
    }
  });
  page.on("console", (message) => {
    if (message.type() === "error") observer.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => observer.pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      observer.serverErrors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });
  return observer;
}

function writesTo(observer: ReturnType<typeof installBrowserObserver>, pathname: string) {
  return observer.writes.filter((write) => write.pathname === pathname);
}

async function assertPageQuality(page: Page, label: string, testInfo: TestInfo) {
  await page.addScriptTag({ content: axe.source });
  const audit = await page.evaluate(async () => {
    const result = await (window as typeof window & { axe: typeof axe }).axe.run();
    const ids = Array.from(document.querySelectorAll<HTMLElement>("[id]")).map((element) => element.id);
    const unnamedControls = Array.from(document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"))
      .filter((element) => {
        const labelledBy = (element.getAttribute("aria-labelledby") ?? "")
          .split(/\s+/)
          .filter(Boolean)
          .map((id) => document.getElementById(id)?.textContent ?? "")
          .join(" ");
        const labels = "labels" in element
          ? Array.from((element as HTMLInputElement).labels ?? []).map((item) => item.textContent ?? "").join(" ")
          : "";
        return !(element.getAttribute("aria-label") || labelledBy || labels || element.textContent || "").trim();
      }).length;
    return {
      violations: result.violations.map((violation) => ({
        id: violation.id,
        nodes: violation.nodes.map((node) => ({
          target: node.target,
          failureSummary: node.failureSummary,
        })),
      })),
      duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index),
      unnamedControls,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      rawJson: /\"(?:artifact_type|source_indexes|deep_research_artifact)\"\s*:/.test(document.body.innerText),
    };
  });
  expect(audit.violations).toEqual([]);
  expect(audit.duplicateIds).toEqual([]);
  expect(audit.unnamedControls).toBe(0);
  expect(audit.overflow).toBeLessThanOrEqual(0);
  expect(audit.rawJson).toBe(false);
  await testInfo.attach(label, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
}
