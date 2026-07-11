import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";
import {
  attachRuntimeCollectors,
  expectBusinessPageNotJson,
  expectPageHealthy,
  expectPageHealthyAtScrollPoints
} from "./audit-helpers";

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8010";
const UNSAFE_ERROR_TEXT =
  /SQLITE_ERROR|\/srv\/app|crypto-outcomes\.db|trace_id|request_json|response_json|BARK_DEVICE_KEY|device_key|https:\/\/api\.day\.app|Bearer|api_key|secret/i;
const MISLEADING_SAVED_TEXT =
  /本次记录已保存|本次访问记录已保存|已保存，便于后续排查/;
const UNSAFE_REASON =
  "SQLITE_ERROR at /srv/app/data/eval/crypto-outcomes.db trace_id=abc request_json payload BARK_DEVICE_KEY=secret https://api.day.app/device/body Bearer raw-secret api_key=secret";
const SAFE_EVAL_ERROR = "复盘请求暂时无法完成，请稍后重试。";

async function submitEvalRun(page: import("@playwright/test").Page) {
  await page.goto("/eval?tab=runs");
  await expect(page.getByRole("heading", { name: "工程复盘诊断" })).toBeVisible();
  await page.getByRole("button", { name: "运行规则 eval" }).click();
  await expect(page.locator(".error-inline[role='alert']")).toContainText(SAFE_EVAL_ERROR);
  await expect(page.locator("body")).not.toContainText(UNSAFE_ERROR_TEXT);
}

async function createManualRun(request: APIRequestContext) {
  const response = await request.post(`${API_BASE_URL}/api/runs/manual`, {
    data: {
      symbol: "ETH-USDT-SWAP",
      query: "错误态回归测试：关注后续复盘和诊断错误脱敏。",
      horizon: "6h",
      alert_channel: "bark",
      position: { side: "unknown" },
      risk_mode: "normal"
    }
  });
  expect(response.ok(), "manual run seed response").toBeTruthy();
  const body = await response.json();
  const traceId = body?.data?.trace_id;
  const planId = body?.data?.plan?.plan_id;
  expect(traceId, "manual run seed trace id").toBeTruthy();
  expect(planId, "manual run seed plan id").toBeTruthy();
  return { traceId: String(traceId), planId: String(planId) };
}

function seedUnsafeRunDiagnostics(traceId: string, planId: string) {
  const dbPath = path.resolve(process.cwd(), "..", ".tmp", "dev-server", "data", "crypto-alert.db");
  execFileSync(
    "python3",
    [
      "-c",
      `
import json
import sqlite3
import sys

db_path, trace_id, plan_id = sys.argv[1], sys.argv[2], sys.argv[3]
unsafe = "SQLITE_ERROR at /srv/app/data/eval/crypto-outcomes.db trace_id=abc request_json payload BARK_DEVICE_KEY=secret https://api.day.app/device/body Bearer raw-secret"

with sqlite3.connect(db_path) as conn:
    conn.execute(
        """
        UPDATE trace_spans
        SET status = 'error',
            error_type = 'SQLITE_ERROR',
            error_message = ?
        WHERE span_id = (
            SELECT span_id FROM trace_spans WHERE trace_id = ? ORDER BY started_at LIMIT 1
        )
        """,
        (unsafe, trace_id),
    )
    row = conn.execute("SELECT payload_json FROM plan_runs WHERE plan_id = ?", (plan_id,)).fetchone()
    if row is None:
        raise SystemExit("missing plan run")
    payload = json.loads(row[0])
    sidecar = payload.setdefault("candidate_final_decision", {})
    sidecar.setdefault("decision_effect", "none")
    sidecar.setdefault("production_final_input", False)
    sidecar.setdefault("input_gate_passed", False)
    sidecar.setdefault("input_ref", f"{trace_id}:pre_final_decision_input")
    sidecar["error"] = {
        "type": "SQLITE_ERROR",
        "message": unsafe,
        "detail": {"request_json": unsafe, "trace_id": trace_id},
    }
    conn.execute(
        "UPDATE plan_runs SET payload_json = ? WHERE plan_id = ?",
        (json.dumps(payload, ensure_ascii=False, sort_keys=True), plan_id),
    )
`,
      dbPath,
      traceId,
      planId
    ],
    { stdio: "pipe" }
  );
}

async function assertNoUnsafeErrorText(page: Page) {
  await expect(page.locator("body")).not.toContainText(UNSAFE_ERROR_TEXT);
}

