import { expect, test } from "@playwright/test";
import type { APIRequestContext, TestInfo } from "@playwright/test";
import crypto from "node:crypto";
import { promises as dns } from "node:dns";
import fs from "node:fs/promises";
import { isIP } from "node:net";
import {
  attachRuntimeCollectors,
  expectBusinessPageNotJson,
  expectPageHealthyAtScrollPoints
} from "./audit-helpers";

const EXPLICIT_API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL;
const EXPLICIT_FRONTEND_BASE_URL = process.env.PLAYWRIGHT_FRONTEND_BASE_URL;
const API_BASE_URL = EXPLICIT_API_BASE_URL ?? "http://127.0.0.1:8010";
const EXPECT_HOSTED_PROD_ACTIONABLE = process.env.PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE === "true";
const REUSE_EXISTING_STACK = process.env.PLAYWRIGHT_REUSE_EXISTING_STACK === "true";
const RAW_OR_SECRET_TEXT =
  /request_json|response_json|choices|chat\.completion|Bearer|api[_-]?key|secret|BARK_DEVICE_KEY|device_key|trace_id|parsed_plan|agent_audit_view/i;
const NON_PROD_MODEL_PROOF_TEXT =
  /本地演练|本地样本|模型链路演练|本地模拟|模拟模型|未调用外部模型|摘要暂不可用|mock|fixture/i;
const GENERIC_MODEL_RETURN_SUMMARY = "模型已返回结构化提醒。";

type JsonObject = Record<string, unknown>;

