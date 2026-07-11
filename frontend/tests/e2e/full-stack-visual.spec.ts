import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import type { APIRequestContext, Locator, Page } from "@playwright/test";
import {
  attachRuntimeCollectors,
  expectBusinessPageNotJson,
  expectPageHealthy,
  expectPageHealthyAtScrollPoints
} from "./audit-helpers";

const PRODUCT_ENGINEERING_TEXT =
  /Cockpit|Trace ID|Trace\b|trace_id|Parsed Plan|request_json|response_json|Span 摘要|Spans\b|LLM\b|legacy\b|raw\b|fixture|provider|manual_execution_required|baseline|outcome|legacy_prompt|decision_input|生产最终输入|本次最终输入选择|Run Type|Plan ID|plan_id|Worker Matrix|parsed_plan|verdict|agent_audit_view|facts_gate|production_control_gate|final_input_selection|run_context|llm_interactions|tool_calls|release_eval_gate|request_payload|response_payload|source_types|notification_history|status_code|device_key|bark_device_key|BARK_DEVICE_KEY|present but not execution fact source|active_event_status|not confirming|Invalid if|fresh OKX mark price|\bblocking\b|\bwarn\b|trigger long|trigger short|open long|open short|hold long|hold short|close long|close short|flip long to short|flip short to long|no trade/i;
const PRODUCT_RESULT_ENGINEERING_TEXT =
  /Trace ID|查看 Trace|Trace\b|LLM\b|legacy\b|raw\b|fixture|provider|manual_execution_required|baseline|outcome|legacy_prompt|decision_input|生产最终输入|本次最终输入选择|parsed_plan|verdict|agent_audit_view|facts_gate|production_control_gate|final_input_selection|run_context|llm_interactions|tool_calls|release_eval_gate|request_payload|response_payload|source_types|present but not execution fact source|active_event_status|not confirming|Invalid if|fresh OKX mark price|\bblocking\b|\bwarn\b|\bLONG\b|\bSHORT\b|trigger long|trigger short|open long|open short|hold long|hold short|close long|close short|flip long to short|flip short to long|no trade/i;
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8010";
const LOCAL_STACK_FLAGS = process.env.PLAYWRIGHT_LOCAL_STACK_FLAGS ?? "";
const EXPECT_MOCK_LLM_PRODUCT_RENDERING = process.env.PLAYWRIGHT_EXPECT_MOCK_LLM === "true";
const EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING =
  process.env.PLAYWRIGHT_EXPECT_ACTIONABLE_STAGING === "true" ||
  LOCAL_STACK_FLAGS.split(/\s+/).includes("--with-actionable-staging");
const EXPECT_FIXED_FIXTURE_SCREENSHOTS =
  !EXPECT_MOCK_LLM_PRODUCT_RENDERING && !EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING;
const GENERIC_MODEL_RETURN_SUMMARY = "模型已返回结构化提醒。";

async function expectAbove(first: Locator, second: Locator, label: string) {
  const [firstBox, secondBox] = await Promise.all([first.boundingBox(), second.boundingBox()]);
  expect(firstBox, `${label}: first element should be visible`).not.toBeNull();
  expect(secondBox, `${label}: second element should be visible`).not.toBeNull();
  expect(firstBox!.y, label).toBeLessThan(secondBox!.y);
}

async function expectTopWithinMobileViewport(page: Page, locator: Locator, label: string) {
  const viewport = page.viewportSize();
  if (!viewport || viewport.width > 500) return;
  const box = await locator.boundingBox();
  expect(box, `${label}: element should be visible`).not.toBeNull();
  expect(box!.y, label).toBeLessThan(viewport.height);
}

async function expectP0BusinessDataProjection(container: Locator, expectRawCompletion: boolean) {
  const tradingData = container.getByLabel("交易数据状态");
  await expect(tradingData).toBeVisible();
  await expect(tradingData.getByRole("heading", { name: "交易数据状态" })).toBeVisible();
  await expect(tradingData).toContainText(/执行事实/);
  for (const label of ["来源", "成功", "失败", "缺失"]) {
    await expect(tradingData.locator(".trading-status-counts dt").filter({ hasText: new RegExp(`^${label}$`) })).toHaveCount(1);
  }
  await expect(tradingData.locator(".trading-status-list li").first()).toBeVisible();
  await expect(tradingData).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key|trace_id|production_control_gate/i);

  const modelReview = container.getByLabel("模型审阅");
  await expect(modelReview).toContainText("模型原始返回摘录");
  await expect(modelReview).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key|trace_id|production_control_gate/i);

  const modelSummary = container.getByLabel("模型返回摘要");
  if (expectRawCompletion) {
    const rawCompletion = modelSummary.getByLabel("模型原始返回摘录");
    await expect(rawCompletion).toBeVisible();
    await expect(rawCompletion).toContainText(/模型结论|触发|止损|暂不操作|等待|风险/);
    await expect(rawCompletion).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key|trace_id|production_control_gate/i);
  }
}

async function seedNotificationHistory(request: APIRequestContext, tracePath: string) {
  const traceId = decodeURIComponent(tracePath.split("?")[0].split("/").filter(Boolean).pop() ?? "");
  expect(traceId, "trace id for notification seed").not.toEqual("");
  const response = await request.get(`${API_BASE_URL}/api/runs/${encodeURIComponent(traceId)}`);
  expect(response.ok(), "run detail for notification seed").toBeTruthy();
  const body = await response.json();
  const planId = body?.data?.trace?.final_plan_id ?? body?.data?.plan_run?.plan_id;
  expect(planId, "plan id for notification seed").toBeTruthy();
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "crypto-alert.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import sqlite3
import sys

db_path, plan_id = sys.argv[1], sys.argv[2]
rows = [
    (
        plan_id,
        "2026-07-08T00:00:00+00:00",
        0,
        500,
        "Bark timeout; BARK_DEVICE_KEY=secret; plan_id=leak; status_code=500; notification_history raw; device_key=abc; https://api.day.app/key/title?token=secret",
    ),
    (
        plan_id,
        "2026-07-08T00:01:00+00:00",
        1,
        200,
        None,
    ),
]
with sqlite3.connect(db_path) as conn:
    conn.executemany(
        "INSERT INTO notifications (plan_id, created_at, ok, status_code, error) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
`,
      dbPath,
      String(planId)
    ],
    { stdio: "pipe" }
  );
}

function seedUnsafeDiagnosticLlmPayload(tracePath: string) {
  const traceId = decodeURIComponent(tracePath.split("?")[0].split("/").filter(Boolean).pop() ?? "");
  expect(traceId, "trace id for diagnostic LLM payload seed").not.toEqual("");
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "crypto-alert.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import json
import sqlite3
import sys

db_path, trace_id = sys.argv[1], sys.argv[2]
request_payload = {
    "api_key": "raw-api-secret",
    "authorization": "Bearer raw-bearer-secret",
    "messages": [{"role": "user", "content": "diagnostic payload"}],
    "nested": {"device_key": "raw-device-secret"},
    "url": "https://api.day.app/raw-device/title?token=raw-query-secret",
}
response_payload = {
    "choices": [{"message": {"content": "模型结论：等待人工复核。"}}],
    "secret": "raw-response-secret",
}
with sqlite3.connect(db_path) as conn:
    cursor = conn.execute(
        """
        UPDATE llm_interactions
        SET request_json = ?, response_json = ?
        WHERE id = (
            SELECT id FROM llm_interactions
            WHERE trace_id = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (
            json.dumps(request_payload, ensure_ascii=False),
            json.dumps(response_payload, ensure_ascii=False),
            trace_id,
        ),
    )
    if cursor.rowcount != 1:
        raise SystemExit("expected one LLM interaction row for diagnostic seed")
`,
      dbPath,
      traceId
    ],
    { stdio: "pipe" }
  );
}

