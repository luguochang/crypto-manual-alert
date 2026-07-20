import { expect, test, type Page, type Request, type TestInfo } from "@playwright/test";
import axe from "axe-core";

import { productTaskSchema } from "../../src/lib/schemas/product-api";


const enabled = process.env.REAL_FORK_E2E === "1";
const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const expectedProjects = {
  "fixture-desktop": {
    taskEnvironmentVariable: "REAL_FORK_TASK_ID_DESKTOP",
    runEnvironmentVariable: "REAL_FORK_SOURCE_RUN_ID_DESKTOP",
    viewport: { width: 1440, height: 1000 },
  },
  "fixture-pixel-7": {
    taskEnvironmentVariable: "REAL_FORK_TASK_ID_MOBILE",
    runEnvironmentVariable: "REAL_FORK_SOURCE_RUN_ID_MOBILE",
    viewport: { width: 412, height: 915 },
  },
} as const;

test.skip(!enabled, "set REAL_FORK_E2E=1 with a real forkable Product Run");

test("forks a historical Product Run through the rendered UI", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const { taskId, sourceRunId, viewport } = forkContextForProject(testInfo);
  expect(page.viewportSize()).toEqual(viewport);
  const writes: Request[] = [];
  page.on("request", (request) => {
    if (writeMethods.has(request.method())) writes.push(request);
  });

  const taskPath = `/api/product/api/v2/tasks/${taskId}`;
  const forkPath = `${taskPath}/fork`;
  await page.goto(`/work?task=${taskId}&run=${sourceRunId}`);

  const panel = page.locator("section.fork-panel");
  await expect(panel.getByRole("heading", { name: "创建分析分支", exact: true })).toBeVisible();
  await expect(panel.getByLabel("源运行")).toHaveValue(sourceRunId);
  await expect(panel.getByRole("button", { name: "创建分支", exact: true })).toBeEnabled();
  await expect(page.locator("body")).not.toContainText(/checkpoint_id|checkpoint map|namespace/i);
  await assertPageQuality(page, "historical fork ready");
  await expect(panel).toHaveScreenshot("historical-fork-panel.png", {
    animations: "disabled",
    mask: [panel.getByLabel("源运行")],
    maskColor: "#d8dde0",
    maxDiffPixelRatio: 0.01,
  });

  const forkResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST" && url.pathname === forkPath;
  });
  await panel.getByRole("button", { name: "创建分支", exact: true }).click();
  const forkResponse = await forkResponsePromise;
  expect(forkResponse.status()).toBe(202);
  const accepted = productTaskSchema.parse(await forkResponse.json());
  expect(accepted.task_id).toBe(taskId);
  expect(["queued", "running", "waiting_human"]).toContain(accepted.status);

  const forkWrites = writes.filter((request) => new URL(request.url()).pathname === forkPath);
  expect(forkWrites).toHaveLength(1);
  expect(forkWrites[0]?.postDataJSON()).toEqual({ source_run_id: sourceRunId });
  expect(forkWrites[0]?.headers()["idempotency-key"]).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]+$/);
  expect(writes.some((request) => {
    const path = new URL(request.url()).pathname;
    return path.startsWith("/api/agent/") || path.startsWith("/threads/") || path.startsWith("/runs/");
  })).toBe(false);

  await expect(page).toHaveURL(new RegExp(`/work\\?task=${taskId}$`));
  await expect(page.getByRole("heading", { name: "分支已排队", exact: true })).toBeVisible();
  await expect(page.getByTestId("task-status").getByRole("heading")).toHaveText("等待人工确认", {
    timeout: 30_000,
  });
  await expect(page.locator("section.hitl-review-panel")).toHaveCount(1);
  await assertPageQuality(page, "forked run waiting for review");
  await attachScreenshot(page, testInfo);
});

function forkContextForProject(testInfo: TestInfo) {
  const project = expectedProjects[testInfo.project.name as keyof typeof expectedProjects];
  if (project === undefined) {
    throw new Error(`real Fork E2E does not support ${testInfo.project.name}`);
  }
  const taskId = process.env[project.taskEnvironmentVariable]?.trim().toLowerCase() ?? "";
  const sourceRunId = process.env[project.runEnvironmentVariable]?.trim().toLowerCase() ?? "";
  if (!uuidPattern.test(taskId)) {
    throw new Error(`${project.taskEnvironmentVariable} must contain a Product Task UUID`);
  }
  if (!uuidPattern.test(sourceRunId)) {
    throw new Error(`${project.runEnvironmentVariable} must contain a Product Run UUID`);
  }
  return { taskId, sourceRunId, viewport: project.viewport };
}

async function assertPageQuality(page: Page, phase: string) {
  await page.addScriptTag({ content: axe.source });
  const audit = await page.evaluate(async () => {
    const axeRuntime = (window as typeof window & {
      axe: { run: () => Promise<{ violations: Array<{ id: string; impact: string | null }> }> };
    }).axe;
    const violations = (await axeRuntime.run()).violations.map(({ id, impact }) => ({ id, impact }));
    const root = document.documentElement;
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
    return {
      violations,
      horizontalOverflow: Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0)
        - root.clientWidth,
      clippedControls: visibleControls.filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -0.5 || rect.right > root.clientWidth + 0.5;
      }).map((element) => element.outerHTML.slice(0, 160)),
      overflowingForkPanels: Array.from(document.querySelectorAll<HTMLElement>(
        ".fork-panel, .fork-form, .fork-source-control",
      )).filter((element) => element.scrollWidth - element.clientWidth > 1)
        .map((element) => element.className),
    };
  });
  expect(audit.violations, `${phase} has accessibility violations`).toEqual([]);
  expect(audit.horizontalOverflow, `${phase} has horizontal overflow`).toBeLessThanOrEqual(0);
  expect(audit.clippedControls, `${phase} has clipped controls`).toEqual([]);
  expect(audit.overflowingForkPanels, `${phase} has overflowing fork controls`).toEqual([]);
}

async function attachScreenshot(page: Page, testInfo: TestInfo) {
  await page.evaluate(() => window.scrollTo({
    behavior: "instant",
    left: 0,
    top: document.documentElement.scrollHeight,
  }));
  const body = await page.screenshot({ animations: "disabled", fullPage: true });
  await testInfo.attach(`real-fork-${testInfo.project.name}`, {
    body,
    contentType: "image/png",
  });
}