function asRecord(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

async function apiData(request: APIRequestContext, path: string): Promise<JsonObject> {
  const response = await request.get(`${API_BASE_URL}${path}`);
  expect(response.ok(), `${path} should return HTTP 2xx`).toBeTruthy();
  const body = await response.json();
  expect(body?.ok, `${path} should return ok=true`).toBe(true);
  return asRecord(body?.data);
}

function hostedProdActionableConfigIssues(config: JsonObject): string[] {
  const trading = asRecord(config.trading);
  const decision = asRecord(config.decision);
  const marketData = asRecord(config.market_data);
  const notification = asRecord(config.notification);
  const macroEvent = asRecord(config.macro_event);
  const workflow = asRecord(config.workflow);
  const readiness = asRecord(config.readiness);
  const prodActionable = asRecord(readiness.prod_actionable);
  const marketReadiness = asRecord(readiness.market_data);
  const issues: string[] = [];

  if (trading.manual_execution_required !== true) issues.push("trading.manual_execution_required must be true");
  if (trading.auto_order_enabled !== false) issues.push("trading.auto_order_enabled must be false");
  if (decision.engine !== "openai_compatible") issues.push("decision.engine must be openai_compatible");
  if (decision.final_input_mode !== "legacy_prompt") issues.push("decision.final_input_mode must be legacy_prompt");
  if (decision.candidate_sidecar_mode !== "disabled") issues.push("decision.candidate_sidecar_mode must be disabled");
  if (marketData.provider !== "okx_public") issues.push("market_data.provider must be okx_public");
  const okxBaseUrl = asString(marketData.okx_base_url);
  if (okxBaseUrl && okxBaseUrl !== "https://www.okx.com") {
    issues.push("market_data.okx_base_url must be unset or https://www.okx.com");
  }
  if (marketReadiness.status === "unsafe") {
    issues.push("readiness.market_data.status must not be unsafe");
  }
  if (notification.enabled !== true) issues.push("notification.enabled must be true");
  if (macroEvent.provider !== "no_active_event") issues.push("macro_event.provider must be no_active_event");
  if (workflow.execution_mode !== "legacy_baseline") issues.push("workflow.execution_mode must be legacy_baseline");
  if (prodActionable.status !== "ready" || prodActionable.prod_actionable_ready !== true) {
    issues.push("readiness.prod_actionable must be ready");
  }
  if (prodActionable.production_main_path_ready !== true) {
    issues.push("readiness.prod_actionable.production_main_path_ready must be true");
  }
  if (asArray(prodActionable.main_path_blockers).length > 0) {
    issues.push("readiness.prod_actionable.main_path_blockers must be empty");
  }

  return issues;
}

function hasExchangeNativeFreshEvidence(detail: JsonObject): boolean {
  const planRun = asRecord(detail.plan_run);
  const audit = asRecord(planRun.agent_audit_view);
  const sources = asArray(audit.evidence_sources).map(asRecord);
  const freshness = asArray(audit.source_freshness).map(asRecord);
  return (
    sources.some(
      (source) =>
        source.source_type === "exchange_native" &&
        source.freshness_status === "fresh" &&
        source.can_satisfy_execution_fact === true
    ) ||
    freshness.some(
      (row) =>
        row.source_type === "exchange_native" &&
        row.freshness_status === "fresh" &&
        Number(row.can_satisfy_execution_fact_count ?? 0) > 0
    )
  );
}

function assertProdActionableRunDetail(detail: JsonObject, options: { runStartedAt: Date }) {
  const trace = asRecord(detail.trace);
  const planRun = asRecord(detail.plan_run);
  const parsedPlan = asRecord(planRun.parsed_plan);
  const verdict = asRecord(planRun.verdict);
  const businessSummary = asRecord(planRun.business_summary);
  const notification = asRecord(businessSummary.notification);
  const audit = asRecord(planRun.agent_audit_view);
  const lineage = asRecord(audit.input_lineage);
  const interactions = asArray(detail.llm_interactions).map(asRecord);
  const notificationHistory = asArray(detail.notification_history).map(asRecord);

  expect(trace.allowed, "trace.allowed").toBe(true);
  expect(verdict.allowed, "verdict.allowed").toBe(true);
  expect(parsedPlan.manual_execution_required, "parsed_plan.manual_execution_required").toBe(true);
  expect(lineage.production_final_input_mode, "production final input mode").toBe("legacy_prompt");
  expect(
    interactions.some((item) => item.component === "decision.final" && item.provider === "openai_compatible"),
    "run detail must include decision.final OpenAI-compatible LLM evidence"
  ).toBe(true);
  expect(
    interactions.some(
      (item) =>
        item.component === "decision.final" &&
        item.provider === "openai_compatible" &&
        item.status === "ok" &&
        !isNonProdModelName(asString(item.model))
    ),
    "run detail must include successful decision.final real non-mock model evidence"
  ).toBe(true);
  expect(hasExchangeNativeFreshEvidence(detail), "run detail must include exchange-native fresh execution evidence").toBe(true);
  expect(notification.status, "business summary notification status").toBe("sent");
  assertStrictBarkSentNotification(notificationHistory, options.runStartedAt);
}

function assertRealGenerationSummary(detail: JsonObject): JsonObject {
  const planRun = asRecord(detail.plan_run);
  const businessSummary = asRecord(planRun.business_summary);
  const generationSummary = asRecord(businessSummary.generation_summary);
  const providerLabel = asString(generationSummary.provider_label);
  const model = asString(generationSummary.model);
  const modeLabel = asString(generationSummary.mode_label);
  const statusLabel = asString(generationSummary.status_label);
  const responseSummary = asString(generationSummary.response_summary);

  expect(providerLabel, "business_summary.generation_summary.provider_label").not.toEqual("");
  expect(model, "business_summary.generation_summary.model").not.toEqual("");
  expect(isNonProdModelName(model), "prod-actionable generation summary requires a real non-mock model").toBe(false);
  expect(modeLabel, "business_summary.generation_summary.mode_label").toContain("真实模型链路");
  expect(statusLabel, "business_summary.generation_summary.status_label").toContain("模型已返回");
  expect(responseSummary, "business_summary.generation_summary.response_summary").not.toEqual("");
  expect(responseSummary, "prod-actionable generation summary must include a concrete model excerpt").not.toEqual(
    GENERIC_MODEL_RETURN_SUMMARY
  );
  expect(
    `${modeLabel}\n${statusLabel}\n${responseSummary}`,
    "prod-actionable generation summary must not describe fixture/mock/fallback output"
  ).not.toMatch(NON_PROD_MODEL_PROOF_TEXT);

  return generationSummary;
}

function assertStrictBarkSentNotification(notificationHistory: JsonObject[], runStartedAt: Date) {
  expect(
    Boolean(strictBarkSentNotificationEvidence(notificationHistory, runStartedAt)),
    "run detail must include same-run Bark sent evidence with HTTP 2xx status_code and timestamp not earlier than runStartedAt"
  ).toBe(true);
}

function strictBarkSentNotificationEvidence(notificationHistory: JsonObject[], runStartedAt: Date): JsonObject | null {
  for (const item of notificationHistory) {
    const timestamp = parseIsoDate(asString(item.sent_at) || asString(item.created_at));
    const statusCode = item.status_code;
    if (
      item.channel === "bark" &&
      item.status === "sent" &&
      item.ok === true &&
      typeof statusCode === "number" &&
      Number.isInteger(statusCode) &&
      statusCode >= 200 &&
      statusCode < 300 &&
      timestamp !== null &&
      timestamp.getTime() >= runStartedAt.getTime()
    ) {
      return {
        channel: item.channel,
        status: item.status,
        ok: item.ok,
        status_code: statusCode,
        created_at: asString(item.created_at),
        sent_at: asString(item.sent_at)
      };
    }
  }
  return null;
}

function parseIsoDate(value: string): Date | null {
  if (!value) return null;
  if (!/(?:z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  return new Date(timestamp);
}

function isNonProdModelName(model: string) {
  const normalized = model.trim().toLowerCase();
  if (!normalized) return true;
  return ["mock", "fixture", "fake", "stub", "test", "local"].some((token) => {
    if (normalized.startsWith(token)) return true;
    return new RegExp(`(^|[^a-z0-9])${token}([^a-z0-9]|$)`).test(normalized);
  });
}

async function assertHostedProdActionableGateEnvironment() {
  if (EXPECT_HOSTED_PROD_ACTIONABLE) {
    expect(
      REUSE_EXISTING_STACK,
      "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_REUSE_EXISTING_STACK=true"
    ).toBe(true);
    expect(
      Boolean(EXPLICIT_FRONTEND_BASE_URL),
      "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL"
    ).toBe(true);
    expect(
      Boolean(EXPLICIT_API_BASE_URL),
      "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_API_BASE_URL"
    ).toBe(true);
    await assertResolvablePublicHttpsBaseUrl(
      EXPLICIT_FRONTEND_BASE_URL,
      "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL to be a public HTTPS URL"
    );
    await assertResolvablePublicHttpsBaseUrl(
      EXPLICIT_API_BASE_URL,
      "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_API_BASE_URL to be a public HTTPS URL"
    );
  }
}

async function assertResolvablePublicHttpsBaseUrl(value: string | undefined, message: string) {
  const parsed = assertPublicHttpsBaseUrl(value, message);
  let addresses: Array<{ address: string; family: number }>;
  try {
    addresses = await dns.lookup(parsed.hostname, { all: true });
  } catch (error) {
    throw new Error(`${message}; DNS lookup failed for ${parsed.hostname}: ${String(error)}`);
  }
  if (addresses.length === 0) {
    throw new Error(`${message}; DNS lookup returned no addresses for ${parsed.hostname}`);
  }
  const privateAddresses = addresses.filter((item) => isLocalOrPrivateAddress(item.address));
  if (privateAddresses.length > 0) {
    throw new Error(
      `${message}; ${parsed.hostname} resolves to a local/private/reserved address: ${privateAddresses.map((item) => item.address).join(", ")}`
    );
  }
}

function assertPublicHttpsBaseUrl(value: string | undefined, message: string): URL {
  expect(Boolean(value), message).toBe(true);
  let parsed: URL;
  try {
    parsed = new URL(value ?? "");
  } catch {
    throw new Error(message);
  }
  expect(parsed.protocol, message).toBe("https:");
  expect(isLocalOrPrivateHostname(parsed.hostname), message).toBe(false);
  return parsed;
}

function isLocalOrPrivateHostname(hostname: string) {
  const normalized = hostname.trim().toLowerCase().replace(/^\[/, "").replace(/\]$/, "").replace(/\.$/, "");
  if (!normalized || normalized === "localhost" || normalized.endsWith(".localhost")) {
    return true;
  }
  if (normalized === "0.0.0.0" || normalized === "::1" || normalized === "0:0:0:0:0:0:0:1") {
    return true;
  }
  const ipv4 = normalized.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!ipv4) {
    return false;
  }
  const octets = ipv4.slice(1).map((part) => Number(part));
  if (octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return true;
  }
  const [first, second] = octets;
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}

function isLocalOrPrivateAddress(address: string) {
  const normalized = address.trim().toLowerCase().replace(/^\[/, "").replace(/\]$/, "");
  if (!normalized) return true;
  if (normalized.startsWith("::ffff:")) {
    return isLocalOrPrivateIpv4(normalized.slice("::ffff:".length));
  }
  if (isIP(normalized) === 4) {
    return isLocalOrPrivateIpv4(normalized);
  }
  if (isIP(normalized) === 6) {
    return isLocalOrPrivateIpv6(normalized);
  }
  return true;
}

function isLocalOrPrivateIpv4(address: string) {
  const match = address.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!match) return true;
  const [first, second, third, fourth] = match.slice(1).map((part) => Number(part));
  if ([first, second, third, fourth].some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return true;
  }
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    first >= 224 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 0 && third === 0) ||
    (first === 192 && second === 0 && third === 2) ||
    (first === 192 && second === 168) ||
    (first === 198 && second >= 18 && second <= 19) ||
    (first === 198 && second === 51 && third === 100) ||
    (first === 203 && second === 0 && third === 113)
  );
}

