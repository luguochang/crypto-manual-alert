import {
  expect,
  test,
  type Page,
  type Request,
  type Response,
  type TestInfo,
} from "@playwright/test";
import axe from "axe-core";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import {
  dataDeletionSchema,
  dataExportBundleSchema,
  dataExportManifestSchema,
  dataExportSchema,
  dataLifecyclePolicySchema,
  type DataLifecyclePolicy,
} from "../../src/lib/schemas/product-api";


const settingsPath = "/settings?section=data-lifecycle";
const lifecycleRoot = "/api/product/api/v2/data-lifecycle";
const policyPath = `${lifecycleRoot}/policy`;
const exportRoot = `${lifecycleRoot}/exports`;
const deletionRoot = `${lifecycleRoot}/deletions`;
const evidenceRoot = process.env.PLAYWRIGHT_EVIDENCE_DIR?.trim() ?? "";
const evidenceDirectory = path.join(evidenceRoot, "visual");
const realEnvironmentReady =
  process.env.REAL_DATA_LIFECYCLE_E2E === "1"
  && path.isAbsolute(evidenceRoot);
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const terminalExportStatuses = new Set(["succeeded", "failed"]);
const isolationConfirmation = "DELETE_ISOLATED_E2E_ACTOR_DATA";
const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

type RuntimeObserver = {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: string[];
  serverErrors: string[];
  productResponses: Response[];
  writes: Request[];
};

test.skip(
  !realEnvironmentReady,
  "requires REAL_DATA_LIFECYCLE_E2E=1, an absolute PLAYWRIGHT_EVIDENCE_DIR, and live Product/Lifecycle workers",
);