async function seedRunResultReview(request: APIRequestContext, tracePath: string) {
  const traceId = decodeURIComponent(tracePath.split("?")[0].split("/").filter(Boolean).pop() ?? "");
  expect(traceId, "trace id for result review seed").not.toEqual("");
  const response = await request.get(`${API_BASE_URL}/api/runs/${encodeURIComponent(traceId)}`);
  expect(response.ok(), "run detail for result review seed").toBeTruthy();
  const body = await response.json();
  const planId = body?.data?.trace?.final_plan_id ?? body?.data?.plan_run?.plan_id;
  const symbol = body?.data?.trace?.symbol ?? "ETH-USDT-SWAP";
  const plan = body?.data?.plan_run?.parsed_plan ?? {};
  expect(planId, "plan id for result review seed").toBeTruthy();
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "eval", "crypto-outcomes.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import json
import sqlite3
import sys

db_path, plan_id, symbol, plan_json = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
plan = json.loads(plan_json)
payload = {
    "decision_ref": f"{plan_id}:legacy_final",
    "evaluation_target": "legacy_final",
    "symbol": symbol,
    "action": plan.get("main_action") or "trigger long",
    "probability": plan.get("probability"),
    "entry_price": plan.get("entry_trigger"),
    "stop_price": plan.get("stop_price"),
    "target_1": plan.get("target_1"),
    "target_2": plan.get("target_2"),
    "window": {
        "name": "6h",
        "symbol": symbol,
        "interval": "1H",
        "source_type": "mocked_outcome",
        "window_start": "2026-07-08T00:00:00+00:00",
        "window_end": "2026-07-08T06:00:00+00:00",
        "collected_at": "2026-07-08T06:01:00+00:00",
        "open_price": 3450.0,
        "high_price": 3568.0,
        "low_price": 3428.0,
        "close_price": 3542.0,
        "matured": True,
        "can_score_execution_outcome": False,
        "unscored_reason": "price_source_not_exchange_native",
    },
    "can_score": False,
    "unscored_reason": "price_source_not_exchange_native",
}
with sqlite3.connect(db_path) as conn:
    conn.execute(
        """
        INSERT OR REPLACE INTO eval_decision_outcomes (
            decision_ref, evaluation_target, symbol, window_name, outcome_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            payload["decision_ref"],
            payload["evaluation_target"],
            symbol,
            payload["window"]["name"],
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
`,
      dbPath,
      String(planId),
      String(symbol),
      JSON.stringify(plan)
    ],
    { stdio: "pipe" }
  );
}

async function seedRunUnknownQualityStatus(request: APIRequestContext, tracePath: string) {
  const traceId = decodeURIComponent(tracePath.split("?")[0].split("/").filter(Boolean).pop() ?? "");
  expect(traceId, "trace id for quality status seed").not.toEqual("");
  const response = await request.get(`${API_BASE_URL}/api/runs/${encodeURIComponent(traceId)}`);
  expect(response.ok(), "run detail for quality status seed").toBeTruthy();
  const body = await response.json();
  const planId = body?.data?.trace?.final_plan_id ?? body?.data?.plan_run?.plan_id;
  expect(planId, "plan id for quality status seed").toBeTruthy();
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "crypto-alert.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import json
import sqlite3
import sys

db_path, plan_id = sys.argv[1], sys.argv[2]
with sqlite3.connect(db_path) as conn:
    row = conn.execute("SELECT payload_json FROM plan_runs WHERE plan_id = ?", (plan_id,)).fetchone()
    if row is None:
        raise SystemExit("missing plan_run")
    payload = json.loads(row[0])
    payload["financial_quality_gate"] = {
        "schema_version": 1,
        "status": "mystery_quality_status",
        "decision_effect": "mystery_decision_effect",
        "structural_release_gate_blocking": False,
        "blocking": False,
        "blocking_reasons": [],
    }
    conn.execute(
        "UPDATE plan_runs SET payload_json = ? WHERE plan_id = ?",
        (json.dumps(payload, ensure_ascii=False, sort_keys=True), plan_id),
    )
`,
      dbPath,
      String(planId)
    ],
    { stdio: "pipe" }
  );
}

function seedEvalQualityGateRun() {
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "eval", "crypto-eval.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import json
import sqlite3
import sys

db_path = sys.argv[1]
metadata = {
    "financial_quality_gate": {
        "schema_version": 1,
        "status": "mystery_quality_status",
        "decision_effect": "mystery_decision_effect",
        "structural_release_gate_blocking": False,
        "blocking": False,
        "blocking_reasons": [],
        "evaluation_targets": ["swarm_candidate_final"],
        "target_gates": [
            {
                "schema_version": 1,
                "status": "not_enough_samples",
                "passed": False,
                "blocking": False,
                "decision_effect": "none",
                "structural_release_gate_blocking": False,
                "evaluation_target": "swarm_candidate_final",
                "minimum_scored_count": 30,
                "observed_scored_count": 2,
                "blocking_reasons": ["financial_quality:not_enough_samples"],
                "brier_event_label": "window_direction_hit",
                "metrics": {
                    "scored_count": 2,
                    "pending_count": 0,
                    "unscored_count": 0,
                    "no_trade_count": 0,
                    "direction_hit_rate": 0.5,
                    "target_hit_rate": None,
                    "invalidation_hit_rate": None,
                    "average_pnl_pct": 0.012,
                    "average_r_multiple": 0.4,
                    "brier_score": 0.24,
                    "unscored_reasons": {},
                },
            },
            {
                "schema_version": 1,
                "status": "baseline_reference",
                "passed": True,
                "blocking": False,
                "decision_effect": "none",
                "structural_release_gate_blocking": False,
                "evaluation_target": "no_trade",
                "minimum_scored_count": 30,
                "observed_scored_count": 2,
                "blocking_reasons": [],
                "brier_event_label": "no_trade_counterfactual",
                "metrics": {
                    "scored_count": 2,
                    "pending_count": 0,
                    "unscored_count": 0,
                    "no_trade_count": 0,
                    "direction_hit_rate": 1.0,
                    "target_hit_rate": None,
                    "invalidation_hit_rate": None,
                    "average_pnl_pct": 0.0,
                    "average_r_multiple": 0.0,
                    "brier_score": 0.0,
                    "unscored_reasons": {},
                },
            },
        ],
    }
}
with sqlite3.connect(db_path) as conn:
    conn.execute(
        """
        INSERT OR REPLACE INTO eval_runs (
            eval_run_id, dataset_name, mode, status, started_at, ended_at,
            case_count, pass_count, fail_count, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "playwright-financial-quality-gate",
            "playwright",
            "judge_only_fixture",
            "passed",
            "2999-01-01T00:00:00+00:00",
            "2999-01-01T00:00:01+00:00",
            2,
            2,
            0,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
`,
      dbPath
    ],
    { stdio: "pipe" }
  );
}

function seedUnknownEvalOutcome() {
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "eval", "crypto-outcomes.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import json
import sqlite3
import sys

db_path = sys.argv[1]
payload = {
    "decision_ref": "quality-unknown-seed",
    "evaluation_target": "mystery_target",
    "symbol": "BTC-USDT-SWAP",
    "action": "trigger long",
    "probability": 0.51,
    "entry_price": 60000.0,
    "stop_price": 59000.0,
    "target_1": 62000.0,
    "target_2": 64000.0,
    "window": {
        "name": "6h",
        "symbol": "BTC-USDT-SWAP",
        "interval": "1H",
        "source_type": "mystery_source",
        "window_start": "2026-07-08T00:00:00+00:00",
        "window_end": "2026-07-08T06:00:00+00:00",
        "collected_at": "2026-07-08T06:01:00+00:00",
        "open_price": 60000.0,
        "high_price": 61000.0,
        "low_price": 59000.0,
        "close_price": 60500.0,
        "matured": True,
        "can_score_execution_outcome": False,
        "unscored_reason": "mystery_unscored_reason",
    },
    "can_score": False,
    "unscored_reason": "mystery_unscored_reason",
}
with sqlite3.connect(db_path) as conn:
    conn.execute(
        """
        INSERT OR REPLACE INTO eval_decision_outcomes (
            decision_ref, evaluation_target, symbol, window_name, outcome_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            payload["decision_ref"],
            payload["evaluation_target"],
            payload["symbol"],
            payload["window"]["name"],
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
`,
      dbPath
    ],
    { stdio: "pipe" }
  );
}