async function assertNoMisleadingSavedClaim(page: Page) {
  await expect(page.locator("body")).not.toContainText(MISLEADING_SAVED_TEXT);
}

test.describe("product error state redaction", () => {
  test("manual run API 500 hides backend internals", async ({ page }) => {
    await page.route(`${API_BASE_URL}/api/runs/manual`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          error: {
            code: "internal_error",
            message:
              "SQLITE_ERROR at /srv/app/data/eval/crypto-outcomes.db trace_id=abc request_json payload BARK_DEVICE_KEY=secret https://api.day.app/device/body Bearer raw-secret"
          }
        })
      });
    });

    await page.goto("/manual-run");
    await page.getByRole("button", { name: "生成提醒建议" }).click();
    await expect(page.locator(".error-state[role='alert']")).toContainText("提醒暂时生成失败，无法确认是否写入记录");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
  });

  test("manual run partial success keeps readable alert and detail link", async ({ page }) => {
    await page.route(`${API_BASE_URL}/api/runs/manual`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          data: {
            trace_id: "partial-summary-trace",
            plan: {
              plan_id: "partial-summary-plan",
              instrument: "ETH-USDT-SWAP",
              main_action: "trigger long",
              horizon: "6h",
              manual_execution_required: true,
              expires_at: "2026-07-09T12:00:00+08:00",
              reference_price: 3500,
              entry_trigger: 3510,
              stop_price: 3435,
              target_1: 3580,
              target_2: 3660,
              probability: 0.58
            },
            verdict: {
              allowed: false,
              reasons: [UNSAFE_REASON],
              warnings: []
            }
          }
        })
      });
    });

    await page.goto("/manual-run");
    await page.getByRole("button", { name: "生成提醒建议" }).click();
    const resultPanel = page.getByRole("heading", { name: "本次提醒建议", exact: true }).locator("xpath=ancestor::*[self::section or self::article or self::div][1]");
    await expect(resultPanel.getByRole("heading", { name: "本次提醒建议", exact: true })).toBeVisible();
    await expect(resultPanel.getByText("摘要暂不可用", { exact: true }).first()).toBeVisible();
    await expect(resultPanel.getByLabel("模型返回摘要")).toBeVisible();
    await expect(resultPanel.getByText("结果尚未生成", { exact: true })).toBeVisible();
    await expect(resultPanel.getByRole("link", { name: "查看详情" })).toHaveAttribute("href", "/runs/partial-summary-trace");
    await expect(page.locator(".error-state")).toHaveCount(0);
    await expect(
      resultPanel.getByText("风控结论已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。").first()
    ).toBeVisible();
    await expect(resultPanel).not.toContainText("工程诊断中核对");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
  });

  test("manual run productizes market failures without overstating production proof", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);
    const longFailure = `订单簿连接超时：${"marketdatafailurecontext".repeat(28)}`;
    const longCompletion = `模型结论：暂不操作，等待交易所原生行情恢复后重新人工复核。${"当前不应开仓，继续等待。".repeat(36)}`;

    await page.route(`${API_BASE_URL}/api/runs/manual`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          data: {
            trace_id: "long-trading-data-trace",
            plan: {
              plan_id: "long-trading-data-plan",
              instrument: "ETH-USDT-SWAP",
              main_action: "no trade",
              horizon: "6h",
              manual_execution_required: true,
              expires_at: "2026-07-11T12:00:00+08:00",
              reference_price: null,
              entry_trigger: null,
              stop_price: null,
              target_1: null,
              target_2: null,
              probability: 0.31
            },
            verdict: {
              allowed: true,
              reasons: [],
              warnings: ["交易所执行事实不完整，本次只允许暂不操作。"]
            },
            business_summary: {
              title: "ETH-USDT-SWAP 手动提醒计划",
              mode_notice: "真实模型已返回，但交易所行情不可用；本次只允许暂不操作，不能作为开仓依据。",
              decision_label: "暂不操作",
              action_text: "no trade",
              confidence_text: "低（31%）",
              price_levels: {
                reference_price: null,
                entry_trigger: null,
                stop_price: null,
                target_1: null,
                target_2: null,
                expires_at: "2026-07-11T12:00:00+08:00"
              },
              reason_bullets: ["交易所执行事实缺失，模型选择暂不操作。"],
              risk_bullets: ["订单簿、标记价和指数价恢复前禁止开仓。"],
              evidence_bullets: ["模型返回已记录；OKX public 行情失败已记录。"],
              data_gap_bullets: [longFailure],
              next_steps: ["等待交易所行情恢复后重新生成提醒。"],
              safety_notice: "系统只生成提醒与审计记录，不自动下单。",
              generation_summary: {
                mode_label: "真实模型链路",
                provider: "openai_compatible",
                provider_label: "OpenAI-compatible",
                model: "gpt-live",
                status: "ok",
                status_label: "模型已返回",
                duration_text: "1234 ms",
                token_text: "432 tokens",
                finish_reason: "stop",
                response_summary: "模型结论：暂不操作，等待交易所原生行情恢复。",
                raw_completion_label: "模型原始返回摘录",
                raw_completion_excerpt: longCompletion,
                detail_bullets: ["模型输出仅供人工复核。"]
              },
              market_data_status: {
                provider: "okx_public",
                provider_label: "OKX public",
                symbol: "ETH-USDT-SWAP",
                summary: "OKX public 行情：成功 0 项，失败 2 项，缺失 5 项；执行事实不完整。",
                execution_facts_ready: false,
                success_count: 0,
                failed_count: 2,
                missing_count: 5,
                items: [
                  {
                    name: "order_book",
                    label: "order_book",
                    status: "failed",
                    status_label: "失败",
                    source: "okx_public",
                    source_label: "OKX public",
                    can_satisfy_execution_fact: true,
                    value_text: null,
                    error_type: null,
                    failure_reason: longFailure
                  },
                  {
                    name: "mark",
                    label: "mark",
                    status: "failed",
                    status_label: "失败",
                    source: "okx_public",
                    source_label: "OKX public",
                    can_satisfy_execution_fact: true,
                    value_text: null,
                    error_type: "ConnectError",
                    failure_reason: UNSAFE_REASON
                  },
                  {
                    name: "index",
                    label: "index",
                    status: "failed",
                    status_label: "失败",
                    source: "okx_public",
                    source_label: "OKX public",
                    can_satisfy_execution_fact: true,
                    value_text: null,
                    error_type: "InvalidPayload",
                    failure_reason: UNSAFE_REASON
                  }
                ],
                failures: []
              },
              notification: {
                enabled: true,
                channel: "bark",
                status: "sent",
                status_code: 200,
                sent_at: "2026-07-11T11:00:00+08:00",
                error: null,
                message: "Bark 已发送。"
              }
            }
          }
        })
      });
    });

    await page.goto("/manual-run");
    await page.getByRole("button", { name: "生成提醒建议" }).click();
    const resultPanel = page.getByRole("heading", { name: "本次提醒建议", exact: true }).locator("xpath=ancestor::*[self::section or self::article or self::div][1]");
    await expect(resultPanel).toBeVisible();
    const tradingData = resultPanel.getByLabel("交易数据状态");
    await expect(tradingData).toBeVisible();
    await expect(tradingData).toContainText("失败");
    await expect(tradingData).toContainText("订单簿连接超时");
    await expect(tradingData).toContainText("marketdatafailurecontext");
    for (const label of ["指数价", "标记价", "订单簿"]) {
      await expect(tradingData.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(resultPanel.getByLabel("提醒证据级别")).not.toContainText("生产可复核证据已记录");
    await expect(tradingData).toContainText("ConnectError");
    await expect(tradingData).toContainText("InvalidPayload");
    await expect(tradingData).not.toContainText("内容已记录，当前摘要不可读");
    const rawCompletion = resultPanel.getByLabel("模型返回摘要").getByLabel("模型原始返回摘录");
    await expect(rawCompletion).toBeVisible();
    await expect(rawCompletion).toContainText("等待交易所原生行情恢复");
    await assertNoUnsafeErrorText(page);
    await expectPageHealthyAtScrollPoints(page, testInfo, "manual-run-long-trading-data-failure");
    await runtime.assertClean(testInfo);
  });

  test("eval run API 500 hides backend internals", async ({ page }) => {
    await page.route(`${API_BASE_URL}/api/eval/runs`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          error: {
            code: "internal_error",
            message:
              "SQLITE_ERROR at /srv/app/data/eval/crypto-outcomes.db trace_id=abc request_json payload BARK_DEVICE_KEY=secret https://api.day.app/device/body"
          }
        })
      });
    });

    await submitEvalRun(page);
  });

  test("eval run invalid envelope uses safe product copy", async ({ page }) => {
    await page.route(`${API_BASE_URL}/api/eval/runs`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          unexpected: "response_json",
          message: "trace_id=abc request_json=/srv/app/secret"
        })
      });
    });

    await submitEvalRun(page);
  });

  test("eval run network abort uses safe product copy", async ({ page }) => {
    await page.route(`${API_BASE_URL}/api/eval/runs`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.abort("failed");
    });

    await submitEvalRun(page);
  });

  test("run diagnostic matrix hides unsafe span and candidate errors", async ({ page, request }) => {
    const { traceId, planId } = await createManualRun(request);
    seedUnsafeRunDiagnostics(traceId, planId);

    await page.goto(`/runs/${encodeURIComponent(traceId)}?columns=observability&tab=matrix`);
    await expect(page.getByRole("heading", { name: "工程诊断摘要" })).toBeVisible();
    await expect(page.getByText("执行异常").first()).toBeVisible();
    await assertNoUnsafeErrorText(page);
  });
});