test("real data lifecycle loads policy, exports a verified bundle, and rejoins after refresh", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  assertSupportedViewport(page, testInfo);
  const observer = observeRuntime(page);

  const initialPolicyResponse = waitForProductResponse(page, "GET", policyPath);
  await page.goto(settingsPath);
  const policyResponse = await initialPolicyResponse;
  expect(policyResponse.status()).toBe(200);
  const policy = dataLifecyclePolicySchema.parse(await policyResponse.json());

  await expect(page.getByRole("heading", { name: "数据与隐私", exact: true })).toBeVisible();
  await assertPolicyRendered(page, policy);
  await captureCheckpoint(page, observer, testInfo, "policy-loaded");

  const admissionResponsePromise = waitForProductResponse(page, "POST", exportRoot);
  await page.getByRole("button", { name: "生成新的导出", exact: true }).click();
  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.status()).toBe(202);
  expectIdempotencyKey(admissionResponse.request());
  expect(admissionResponse.request().postDataJSON()).toEqual({ scope: "user_data" });

  const admitted = dataExportSchema.parse(await admissionResponse.json());
  expect(admitted).toMatchObject({
    tenant_id: policy.tenant_id,
    workspace_id: policy.workspace_id,
    owner_user_id: policy.owner_user_id,
    scope: "user_data",
  });
  expect(["queued", "running", "succeeded"]).toContain(admitted.status);

  const exportPath = `${exportRoot}/${admitted.id}`;
  const manifestPath = `${exportPath}/manifest`;
  const bundlePath = `${exportPath}/bundle`;
  await expect(page.locator(".lifecycle-status")).toHaveText("导出：已完成", {
    timeout: 90_000,
  });
  await expect(page.locator(".lifecycle-receipt")).toContainText("清单已校验");

  const pollResponses = responsesFor(observer, "GET", exportPath);
  if (!terminalExportStatuses.has(admitted.status)) {
    expect(pollResponses.length, "the rendered workflow must poll its admitted export").toBeGreaterThan(0);
  }
  for (const response of pollResponses) {
    expect(response.status()).toBe(200);
    const polled = dataExportSchema.parse(await response.json());
    expect(polled.id).toBe(admitted.id);
  }

  const manifestResponse = singleResponse(observer, "GET", manifestPath);
  const bundleResponse = singleResponse(observer, "GET", bundlePath);
  expect(manifestResponse.status()).toBe(200);
  expect(bundleResponse.status()).toBe(200);
  const manifest = dataExportManifestSchema.parse(await manifestResponse.json());
  const bundle = dataExportBundleSchema.parse(await bundleResponse.json());
  expect(manifest).toMatchObject({
    export_id: admitted.id,
    status: "succeeded",
  });
  expect(bundle).toMatchObject({
    export_id: admitted.id,
    status: "succeeded",
    manifest_version: manifest.manifest_version,
    manifest_hash: manifest.manifest_hash,
  });
  expect(manifest.manifest).not.toBeNull();
  expect(bundle.bundle).not.toBeNull();
  expect(manifest.manifest_hash).toBe(sha256CanonicalJson(manifest.manifest));
  expect(manifest.manifest?.bundle_sha256).toBe(sha256CanonicalJson(bundle.bundle));
  expect(collectObjectKeys(bundle.bundle)).not.toEqual(expect.arrayContaining([
    "credential",
    "credentials",
    "request_payload",
    "response_payload",
    "raw_model_response",
    "raw_prompt",
    "raw_response",
    "secret",
  ]));

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载数据包", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("crypto-alert-data-export.json");
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const downloadedBundle = JSON.parse(await fs.readFile(downloadPath!, "utf8")) as unknown;
  expect(downloadedBundle).toEqual(bundle.bundle);
  await captureCheckpoint(page, observer, testInfo, "export-succeeded");

  const reloadPolicyResponse = waitForProductResponse(page, "GET", policyPath);
  await page.reload();
  const reloadedPolicyResponse = await reloadPolicyResponse;
  expect(reloadedPolicyResponse.status()).toBe(200);
  expect(dataLifecyclePolicySchema.parse(await reloadedPolicyResponse.json())).toMatchObject({
    tenant_id: policy.tenant_id,
    workspace_id: policy.workspace_id,
    owner_user_id: policy.owner_user_id,
  });
  await expect(page.getByRole("heading", { name: "数据与隐私", exact: true })).toBeVisible();

  const durableResponse = await page.request.get(exportPath, {
    headers: { accept: "application/json" },
    failOnStatusCode: false,
  });
  expect(durableResponse.status()).toBe(200);
  expect(dataExportSchema.parse(await durableResponse.json()).status).toBe("succeeded");

  await expect.soft(
    page.locator(".lifecycle-status"),
    "refresh must rejoin and render the durable export job",
  ).toHaveText("导出：已完成");
  await expect.soft(
    page.locator(".lifecycle-receipt"),
    "refresh must restore the verified manifest and bundle download",
  ).toContainText("清单已校验");
  await captureCheckpoint(page, observer, testInfo, "export-rejoined");

  assertExpectedWrites(observer, [{ method: "POST", pathname: exportRoot }]);
  assertRuntimeClean(observer, "completed export lifecycle");
});