function isLocalOrPrivateIpv6(address: string) {
  const normalized = address.toLowerCase();
  return (
    normalized === "::" ||
    normalized === "::1" ||
    normalized.startsWith("fc") ||
    normalized.startsWith("fd") ||
    normalized.startsWith("fe80:") ||
    normalized.startsWith("ff") ||
    normalized.startsWith("2001:db8:")
  );
}

function stableDigest(value: unknown): string {
  return crypto.createHash("sha256").update(stableJson(value)).digest("hex");
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.entries(value as JsonObject)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entry]) => `${JSON.stringify(key)}:${stableJson(entry)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function writeHostedProdActionableProofManifest(options: {
  config: JsonObject;
  detail: JsonObject;
  focus: string;
  generationSummary: JsonObject;
  runStartedAt: Date;
  screenshotPath: string;
  testInfo: TestInfo;
  traceId: string;
}) {
  const trace = asRecord(options.detail.trace);
  const planRun = asRecord(options.detail.plan_run);
  const parsedPlan = asRecord(planRun.parsed_plan);
  const verdict = asRecord(planRun.verdict);
  const audit = asRecord(planRun.agent_audit_view);
  const lineage = asRecord(audit.input_lineage);
  const interactions = asArray(options.detail.llm_interactions).map(asRecord);
  const notificationHistory = asArray(options.detail.notification_history).map(asRecord);
  const barkEvidence = strictBarkSentNotificationEvidence(notificationHistory, options.runStartedAt);
  const finalInteraction = interactions.find(
    (item) =>
      item.component === "decision.final" &&
      item.provider === "openai_compatible" &&
      item.status === "ok" &&
      !isNonProdModelName(asString(item.model))
  );
  const manifestPath = options.testInfo.outputPath("hosted-prod-actionable-proof-manifest.json");
  const manifest = {
    schema_version: "2026-07-09.hosted-prod-actionable-visual-proof.v1",
    proof_level: "hosted-prod-actionable-visual",
    generated_at: new Date().toISOString(),
    run_started_at: options.runStartedAt.toISOString(),
    trace_id: options.traceId,
    frontend_base_url: EXPLICIT_FRONTEND_BASE_URL,
    api_base_url: API_BASE_URL,
    focus: options.focus,
    config_digest: stableDigest(options.config),
    run_detail_digest: stableDigest(options.detail),
    prod_actionable_visual_proven: true,
    real_outcome_proven: false,
    does_not_prove: "hosted_real_outcome",
    run_detail_summary: {
      trace_allowed: trace.allowed,
      verdict_allowed: verdict.allowed,
      manual_execution_required: parsedPlan.manual_execution_required,
      production_final_input_mode: lineage.production_final_input_mode,
      decision_final_provider: asString(asRecord(finalInteraction).provider),
      decision_final_model: asString(asRecord(finalInteraction).model),
      generation_provider_label: asString(options.generationSummary.provider_label),
      generation_model: asString(options.generationSummary.model),
      exchange_native_fresh_evidence: hasExchangeNativeFreshEvidence(options.detail),
      bark_sent: Boolean(barkEvidence),
      bark_evidence: barkEvidence
    },
    artifacts: {
      screenshot_path: options.screenshotPath,
      manifest_path: manifestPath,
      playwright_output_dir: options.testInfo.outputDir,
      trace_policy: "retain-on-failure",
      video_policy: "retain-on-failure"
    }
  };

  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");
  await options.testInfo.attach("hosted-prod-actionable-proof-manifest", {
    path: manifestPath,
    contentType: "application/json"
  });
  await options.testInfo.attach("hosted-prod-actionable-run-detail-screenshot", {
    path: options.screenshotPath,
    contentType: "image/png"
  });
}

test.describe("hosted prod-actionable visual gate", () => {
  test("default stack cannot be mistaken for hosted prod-actionable visual proof", async ({ request }) => {
    await assertHostedProdActionableGateEnvironment();
    const config = await apiData(request, "/api/system/config");
    const issues = hostedProdActionableConfigIssues(config);

    if (EXPECT_HOSTED_PROD_ACTIONABLE) {
      expect(issues, "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires production-ready hosted config").toEqual([]);
    } else {
      expect(
        issues.length,
        "default Playwright runs must not look like hosted prod-actionable proof; set PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true only when reusing a production-ready hosted stack"
      ).toBeGreaterThan(0);
    }
  });

  test("renders the same hosted prod-actionable trace without raw JSON or visual defects", async ({ page, request }, testInfo) => {
    test.skip(
      !EXPECT_HOSTED_PROD_ACTIONABLE,
      "requires PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true, PLAYWRIGHT_REUSE_EXISTING_STACK=true, and a production-ready hosted API/frontend"
    );
    await assertHostedProdActionableGateEnvironment();

    const config = await apiData(request, "/api/system/config");
    expect(hostedProdActionableConfigIssues(config), "production config preflight").toEqual([]);

    const focus = `Playwright hosted prod-actionable visual gate ${Date.now()}: verify model review, evidence, notification, and layout.`;
    const runStartedAt = new Date();
    const runResponse = await request.post(`${API_BASE_URL}/api/runs/manual`, {
      data: {
        symbol: "ETH-USDT-SWAP",
        horizon: "6h",
        query: focus
      }
    });
    expect(runResponse.ok(), "manual run should return HTTP 2xx").toBeTruthy();
    const runBody = await runResponse.json();
    expect(runBody?.ok, "manual run envelope").toBe(true);
    const traceId = String(runBody?.data?.trace_id ?? "");
    expect(traceId, "manual run trace_id").not.toEqual("");

    const detail = await apiData(request, `/api/runs/${encodeURIComponent(traceId)}`);
    assertProdActionableRunDetail(detail, { runStartedAt });
    const generationSummary = assertRealGenerationSummary(detail);

    const runtime = attachRuntimeCollectors(page);
    await page.goto(`/runs/${encodeURIComponent(traceId)}`);
    await expectBusinessPageNotJson(page, "提醒详情");

    const main = page.locator("main");
    const decisionSummary = page.getByLabel("提醒建议摘要");
    await expect(decisionSummary).toBeVisible();
    await expect(decisionSummary.getByLabel("模型返回摘要")).toContainText("模型已返回");
    await expect(decisionSummary.getByLabel("模型审阅")).toContainText("用户关注点");
    await expect(decisionSummary.getByLabel("模型审阅")).toContainText(focus);
    await expect(decisionSummary.getByLabel("模型审阅")).toContainText("模型结论摘录");
    await expect(decisionSummary.getByLabel("模型审阅")).toContainText("引用与证据");
    const modelSummary = decisionSummary.getByLabel("模型返回摘要");
    await expect(modelSummary).toContainText(asString(generationSummary.mode_label));
    await expect(modelSummary).toContainText(asString(generationSummary.provider_label));
    await expect(modelSummary).toContainText(asString(generationSummary.model));
    await expect(modelSummary).toContainText(asString(generationSummary.status_label));
    await expect(modelSummary).toContainText(asString(generationSummary.response_summary));
    await expect(modelSummary).not.toContainText(NON_PROD_MODEL_PROOF_TEXT);
    await expect(decisionSummary.getByLabel("证据摘要").getByRole("listitem").first()).toBeVisible();
    await expect(page.getByLabel("通知历史")).toContainText("Bark 已发送");
    await expect(page.getByLabel("后续复盘")).toBeVisible();
    await expect(page.getByRole("link", { name: /工程诊断|原始数据/ })).toHaveCount(0);
    await expect(main.locator("pre, .json-details")).toHaveCount(0);
    await expect(main).not.toContainText(RAW_OR_SECRET_TEXT);
    await expectPageHealthyAtScrollPoints(page, testInfo, "hosted-prod-actionable-run-detail");
    await runtime.assertClean(testInfo);
    const screenshotPath = testInfo.outputPath("hosted-prod-actionable-run-detail.png");
    await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled" });
    await writeHostedProdActionableProofManifest({
      config,
      detail,
      focus,
      generationSummary,
      runStartedAt,
      screenshotPath,
      testInfo,
      traceId
    });
  });
});