test.describe("Server Component first-load API failures", () => {
  test.skip(
    process.env.PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS !== "true",
    "requires PLAYWRIGHT_LOCAL_STACK_FLAGS='--seed-mock-outcome --with-error-internal-api'",
  );

  test("eval diagnostic tabs sanitize server-side GET failures", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);

    await page.goto("/eval?tab=runs");
    await expect(page.getByRole("heading", { name: "工程复盘诊断" })).toBeVisible();
    await expect(page.locator(".error-state[role='alert']")).toContainText("复盘批次暂时无法加载，请稍后重试。");
    await expectBusinessPageNotJson(page, "工程复盘诊断");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
    await expectPageHealthy(page, testInfo, "server-component-eval-runs-error");

    await page.goto("/eval?tab=cases");
    await expect(page.getByRole("heading", { name: "工程复盘诊断" })).toBeVisible();
    await expect(page.locator(".error-state[role='alert']")).toContainText("问题样本暂时无法加载，请稍后重试。");
    await expectBusinessPageNotJson(page, "工程复盘诊断");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
    await expectPageHealthy(page, testInfo, "server-component-eval-cases-error");

    await page.goto("/eval?tab=quality");
    await expect(page.getByRole("heading", { name: "质量复盘" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "金融质量" })).toBeVisible();
    await expect(page.locator(".error-state")).toContainText("结果样本暂时无法加载，请稍后重试。");
    await expectBusinessPageNotJson(page, "金融质量");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
    await expectPageHealthy(page, testInfo, "server-component-eval-quality-error");

    await runtime.assertClean(testInfo);
  });

  test("runs list and detail failures do not claim a record was saved", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);

    await page.goto("/runs");
    await expect(page.getByRole("heading", { name: "提醒记录" })).toBeVisible();
    await expect(page.locator(".error-state[role='alert']")).toContainText("提醒记录暂时无法加载，请稍后重试。");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
    await expectPageHealthy(page, testInfo, "server-component-runs-list-error");

    await page.goto("/runs/unavailable-trace");
    await expect(page.locator(".error-state[role='alert']")).toContainText("提醒详情暂时无法加载，请稍后重试。");
    await assertNoUnsafeErrorText(page);
    await assertNoMisleadingSavedClaim(page);
    await expectPageHealthy(page, testInfo, "server-component-run-detail-error");

    await runtime.assertClean(testInfo);
  });

  test("run detail partial projection keeps readable fallback", async ({ page }, testInfo) => {
    const runtime = attachRuntimeCollectors(page);

    await page.goto("/runs/partial-detail-trace");
    await expect(page.getByRole("heading", { name: "提醒详情" })).toBeVisible();
    await expect(page.getByRole("region", { name: "提醒建议摘要" })).toBeVisible();
    await expect(page.getByText("摘要暂不可用", { exact: true }).first()).toBeVisible();
    await expect(page.getByLabel("模型返回摘要")).toBeVisible();
    await expect(page.getByRole("heading", { name: "后续复盘" })).toBeVisible();
    await expect(page.getByText("结果尚未生成", { exact: true })).toBeVisible();
    await expect(page.locator(".error-state")).toHaveCount(0);
    await expectBusinessPageNotJson(page, "建议摘要");
    await assertNoUnsafeErrorText(page);
    await expectPageHealthy(page, testInfo, "server-component-run-detail-partial");

    await runtime.assertClean(testInfo);
  });
});