test("real isolated deletion is blocked by legal hold and stops at pending_external", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  assertSupportedViewport(page, testInfo);
  const observer = observeRuntime(page);
  let originalPolicy: DataLifecyclePolicy | null = null;
  let policyChanged = false;

  try {
    const initialPolicyResponse = waitForProductResponse(page, "GET", policyPath);
    await page.goto(settingsPath);
    const policyResponse = await initialPolicyResponse;
    expect(policyResponse.status()).toBe(200);
    originalPolicy = dataLifecyclePolicySchema.parse(await policyResponse.json());

    // This assertion runs before any policy or deletion write. Missing or
    // mismatched isolation proof therefore fails without touching shared data.
    assertIsolatedDeletionEnvironment(originalPolicy);
    await expect(page.getByRole("heading", { name: "删除我的数据", exact: true })).toBeVisible();

    const holdReason = `Playwright isolated deletion gate ${testInfo.project.name} ${Date.now().toString(36)}`;
    const switchControl = page.getByRole("switch");
    if (!(await switchControl.isChecked())) await switchControl.check();
    await page.getByLabel("保留原因", { exact: true }).fill(holdReason);

    const enableHoldResponsePromise = waitForProductResponse(page, "PUT", policyPath);
    await page.getByRole("button", { name: "保存策略", exact: true }).click();
    const enableHoldResponse = await enableHoldResponsePromise;
    expect(enableHoldResponse.status()).toBe(200);
    const heldPolicy = dataLifecyclePolicySchema.parse(await enableHoldResponse.json());
    expect(heldPolicy).toMatchObject({
      legal_hold_active: true,
      legal_hold_reason: holdReason,
    });
    policyChanged = true;

    const confirmationInput = page.getByLabel("输入 DELETE MY DATA 以确认", { exact: true });
    const deletionButton = page.getByRole("button", { name: "提交删除请求", exact: true });
    await expect(confirmationInput).toBeDisabled();
    await expect(deletionButton).toBeDisabled();
    expect(responsesFor(observer, "POST", deletionRoot)).toEqual([]);

    const blockedResponse = await page.request.post(deletionRoot, {
      data: { scope: "user_data", confirmation: "DELETE MY DATA" },
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": `lifecycle-held-${crypto.randomUUID()}`,
      },
      failOnStatusCode: false,
    });
    expect(blockedResponse.status()).toBe(202);
    const blocked = dataDeletionSchema.parse(await blockedResponse.json());
    expect(blocked).toMatchObject({
      tenant_id: originalPolicy.tenant_id,
      workspace_id: originalPolicy.workspace_id,
      owner_user_id: originalPolicy.owner_user_id,
      status: "blocked_legal_hold",
      attempt: 0,
      legal_hold_active: true,
      legal_hold_reason: holdReason,
    });
    expect(Object.values(blocked.system_status).every((state) => state === "blocked_legal_hold")).toBe(true);
    await captureCheckpoint(page, observer, testInfo, "legal-hold-blocked");

    await switchControl.uncheck();
    const disableHoldResponsePromise = waitForProductResponse(page, "PUT", policyPath);
    await page.getByRole("button", { name: "保存策略", exact: true }).click();
    const disableHoldResponse = await disableHoldResponsePromise;
    expect(disableHoldResponse.status()).toBe(200);
    expect(dataLifecyclePolicySchema.parse(await disableHoldResponse.json())).toMatchObject({
      legal_hold_active: false,
      legal_hold_reason: null,
    });

    await confirmationInput.fill("DELETE MY DATA");
    await expect(deletionButton).toBeEnabled();
    const deletionAdmissionPromise = waitForProductResponse(page, "POST", deletionRoot);
    await deletionButton.click();
    const deletionAdmissionResponse = await deletionAdmissionPromise;
    expect(deletionAdmissionResponse.status()).toBe(202);
    expectIdempotencyKey(deletionAdmissionResponse.request());
    expect(deletionAdmissionResponse.request().postDataJSON()).toEqual({
      scope: "user_data",
      confirmation: "DELETE MY DATA",
    });
    const admitted = dataDeletionSchema.parse(await deletionAdmissionResponse.json());
    expect(admitted).toMatchObject({
      tenant_id: originalPolicy.tenant_id,
      workspace_id: originalPolicy.workspace_id,
      owner_user_id: originalPolicy.owner_user_id,
      legal_hold_active: false,
    });
    expect(["queued", "running", "pending_external"]).toContain(admitted.status);

    await expect(page.getByText("删除任务：等待外部回执", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByText(
      "Product 数据已进入删除流程，外部系统仍等待可验证的删除回执。",
      { exact: true },
    )).toBeVisible();

    const deletionPath = `${deletionRoot}/${admitted.id}`;
    const deletionPollResponses = responsesFor(observer, "GET", deletionPath);
    if (!["pending_external", "succeeded", "blocked_legal_hold", "failed"].includes(admitted.status)) {
      expect(
        deletionPollResponses.length,
        "the rendered workflow must poll its admitted deletion",
      ).toBeGreaterThan(0);
    }
    for (const response of deletionPollResponses) {
      expect(response.status()).toBe(200);
      expect(dataDeletionSchema.parse(await response.json()).id).toBe(admitted.id);
    }
    const finalResponse = await page.request.get(deletionPath, {
      headers: { accept: "application/json" },
      failOnStatusCode: false,
    });
    expect(finalResponse.status()).toBe(200);
    const deletion = dataDeletionSchema.parse(await finalResponse.json());
    expect(deletion.status).toBe("pending_external");
    expect(deletion.system_status.product_db).toBe("succeeded");
    expect(Object.values(deletion.system_status)).toContain("pending_external");
    expect(Object.values(deletion.external_deletion_reference).every((receipt) => receipt === null)).toBe(true);
    await expect(page.locator(".lifecycle-system-list [data-state='succeeded']").first()).toBeVisible();
    await expect(page.locator(".lifecycle-system-list [data-state='pending_external']").first()).toBeVisible();
    await captureCheckpoint(page, observer, testInfo, "deletion-pending-external");

    assertExpectedWrites(observer, [
      { method: "PUT", pathname: policyPath },
      { method: "PUT", pathname: policyPath },
      { method: "POST", pathname: deletionRoot },
    ]);
    assertRuntimeClean(observer, "completed isolated deletion lifecycle");
  } finally {
    if (policyChanged && originalPolicy !== null) {
      await restoreLegalHold(page, originalPolicy, testInfo);
    }
  }
});

