import { expect, test, type Browser, type TestInfo } from "@playwright/test";


requireFlag("HOSTED_PRODUCTION_E2E");
const taskId = requiredUuid("HOSTED_PRODUCTION_TASK_ID");
const runId = requiredUuid("HOSTED_PRODUCTION_RUN_ID");
const storageState = requiredEnvironment("HOSTED_OWNER_STORAGE_STATE");

test("hosted Product keeps Task, Run and committed evidence continuous", async ({ browser }, testInfo) => {
  const context = await authenticatedContext(browser, testInfo);
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  try {
    await page.goto(`/runs/${runId}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("region", { name: "市场与研究证据" })).toBeVisible();
    await expect(page.getByRole("region", { name: "证据门禁" })).toBeVisible();
    await expect(page.getByRole("region", { name: "风险门禁" })).toBeVisible();
    await expect(page.getByLabel("模型调用审计")).toBeVisible();
    expect(await page.locator('a[href^="https://"]').count()).toBeGreaterThan(0);

    const run = await productFetch(page, `/api/v2/runs/${runId}`);
    expect(run.status).toBe(200);
    expect(record(run.body).run_id).toBe(runId);
    expect(record(run.body).task_id).toBe(taskId);
    const task = await productFetch(page, `/api/v2/tasks/${taskId}`);
    expect(task.status).toBe(200);
    expect(record(task.body).task_id).toBe(taskId);

    const geometry = await page.evaluate(() => ({
      width: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      h1: document.querySelectorAll("h1").length,
    }));
    expect(geometry.h1).toBe(1);
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width);
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

async function authenticatedContext(browser: Browser, testInfo: TestInfo) {
  const baseURL = String(testInfo.project.use.baseURL ?? "");
  assertPublicHttps(baseURL);
  return browser.newContext({baseURL, storageState});
}

async function productFetch(page: import("@playwright/test").Page, path: string) {
  return page.evaluate(async (requestPath) => {
    const response = await fetch(`/api/product${requestPath}`, {
      cache: "no-store",
      credentials: "same-origin",
      headers: {accept: "application/json"},
    });
    return {status: response.status, body: await response.json()};
  }, path);
}

function assertPublicHttps(value: string) {
  const url = new URL(value);
  if (url.protocol !== "https:" || ["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
    throw new Error("hosted production requires a public https:// origin, never localhost or 127.0.0.1");
  }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("response must be an object");
  return value as Record<string, unknown>;
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function requiredUuid(name: string): string {
  const value = requiredEnvironment(name);
  if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)) throw new Error(`${name} must be a UUID`);
  return value;
}

function requireFlag(name: string) {
  if (process.env[name] !== "1") throw new Error(`${name}=1 is required`);
}