test.describe("full-stack visual and interaction audit", () => {
  test("runs empty state explains local proof level and missing production readiness", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);

    await page.goto("/runs?symbol=NO-SUCH-SYMBOL");

    const emptyState = page.getByLabel("当前记录状态");
    await expect(emptyState.getByRole("heading", { name: "当前没有可审计提醒" })).toBeVisible();
    await expect(emptyState).toContainText("当前只是本地演练或空数据状态，不是生产成功证明。");
    await expect(emptyState.getByText("真实模型", { exact: true })).toBeVisible();
    await expect(emptyState.getByText("真实行情", { exact: true })).toBeVisible();
    await expect(emptyState.getByText("Bark 通知", { exact: true })).toBeVisible();
    await expect(emptyState.getByText("宏观事件状态", { exact: true })).toBeVisible();
    await expect(emptyState.getByRole("link", { name: "查看配置检查" })).toHaveAttribute("href", "/config");
    await expect(emptyState.getByRole("link", { name: "新建提醒" })).toHaveAttribute("href", "/manual-run");
    await expectBusinessPageNotJson(page, "提醒记录");
    await expect(page.locator("main")).not.toContainText(/trace_id|request_json|response_json|OPENAI_API_KEY|BARK_DEVICE_KEY|OKX_API_SECRET/i);
    await expectPageHealthy(page, testInfo, "runs-empty-readiness");
    await runtime.assertClean(testInfo);
  });

  test("manual run async flow, run detail, eval tabs, and config render without visual/DOM defects", async ({ page, request }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);
    const manualFocus = "重点关注 ETH 当前持仓风险、触发价、止损和复核时间。";

    await page.goto("/");
    const main = page.locator("main");
    await expect(page.getByRole("heading", { name: "提醒控制台" })).toBeVisible();
    await expectBusinessPageNotJson(page, "提醒控制台");
    await expect(page.getByRole("link", { name: /新建提醒/ }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /质量复盘/ }).first()).toHaveAttribute("href", "/eval?tab=quality");
    await expect(main).not.toContainText(/诊断视图|baseline|outcome|trace/i);
    await expect(main).not.toContainText(/SHADOW|sqlite|crypto-manual-alert/);
    await expect(page.getByRole("navigation", { name: "评估" }).getByRole("link", { name: "诊断视图" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "评估" }).getByRole("link", { name: "质量复盘" })).toHaveAttribute("href", "/eval?tab=quality");
    await expect(main).not.toContainText(PRODUCT_ENGINEERING_TEXT);
    await expectPageHealthy(page, testInfo, "dashboard");
    if (EXPECT_FIXED_FIXTURE_SCREENSHOTS) {
      await expect(page).toHaveScreenshot("dashboard-fullpage.png", {
        animations: "disabled"
      });
    }

    await page.goto("/manual-run");
    await expect(page.getByRole("heading", { name: "新建提醒" })).toBeVisible();
    await expectBusinessPageNotJson(page, "新建提醒");
    await expect(page.getByRole("heading", { name: "提醒参数" })).toBeVisible();
    await expect(page.getByText("关注点会记录为本次复核备注；当前主计划仍由交易对、周期、持仓和配置驱动，系统不会自动下单。")).toBeVisible();
    await expect(main).not.toContainText("帮助生成更贴近当前仓位的提醒");
    await page.getByLabel("交易对").fill("ETH-USDT-SWAP");
    await page.getByLabel("关注点").fill(manualFocus);
    await expect(main).not.toContainText(/Manual Run|trace_id|Trace\b|最终输入模式|审计备注|LLM\b/i);
    await page.getByRole("button", { name: "生成提醒建议" }).click();
    const resultPanel = page.getByRole("heading", { name: "本次提醒建议", exact: true }).locator("xpath=ancestor::*[self::section or self::article or self::div][1]");
    await expect(resultPanel.getByRole("heading", { name: "本次提醒建议", exact: true })).toBeVisible({ timeout: 30_000 });
    await expectBusinessPageNotJson(page, "本次提醒建议");
    if (EXPECT_MOCK_LLM_PRODUCT_RENDERING) {
      await expect(resultPanel.getByText("模型链路演练", { exact: true }).first()).toBeVisible();
    } else if (EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING) {
      await expect(resultPanel.getByText("可人工复核", { exact: true }).first()).toBeVisible();
      await expect(resultPanel).not.toContainText("本地演练");
    } else {
      await expect(resultPanel.getByText("本地演练", { exact: true }).first()).toBeVisible();
    }
    const resultProofStatus = resultPanel.getByLabel("提醒证据级别");
    await expect(resultProofStatus).toBeVisible();
    await expect(resultProofStatus).toContainText(/证据级别/);
    await expect(resultProofStatus).toContainText(
      EXPECT_MOCK_LLM_PRODUCT_RENDERING
        ? /模型链路演练/
        : EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING
          ? /本地预发人工复核/
          : /本地流程验证/
    );
    await expect(resultProofStatus).toContainText(
      EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING ? /不是生产成功/ : /不是生产成功/
    );
    await expect(resultProofStatus).toContainText(/人工核对后手动执行/);
    const resultModelConclusion = resultPanel.getByLabel("模型结论");
    await expect(resultModelConclusion).toBeVisible();
    await expect(resultModelConclusion.getByRole("heading", { name: "模型结论" })).toBeVisible();
    await expect(resultModelConclusion).toContainText(/模型|建议|提醒|风险|触发|止损|目标|等待|观望/);
    await expect(resultModelConclusion).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key|trace_id|production_control_gate/i);
    await expect(resultModelConclusion).not.toContainText(/模型链路演练|真实模型链路|本地流程验证|本地预发人工复核/);
    const resultPriceGrid = resultPanel.locator(".price-grid").first();
    await expectAbove(resultPanel.locator(".alert-summary"), resultProofStatus, "manual result action should lead proof level");
    await expectAbove(resultModelConclusion, resultProofStatus, "manual result model conclusion should lead proof level");
    await expectAbove(resultPriceGrid, resultProofStatus, "manual result price levels should lead proof level");
    await expectAbove(resultPanel.locator(".alert-summary"), resultPanel.locator(".mode-notice"), "manual result action should lead mode notice");
    await expectAbove(resultModelConclusion, resultPanel.locator(".mode-notice"), "manual result model conclusion should lead mode notice");
    await expectAbove(resultPriceGrid, resultPanel.locator(".mode-notice"), "manual result price levels should lead mode notice");
    await expectTopWithinMobileViewport(page, resultPriceGrid, "manual result price levels should be near the first mobile viewport");
    await expect(resultPanel.getByText("参考价", { exact: true })).toBeVisible();
    await expect(resultPanel.getByText("触发价", { exact: true })).toBeVisible();
    await expect(resultPanel.getByText("止损", { exact: true })).toBeVisible();
    await expect(resultPanel.getByRole("heading", { name: "生成链路" })).toBeVisible();
    const resultModelSummary = resultPanel.getByLabel("模型返回摘要");
    await expect(resultModelSummary).toBeVisible();
    for (const label of ["模型状态", "接口", "模型", "耗时", "Token", "完成状态"]) {
      await expect(resultModelSummary.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(resultModelSummary).toContainText("摘要：");
    await expect(resultModelSummary).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key/i);
    const resultModelReview = resultPanel.getByLabel("模型审阅");
    await expect(resultModelReview).toBeVisible();
    for (const label of ["用户关注点", "模型结论摘录", "引用与证据"]) {
      await expect(resultModelReview.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(resultModelReview).toContainText(manualFocus);
    await expect(resultModelReview).toContainText(/证据来源|证据摘要/);
    await expect(resultModelReview).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key/i);
    const resultEvidenceSummary = resultPanel.getByLabel("证据摘要");
    await expect(resultEvidenceSummary).toBeVisible();
    await expect(resultEvidenceSummary.getByRole("listitem").first()).toBeVisible();
    await expect(resultEvidenceSummary).toContainText(/证据|行情|事件|数据|样本/);
    await expectP0BusinessDataProjection(resultPanel, EXPECT_MOCK_LLM_PRODUCT_RENDERING);
    if (EXPECT_MOCK_LLM_PRODUCT_RENDERING) {
      await expect(resultPanel.getByText(/mock-crypto-plan/).first()).toBeVisible();
      await expect(resultPanel.getByText("模型已返回", { exact: true }).first()).toBeVisible();
      await expect(resultModelSummary).toContainText("模型结论");
      await expect(resultModelSummary).not.toContainText(GENERIC_MODEL_RETURN_SUMMARY);
      await expect(resultPanel.getByText("3,510", { exact: true })).toBeVisible();
      await expect(resultPanel.getByText("3,435", { exact: true })).toBeVisible();
      await expect(resultPanel).not.toContainText(/未调用外部模型|request_json|response_json|choices|chat\.completion/i);
    } else {
      await expect(resultPanel.getByText("使用本地样本计划，未产生真实模型返回。", { exact: true }).first()).toBeVisible();
    }
    await expect(resultPanel.getByRole("heading", { name: "下一步" })).toBeVisible();
    await expect(resultPanel.getByRole("heading", { name: "后续复盘" })).toBeVisible();
    await expect(resultPanel.getByText("结果尚未生成", { exact: true })).toBeVisible();
    await expect(resultPanel.getByText(/观察窗口成熟并完成采集/)).toBeVisible();
    await expect(resultPanel.getByRole("link", { name: "查看详情" })).toBeVisible();
    await expect(resultPanel).not.toContainText(/支持排查编号|诊断信息/);
    await expect(resultPanel).not.toContainText(/outcome|replay|baseline|evaluation_target|swarm_candidate_final|legacy_final|mocked_outcome|exchange-native|OutcomeStore|collect-outcomes|decision_ref|can_score|unscored_reason/i);
    await expect(resultPanel).not.toContainText(PRODUCT_RESULT_ENGINEERING_TEXT);
    await expectPageHealthy(page, testInfo, "manual-run-result");
    const traceHref = await resultPanel.getByRole("link", { name: "查看详情" }).getAttribute("href");
    expect(traceHref, "manual run trace href").toMatch(/^\/runs\/[^?/#]+/);
    const tracePath = traceHref ?? "/runs";

    await page.goto(tracePath);
    await expect(page.getByRole("heading", { name: "提醒详情" })).toBeVisible();
    await expectBusinessPageNotJson(page, "提醒详情");
    await expect(page.getByRole("link", { name: /建议摘要/ })).toHaveAttribute("aria-current", "page");
    const decisionSummary = page.getByLabel("提醒建议摘要");
    await expect(decisionSummary).toBeVisible();
    const detailProofStatus = decisionSummary.getByLabel("提醒证据级别");
    await expect(detailProofStatus).toBeVisible();
    await expect(detailProofStatus).toContainText(/证据级别/);
    await expect(detailProofStatus).toContainText(
      EXPECT_MOCK_LLM_PRODUCT_RENDERING
        ? /模型链路演练/
        : EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING
          ? /本地预发人工复核/
          : /本地流程验证/
    );
    await expect(detailProofStatus).toContainText(/不是生产成功/);
    await expect(detailProofStatus).toContainText(/人工核对后手动执行/);
    const detailModelConclusion = decisionSummary.getByLabel("模型结论");
    await expect(detailModelConclusion).toBeVisible();
    await expect(detailModelConclusion.getByRole("heading", { name: "模型结论" })).toBeVisible();
    await expect(detailModelConclusion).toContainText(/模型|建议|提醒|风险|触发|止损|目标|等待|观望/);
    await expect(detailModelConclusion).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key|trace_id|production_control_gate/i);
    await expect(detailModelConclusion).not.toContainText(/模型链路演练|真实模型链路|本地流程验证|本地预发人工复核/);
    const detailPriceGrid = decisionSummary.locator(".price-grid").first();
    await expectAbove(decisionSummary.locator(".decision-card-header"), detailProofStatus, "detail action should lead proof level");
    await expectAbove(detailModelConclusion, detailProofStatus, "detail model conclusion should lead proof level");
    await expectAbove(detailPriceGrid, detailProofStatus, "detail price levels should lead proof level");
    await expectAbove(decisionSummary.locator(".decision-card-header"), decisionSummary.locator(".mode-notice"), "detail action should lead mode notice");
    await expectAbove(detailModelConclusion, decisionSummary.locator(".mode-notice"), "detail model conclusion should lead mode notice");
    await expectAbove(detailPriceGrid, decisionSummary.locator(".mode-notice"), "detail price levels should lead mode notice");
    await expectTopWithinMobileViewport(page, detailPriceGrid, "detail price levels should be near the first mobile viewport");
    await expect(decisionSummary.getByText("参考价", { exact: true })).toBeVisible();
    await expect(decisionSummary.getByText("触发价", { exact: true })).toBeVisible();
    await expect(decisionSummary.getByText("止损", { exact: true })).toBeVisible();
    await expect(decisionSummary.getByRole("heading", { name: "生成链路" })).toBeVisible();
    const detailModelSummary = decisionSummary.getByLabel("模型返回摘要");
    await expect(detailModelSummary).toBeVisible();
    for (const label of ["模型状态", "接口", "模型", "耗时", "Token", "完成状态"]) {
      await expect(detailModelSummary.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(detailModelSummary).toContainText("摘要：");
    await expect(detailModelSummary).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key/i);
    const detailModelReview = decisionSummary.getByLabel("模型审阅");
    await expect(detailModelReview).toBeVisible();
    for (const label of ["用户关注点", "模型结论摘录", "引用与证据"]) {
      await expect(detailModelReview.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(detailModelReview).toContainText(manualFocus);
    await expect(detailModelReview).toContainText(/证据来源|证据摘要/);
    await expect(detailModelReview).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key/i);
    const detailEvidenceSummary = decisionSummary.getByLabel("证据摘要");
    await expect(detailEvidenceSummary).toBeVisible();
    await expect(detailEvidenceSummary.getByRole("listitem").first()).toBeVisible();
    await expect(detailEvidenceSummary).toContainText(/证据|行情|事件|数据|样本/);
    await expectP0BusinessDataProjection(decisionSummary, EXPECT_MOCK_LLM_PRODUCT_RENDERING);
    if (EXPECT_MOCK_LLM_PRODUCT_RENDERING) {
      await expect(decisionSummary.getByText("模型链路演练", { exact: true }).first()).toBeVisible();
      await expect(decisionSummary.getByText(/mock-crypto-plan/).first()).toBeVisible();
      await expect(decisionSummary.getByText("模型已返回", { exact: true }).first()).toBeVisible();
      await expect(detailModelSummary).toContainText("模型结论");
      await expect(detailModelSummary).not.toContainText(GENERIC_MODEL_RETURN_SUMMARY);
      await expect(decisionSummary.getByText("3,510", { exact: true })).toBeVisible();
      await expect(decisionSummary.getByText("3,435", { exact: true })).toBeVisible();
      await expect(decisionSummary).not.toContainText(/未调用外部模型|request_json|response_json|choices|chat\.completion/i);
    } else if (EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING) {
      await expect(decisionSummary.getByText("可人工复核", { exact: true }).first()).toBeVisible();
      await expect(decisionSummary).not.toContainText("本地演练");
    } else {
      await expect(decisionSummary.getByText("使用本地样本计划，未产生真实模型返回。", { exact: true }).first()).toBeVisible();
    }
    await expect(decisionSummary.getByRole("heading", { name: "为什么" })).toBeVisible();
    await expect(decisionSummary.getByRole("heading", { name: "下一步" })).toBeVisible();
    await expect(decisionSummary.locator("pre")).toHaveCount(0);
    const resultReview = page.getByLabel("后续复盘");
    await expect(resultReview.getByRole("heading", { name: "后续复盘" })).toBeVisible();
    await expect(resultReview.getByText("结果尚未生成", { exact: true })).toBeVisible();
    await expect(resultReview.getByText(/观察窗口成熟并完成采集/)).toBeVisible();
    await expect(resultReview).not.toContainText(/outcome|replay|baseline|evaluation_target|swarm_candidate_final|legacy_final|mocked_outcome|exchange-native|OutcomeStore|collect-outcomes|decision_ref|can_score|unscored_reason/i);

    await seedRunResultReview(request, tracePath);
    await page.goto(tracePath);
    const seededResultReview = page.getByLabel("后续复盘");
    await expect(seededResultReview.getByText("本地展示样本", { exact: true }).first()).toBeVisible();
    await expect(seededResultReview.getByText("本地展示样本，不计入真实金融质量。", { exact: true })).toBeVisible();
    await expect(seededResultReview.getByText("不可评分", { exact: true })).toBeVisible();
    await expect(seededResultReview.getByText("最终建议链路", { exact: true })).toBeVisible();
    await expect(seededResultReview).not.toContainText(/outcome|replay|baseline|evaluation_target|swarm_candidate_final|legacy_final|mocked_outcome|exchange-native|OutcomeStore|collect-outcomes|decision_ref|can_score|unscored_reason/i);
    const notificationHistory = page.getByLabel("通知历史");
    await expect(notificationHistory.getByRole("heading", { name: "通知历史" })).toBeVisible();
    await expect(notificationHistory.getByText("暂无通知记录", { exact: true })).toBeVisible();
    await expect(notificationHistory.getByText("通知未启用", { exact: true })).toBeVisible();
    await expect(notificationHistory.locator("pre")).toHaveCount(0);
    await expect(page.getByRole("link", { name: /工程诊断/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /原始数据/ })).toHaveCount(0);
    await expect(main).not.toContainText(PRODUCT_ENGINEERING_TEXT);
    await expectPageHealthy(page, testInfo, "run-detail-summary");
    if (EXPECT_FIXED_FIXTURE_SCREENSHOTS) {
      await expect(page).toHaveScreenshot("run-detail-summary-fullpage.png", {
        animations: "disabled"
      });
    }

    await seedRunUnknownQualityStatus(request, tracePath);
    await page.goto(tracePath);
    const seededStatusBar = page.getByLabel("复核状态摘要");
    await expect(seededStatusBar.getByText("状态已记录", { exact: true })).toBeVisible();
    await expect(seededStatusBar).not.toContainText(/mystery_quality_status|mystery_decision_effect/);

    await page.goto(tracePath.includes("?") ? `${tracePath}&tab=raw` : `${tracePath}?tab=raw`);
    await expect(page.getByRole("link", { name: /建议摘要/ })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "原始数据" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "评估" }).getByRole("link", { name: "诊断视图" })).toHaveCount(0);
    await expect(main).not.toContainText(/Parsed Plan|request_json|response_json|LLM 交互|Span 摘要|parsed_plan|verdict/i);

    await page.goto("/runs");
    await expect(page.getByRole("heading", { name: "提醒记录" })).toBeVisible();
    await expectBusinessPageNotJson(page, "提醒记录");
    await expect(page.getByRole("columnheader", { name: "提醒时间" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "建议动作" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "复核结果" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "模型结论" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "风险摘要" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "通知" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "后续复盘" })).toBeVisible();
    const runListRow = page.getByRole("row", { name: /ETH-USDT-SWAP/ }).first();
    const runListModelCell = runListRow.locator(".runs-model-cell");
    await expect(runListModelCell).toBeVisible();
    await expect(runListModelCell).toContainText(/模型|建议|提醒|风险|触发|止损|目标|等待|观望/);
    await expect(runListModelCell).not.toContainText(/request_json|response_json|choices|chat\.completion|Bearer|api_key|trace_id|production_control_gate|raw|secret|token/i);
    await expect(runListRow).toContainText("本地展示样本");
    await expect(runListRow).toContainText("结果样本 1 条");
    await expect(runListRow).not.toContainText(/outcome|decision_ref|mocked_outcome|exchange_native|legacy_final|can_score|unscored_reason/i);
    await expect(page.getByText("通知未启用", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "提醒编号" })).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "创建时间" })).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "Trace" })).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "Spans" })).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "LLM" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "列显示" })).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText(/提醒编号|Trace\b|Spans\b|LLM\b|\ballowed\b|\bblocked\b|worker|gate/i);
    await expectPageHealthy(page, testInfo, "runs-business");
    if (EXPECT_FIXED_FIXTURE_SCREENSHOTS) {
      await page.addStyleTag({
        content: ".table-wrap tbody tr:nth-child(n+2) { display: none !important; }"
      });
      await expect(page).toHaveScreenshot("runs-business-fullpage.png", {
        animations: "disabled",
        mask: [page.locator(".table-wrap tbody tr:first-child td").first()]
      });
    }

    await seedNotificationHistory(request, tracePath);
    await page.goto(tracePath);
    const seededNotificationHistory = page.getByLabel("通知历史");
    await expect(seededNotificationHistory).toBeVisible();
    await expect(seededNotificationHistory.locator(".notification-item").first()).toContainText("Bark 已发送");
    await expect(seededNotificationHistory.getByText("发送失败", { exact: true })).toBeVisible();
    await expect(seededNotificationHistory.getByText("服务响应 200", { exact: true })).toBeVisible();
    await expect(seededNotificationHistory.getByText("服务响应 500", { exact: true })).toBeVisible();
    await expect(seededNotificationHistory.getByText("失败原因：Bark 发送超时", { exact: true })).toBeVisible();
    await expect(seededNotificationHistory.locator("pre")).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText(PRODUCT_ENGINEERING_TEXT);
    await expect(seededNotificationHistory).not.toContainText(/secret|BARK_DEVICE_KEY|device_key|plan_id|status_code|notification_history|https:\/\/api\.day\.app|raw/i);
    await expectPageHealthy(page, testInfo, "run-detail-notification-history-seeded");

    await page.goto("/runs?columns=observability");
    await expect(page.getByRole("heading", { name: "提醒记录" })).toBeVisible();
    await expect(page.getByLabel("工程诊断说明")).toContainText("这是工程诊断视图，不是普通提醒记录");
    await expect(page.getByRole("link", { name: /观测列/ })).toHaveClass(/active/);
    await expect(page.getByRole("navigation", { name: "评估" }).getByRole("link", { name: "诊断视图" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: "业务" }).getByRole("link", { name: "提醒记录" })).not.toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: "列显示" }).locator("[aria-current='page']")).toHaveCount(1);
    await expect(page.getByRole("columnheader", { name: "Spans" })).toBeVisible();
    const desktopRunsFilter = page.locator(".runs-filter-form-desktop");
    let runsFilter = desktopRunsFilter;
    if (!(await desktopRunsFilter.isVisible())) {
      const mobileFilter = page.locator(".runs-mobile-filter");
      await mobileFilter.locator("summary").click();
      runsFilter = page.locator(".runs-filter-form-mobile");
    }
    await expect(runsFilter).toBeVisible();
    await runsFilter.getByLabel("交易对").fill("ETH");
    const filteredStatus = EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING ? "allowed" : "blocked";
    await runsFilter.getByLabel("状态").selectOption(filteredStatus);
    await runsFilter.getByLabel("风控").selectOption(filteredStatus);
    await runsFilter.getByRole("button", { name: "筛选" }).click();
    await expect(page).toHaveURL(/symbol=ETH/);
    await expect(
      page.getByRole("row", {
        name: EXPECT_ACTIONABLE_STAGING_PRODUCT_RENDERING ? /ETH-USDT-SWAP.*可人工复核/ : /ETH-USDT-SWAP.*风控阻断/
      }).first()
    ).toBeVisible();
    await expectPageHealthy(page, testInfo, "runs-filtered-observability");

    await page.goto(tracePath.includes("?") ? `${tracePath}&tab=matrix&columns=observability` : `${tracePath}?tab=matrix&columns=observability`);
    await expect(page.getByLabel("工程诊断说明")).toContainText("这是工程诊断视图，不是普通提醒详情");
    await expect(page.getByRole("link", { name: /工程诊断/ })).toHaveClass(/active/);
    await expect(page.getByRole("link", { name: /工程诊断/ })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "工程诊断摘要" })).toBeVisible();
    await expect(page.getByLabel("工程诊断摘要")).toContainText("生产主链");
    await expect(page.getByLabel("工程诊断摘要")).toContainText("模型调用");
    await expect(page.getByText("Worker Matrix")).toBeVisible();
    await expect(page.getByLabel("Worker Matrix").getByText("ExecutionRiskAgent", { exact: true })).toBeVisible();
    await expect(page.locator("main pre")).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText(/\{\s*["'][^"']+["']\s*:/);
    await expectPageHealthy(page, testInfo, "run-detail-matrix");
    if (EXPECT_MOCK_LLM_PRODUCT_RENDERING) {
      seedUnsafeDiagnosticLlmPayload(tracePath);
    }
    await page.goto(tracePath.includes("?") ? `${tracePath}&tab=raw&columns=observability` : `${tracePath}?tab=raw&columns=observability`);
    await expect(page.getByRole("heading", { name: "原始数据", exact: true })).toBeVisible();
    await expect(page.getByLabel("原始数据诊断说明")).toContainText("这是工程诊断视图，不是普通提醒详情");
    await expect(page.getByRole("link", { name: /原始数据/ })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "原始数据摘要" })).toBeVisible();
    await expect(page.getByLabel("原始数据摘要")).toContainText("已应用展示层脱敏");
    await expect(page.locator("summary span").getByText("LLM 交互", { exact: true })).toBeVisible();
    await expect(page.locator("details.json-details[open]")).toHaveCount(0);
    await expect(page.locator("details.json-details pre:visible")).toHaveCount(0);
    if (EXPECT_MOCK_LLM_PRODUCT_RENDERING) {
      const llmJson = page.getByRole("group", { name: "LLM 交互 JSON" });
      await llmJson.locator("summary").click();
      await expect(llmJson).toHaveAttribute("open", "");
      const llmJsonText = llmJson.locator("pre");
      await expect(llmJsonText).toBeVisible();
      await expect(llmJsonText).toContainText("[REDACTED]");
      await expect(llmJsonText).not.toContainText(
        /raw-api-secret|raw-bearer-secret|raw-device-secret|raw-query-secret|raw-response-secret/
      );
    }
    await expectPageHealthy(page, testInfo, "run-detail-raw");

    seedEvalQualityGateRun();
    seedUnknownEvalOutcome();
    await page.goto("/eval");
    await expect(page.getByRole("heading", { name: "质量复盘" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "金融质量" })).toBeVisible();
    await expect(page.getByRole("link", { name: /质量指标/ })).toHaveAttribute("aria-current", "page");
    await expect(main).not.toContainText(/发起复盘|Dataset|Badcase IDs|Mode|judge_only_fixture|judge_openai|复盘批次|问题样本/);
    await expect(page.getByRole("navigation", { name: "质量复盘视图" }).getByRole("link", { name: /复盘批次|问题样本|结果样本/ })).toHaveCount(0);
    await expect(main).not.toContainText(/最近复盘批次|最新回放明细|最新评分明细|Eval Run Detail|Frozen Input|Promotion Artifacts/i);
    await page.goto("/eval?tab=cases");
    await expect(page.getByRole("heading", { name: "工程复盘诊断" })).toBeVisible();
    await expect(page.getByText("发起复盘", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /问题样本/ })).toHaveClass(/active/);
    await expect(page.getByRole("navigation", { name: "质量复盘视图" }).locator("[aria-current='page']")).toHaveCount(1);
    await expectPageHealthy(page, testInfo, "eval-cases");

    await page.goto("/eval/runs/playwright-financial-quality-gate");
    await expect(page.getByRole("heading", { name: "工程复盘诊断" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "复盘批次详情" })).toBeVisible();
    await expect(page.getByRole("link", { name: /返回诊断列表/ })).toHaveAttribute("href", "/eval?tab=runs");
    await expect(main).not.toContainText(/Eval Run Detail|Run ID|Promotion Artifacts|Frozen Input|Frozen Hash|Top Level Keys|fail_count|judge_only_fixture|dataset_name|Artifact\b|Effect\b|Ref\b|hash mismatch/i);
    await expectPageHealthy(page, testInfo, "eval-run-detail");

    await page.goto("/eval?tab=quality");
    await expect(page.getByRole("heading", { name: "金融质量" })).toBeVisible();
    await expect(page.getByRole("link", { name: /质量指标/ })).toHaveAttribute("aria-current", "page");
    const qualityPanel = page.getByRole("heading", { name: "金融质量" }).locator("xpath=ancestor::section[1]");
    await expect(qualityPanel.locator(".error-state")).toHaveCount(0);
    await expect(qualityPanel).toContainText("状态已记录");
    await expect(qualityPanel).toContainText("需人工复核");
    await expect(qualityPanel.getByText("暂无 outcome 样本。")).toHaveCount(0);
    await expect(qualityPanel).toContainText(/已收集结果样本\s*\d+（可评分 0 \/ 待成熟 0 \/ 不可评分 \d+）/);
    const mockedOutcomeRow = qualityPanel.getByRole("row", { name: /样本 1/ });
    await expect(mockedOutcomeRow).toBeVisible();
    await expect(mockedOutcomeRow).toContainText("本地展示样本");
    await expect(mockedOutcomeRow).toContainText("价格不是交易所原生样本");
    await expect(mockedOutcomeRow).toContainText("最终建议链路");
    await expect(mockedOutcomeRow).toContainText("ETH-USDT-SWAP");
    const unknownOutcomeRow = qualityPanel.getByRole("row", { name: /其他复盘目标/ });
    await expect(unknownOutcomeRow).toBeVisible();
    await expect(unknownOutcomeRow).toContainText("其他复盘目标");
    await expect(unknownOutcomeRow).toContainText("其他样本来源");
    await expect(unknownOutcomeRow).toContainText("触发做多");
    await expect(unknownOutcomeRow).toContainText("价格不是交易所原生样本");
    await expect(qualityPanel.getByRole("columnheader", { name: "结果样本" })).toBeVisible();
    await expect(qualityPanel.getByRole("columnheader", { name: "评分目标" }).first()).toBeVisible();
    await expect(qualityPanel.getByRole("columnheader", { name: "建议动作" })).toBeVisible();
    await expect(qualityPanel.getByRole("columnheader", { name: "入场 / 止损" })).toBeVisible();
    const qualityGateTable = qualityPanel.getByRole("table", { name: "金融质量目标门禁" });
    await expect(qualityGateTable.getByRole("row", { name: /候选建议链路/ })).toContainText("样本不足");
    await expect(qualityGateTable.getByRole("row", { name: /不操作基线/ })).toContainText("基线参考");
    await expect(qualityPanel).not.toContainText(/Decision Ref|Target\b|Symbol\b|Action\b|Entry \/ Stop|窗口 Close|OutcomeStore|collect-outcomes|exchange-native|mock seed|mocked-outcome-seed|quality-unknown-seed|待成熟 1|mocked_outcome|price_source_not_exchange_native|legacy_final|swarm_candidate_final|baseline_reference|\bno_trade\b|mystery_target|mystery_source|mystery_action|mystery_unscored_reason|mystery_quality_status|mystery_decision_effect/);
    await expectPageHealthy(page, testInfo, "eval-quality");

    await page.goto("/config");
    await expect(page.getByRole("heading", { name: "生产提醒就绪检查" })).toBeVisible();
    await expectBusinessPageNotJson(page, "生产提醒就绪检查");
    const readinessChecklist = page.getByLabel("生产提醒缺口");
    await expect(readinessChecklist.getByText("还不能作为生产提醒交付", { exact: true })).toBeVisible();
    const modelReadinessItem = readinessChecklist.locator(".risk-summary-item").filter({ hasText: "真实模型" });
    await expect(modelReadinessItem.getByText("真实模型", { exact: true })).toBeVisible();
    await expect(modelReadinessItem.locator("strong")).toHaveText(EXPECT_MOCK_LLM_PRODUCT_RENDERING ? "需处理" : "仅演练");
    await expect(readinessChecklist.getByText("真实行情", { exact: true })).toBeVisible();
    await expect(readinessChecklist.getByText("Bark 通知", { exact: true })).toBeVisible();
    await expect(readinessChecklist.getByText("宏观事件状态", { exact: true })).toBeVisible();
    await expect(readinessChecklist.getByText("运行主链", { exact: true })).toBeVisible();
    await expect(readinessChecklist.getByText("候选旁路", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "配置明细" })).toBeVisible();
    await expect(main).not.toContainText(/配置快照|主流程 Profile|OpenAI Key|Order Book|app\.mode|auto_order_enabled|manual_execution_required|enabled|disabled|SHADOW|fixture|provider|LLM|execution facts|active_event_status|MACRO_EVENT_PROVIDER|CANDIDATE_SIDECAR_MODE/);
    await expectPageHealthy(page, testInfo, "config");

    await runtime.assertClean(testInfo);
  });

  test("core pages stay usable on mobile viewport", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);
    for (const path of ["/", "/manual-run", "/runs", "/runs?columns=observability", "/eval?tab=quality", "/config"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("body")).toBeVisible();
      if (path === "/runs") {
        const primaryRunsContent = page.locator(".table-wrap, .empty-state").first();
        await expect(primaryRunsContent).toBeVisible();
        const contentBox = await primaryRunsContent.boundingBox();
        const viewport = page.viewportSize();
        expect(contentBox, "mobile runs primary content box").not.toBeNull();
        if ((viewport?.width ?? 0) <= 500) {
          expect(contentBox!.y).toBeLessThan((viewport?.height ?? 0) - 120);
        }
      }
      await expectPageHealthyAtScrollPoints(page, testInfo, `mobile-${path.replace(/[^a-z0-9]+/gi, "-") || "home"}`);
      if (path === "/eval?tab=quality") {
        const qualityPanel = page.getByRole("heading", { name: "金融质量" }).locator("xpath=ancestor::section[1]");
        const outcomeTableWrap = qualityPanel.locator(".table-wrap").last();
        await expect(outcomeTableWrap).toBeVisible();
        const scrollMetrics = await outcomeTableWrap.evaluate((element) => ({
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth
        }));
        const viewport = page.viewportSize();
        if ((viewport?.width ?? 0) <= 500) {
          expect(scrollMetrics.scrollWidth).toBeGreaterThan(scrollMetrics.clientWidth);
        }
        if (scrollMetrics.scrollWidth > scrollMetrics.clientWidth) {
          await outcomeTableWrap.evaluate((element) => {
            element.scrollLeft = element.scrollWidth;
          });
        }
        const unscoredReason = qualityPanel.getByText("价格不是交易所原生样本").first();
        await expect(unscoredReason).toBeVisible();
        const reasonBox = await unscoredReason.boundingBox();
        const wrapBox = await outcomeTableWrap.boundingBox();
        expect(reasonBox, "mobile outcome unscored reason cell box").not.toBeNull();
        expect(wrapBox, "mobile outcome table wrapper box").not.toBeNull();
        expect(reasonBox!.x + reasonBox!.width).toBeLessThanOrEqual(wrapBox!.x + wrapBox!.width + 2);
        expect(reasonBox!.x).toBeGreaterThanOrEqual(wrapBox!.x - 2);
      }
    }
    await runtime.assertClean(testInfo);
  });

  test("missing product routes show a product recovery state", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);

    await page.goto("/runs/not-a-real-alert");
    const missingState = page.getByLabel("提醒不存在");
    await expect(missingState.getByRole("heading", { name: "没有找到这条提醒" })).toBeVisible();
    await expect(missingState.getByText("这条提醒可能还没有生成，或本地数据已经被清理。系统不会因为这个页面自动下单。")).toBeVisible();
    await expect(missingState.getByRole("link", { name: "返回提醒记录" })).toHaveAttribute("href", "/runs");
    await expect(missingState.getByRole("link", { name: "新建提醒" })).toHaveAttribute("href", "/manual-run");
    await expectBusinessPageNotJson(page, "没有找到这条提醒");
    await expect(page.locator("main")).not.toContainText(/This page could not be found|404|Unhandled Runtime Error|trace_id|Parsed Plan|request_json|response_json/i);
    await expectPageHealthy(page, testInfo, "missing-run-product-state");
    await runtime.assertClean(testInfo);
  });
});