function assertSupportedViewport(page: Page, testInfo: TestInfo) {
  if (testInfo.project.name.endsWith("desktop")) {
    expect(page.viewportSize()).toEqual({ width: 1440, height: 1000 });
    expect(Boolean(testInfo.project.use.isMobile)).toBe(false);
    return;
  }
  if (testInfo.project.name.endsWith("pixel-7")) {
    expect(page.viewportSize()).toEqual({ width: 412, height: 915 });
    expect(Boolean(testInfo.project.use.isMobile)).toBe(true);
    return;
  }
  throw new Error(`real data lifecycle E2E does not support project ${testInfo.project.name}`);
}

function assertIsolatedDeletionEnvironment(policy: DataLifecyclePolicy) {
  const required = [
    "DATA_LIFECYCLE_E2E_ISOLATED_DATABASE",
    "DATA_LIFECYCLE_E2E_ISOLATION_CONFIRMATION",
    "DATA_LIFECYCLE_E2E_EXPECTED_TENANT_ID",
    "DATA_LIFECYCLE_E2E_EXPECTED_WORKSPACE_ID",
    "DATA_LIFECYCLE_E2E_EXPECTED_OWNER_USER_ID",
  ] as const;
  const missing = required.filter((name) => !process.env[name]?.trim());
  if (missing.length > 0) {
    throw new Error(
      `Refusing deletion: the isolated lifecycle environment is missing ${missing.join(", ")}.`,
    );
  }
  if (
    process.env.DATA_LIFECYCLE_E2E_ISOLATED_DATABASE !== "1"
    || process.env.DATA_LIFECYCLE_E2E_ISOLATION_CONFIRMATION !== isolationConfirmation
  ) {
    throw new Error("Refusing deletion: explicit isolated database confirmation is invalid.");
  }

  const expectedIdentity = {
    tenant_id: process.env.DATA_LIFECYCLE_E2E_EXPECTED_TENANT_ID!,
    workspace_id: process.env.DATA_LIFECYCLE_E2E_EXPECTED_WORKSPACE_ID!,
    owner_user_id: process.env.DATA_LIFECYCLE_E2E_EXPECTED_OWNER_USER_ID!,
  };
  if (!Object.values(expectedIdentity).every((value) => uuidPattern.test(value))) {
    throw new Error("Refusing deletion: isolated actor identity values must be UUIDs.");
  }
  if (
    policy.tenant_id !== expectedIdentity.tenant_id
    || policy.workspace_id !== expectedIdentity.workspace_id
    || policy.owner_user_id !== expectedIdentity.owner_user_id
  ) {
    throw new Error("Refusing deletion: the rendered Product actor does not match the isolated actor proof.");
  }
}

async function assertPolicyRendered(page: Page, policy: DataLifecyclePolicy) {
  const facts = page.locator("dl.lifecycle-facts");
  const expectedFacts = [
    ["任务、运行、决策与用量", `${policy.product_retention_days}天`],
    ["报告与证据", `${policy.artifact_retention_days}天`],
    ["完成后的技术检查点", `${policy.completed_checkpoint_retention_days}天`],
    ["技术投影", `${policy.technical_projection_retention_days}天`],
    ["应用日志", `${policy.log_retention_days}天`],
    ["在线备份轮换", `${policy.backup_retention_days}天`],
    ["原始 Prompt", policy.retain_raw_prompt ? "已启用" : "未保存"],
    ["原始 Response", policy.retain_raw_response ? "已启用" : "未保存"],
  ] as const;
  for (const [label, value] of expectedFacts) {
    const row = facts.locator("div").filter({ has: page.getByText(label, { exact: true }) });
    await expect(row).toContainText(value);
  }
  expect(policy.retain_raw_prompt, "raw Prompt retention must remain disabled by default").toBe(false);
  expect(policy.retain_raw_response, "raw Response retention must remain disabled by default").toBe(false);
}

function observeRuntime(page: Page): RuntimeObserver {
  const observer: RuntimeObserver = {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    serverErrors: [],
    productResponses: [],
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
    if (isSameOriginProductRequest(response.url())) observer.productResponses.push(response);
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

function responsesFor(observer: RuntimeObserver, method: string, pathname: string): Response[] {
  return observer.productResponses.filter((response) => {
    return response.request().method() === method
      && safePathname(response.url()) === pathname;
  });
}

function singleResponse(observer: RuntimeObserver, method: string, pathname: string): Response {
  const responses = responsesFor(observer, method, pathname);
  expect(responses, `${method} ${pathname} response count`).toHaveLength(1);
  return responses[0]!;
}

function expectIdempotencyKey(request: Request) {
  const key = request.headers()["idempotency-key"] ?? "";
  expect(key).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/);
}

function assertExpectedWrites(
  observer: RuntimeObserver,
  expected: Array<{ method: string; pathname: string }>,
) {
  const writes = observer.writes.map((request) => ({
    method: request.method(),
    pathname: safePathname(request.url()),
  }));
  expect(writes).toEqual(expected);
}

async function restoreLegalHold(page: Page, policy: DataLifecyclePolicy, testInfo: TestInfo) {
  try {
    const response = await page.request.put(policyPath, {
      data: {
        legal_hold_active: policy.legal_hold_active,
        legal_hold_reason: policy.legal_hold_reason,
      },
      headers: { accept: "application/json", "content-type": "application/json" },
      failOnStatusCode: false,
    });
    if (response.status() === 200) {
      const restored = dataLifecyclePolicySchema.parse(await response.json());
      if (
        restored.legal_hold_active === policy.legal_hold_active
        && restored.legal_hold_reason === policy.legal_hold_reason
      ) return;
    }
    await testInfo.attach("legal-hold-restore-failure", {
      body: `legal-hold restore returned status ${response.status()}`,
      contentType: "text/plain",
    });
  } catch (reason) {
    await testInfo.attach("legal-hold-restore-failure", {
      body: redactDiagnostic(reason instanceof Error ? reason.message : "unknown restore failure"),
      contentType: "text/plain",
    });
  }
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
        || /"(?:export_id|owner_user_id|tenant_id|workspace_id|system_status|manifest_hash)"\s*:/.test(visibleText),
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
  await testInfo.attach(`real-data-lifecycle-${phase}-${testInfo.project.name}`, {
    body: screenshot,
    contentType: "image/png",
  });
  await testInfo.attach(`real-data-lifecycle-${phase}-quality`, {
    body: Buffer.from(JSON.stringify({
      ...audit,
      consoleErrors: observer.consoleErrors,
      pageErrors: observer.pageErrors,
      failedRequests: observer.failedRequests,
      serverErrors: observer.serverErrors,
    }, null, 2)),
    contentType: "application/json",
  });

  expect(screenshot.byteLength, `${phase} screenshot must be non-empty`).toBeGreaterThan(10_000);
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

function collectObjectKeys(value: unknown, keys = new Set<string>()): string[] {
  if (Array.isArray(value)) {
    value.forEach((item) => collectObjectKeys(item, keys));
  } else if (value !== null && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      keys.add(key.toLowerCase());
      collectObjectKeys(item, keys);
    }
  }
  return [...keys];
}

function sha256CanonicalJson(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.entries(value)
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
    .join(",")}}`;
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
