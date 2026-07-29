import { expect, test, type Request } from "@playwright/test";

const taskId = "22222222-2222-4222-8222-222222222222";
const taskPath = `/api/product/api/v2/tasks/${taskId}`;
const notificationsPath = `${taskPath}/notifications`;
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

test("discovers a delayed notification projection after refresh recovery", async ({ page }) => {
  let notificationReads = 0;
  const writes: Array<{ method: string; pathname: string }> = [];
  page.on("request", (request) => {
    const observed = observedRequest(request);
    if (writeMethods.has(observed.method)) writes.push(observed);
  });

  await page.route(`**${notificationsPath}`, async (route) => {
    notificationReads += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        task_id: taskId,
        items: notificationReads < 3 ? [] : [deliveredNotification()],
      }),
    });
  });
  await page.route(`**${taskPath}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(succeededTask()),
    });
  });

  await page.goto(`/work?task=${taskId}`);

  await expect(page.getByText("Provider 已接收", { exact: true })).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText("bark:1721116920", { exact: true })).toBeVisible();
  expect(notificationReads).toBeGreaterThanOrEqual(3);
  expect(writes).toEqual([]);

  await page.reload();

  await expect(page.getByText("Provider 已接收", { exact: true })).toBeVisible();
  await expect(page.getByText("bark:1721116920", { exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});

function observedRequest(request: Request) {
  return {
    method: request.method().toUpperCase(),
    pathname: new URL(request.url()).pathname,
  };
}

function deliveredNotification() {
  return {
    notification_id: "77777777-7777-4777-8777-777777777777",
    task_id: taskId,
    run_id: "33333333-3333-4333-8333-333333333333",
    artifact_id: "44444444-4444-4444-8444-444444444444",
    artifact_version_id: "55555555-5555-4555-8555-555555555555",
    decision_id: "66666666-6666-4666-8666-666666666666",
    decision_version: 1,
    channel: "bark",
    type: "analysis_completed",
    status: "delivered",
    attempt_count: 1,
    manual_resend_pending: false,
    manual_resend_available: false,
    manual_resend_requested_at: null,
    available_at: "2026-07-16T08:00:00Z",
    delivered_at: "2026-07-16T08:02:00Z",
    terminal_at: "2026-07-16T08:02:00Z",
    created_at: "2026-07-16T08:00:00Z",
    updated_at: "2026-07-16T08:02:00Z",
    attempts: [{
      attempt_id: "88888888-8888-4888-8888-888888888888",
      attempt_number: 1,
      trigger: "automatic",
      result: "delivered",
      reason: null,
      delay_seconds: 0,
      retry_after_seconds: null,
      cost_units: "0.000000",
      provider_receipt: "bark:1721116920",
      error_code: null,
      created_at: "2026-07-16T08:01:00Z",
      finished_at: "2026-07-16T08:02:00Z",
    }],
  };
}

function succeededTask() {
  return {
    task_id: taskId,
    correlation_id: "99999999-9999-4999-8999-999999999999",
    status: "succeeded",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    query_text: "Assess the current market structure.",
    created_at: "2026-07-16T08:00:00Z",
    completed_at: "2026-07-16T08:02:00Z",
    cancel_requested_at: null,
    artifact: {
      artifact_type: "analysis_report",
      schema_version: "1.0",
      content_version: 1,
      status: "committed",
      analysis: {
        regime: "risk_on",
        factor_scores: { momentum: 1 },
        total_score: 1,
        main_action: "no_trade",
        instrument: "BTC-USDT-SWAP",
        horizon: "4h",
        reference_price: 67_250,
        entry_trigger: null,
        stop_price: null,
        target_1: null,
        target_2: null,
        probability: 0.6,
        position_size_class: "none",
        max_leverage: 1,
        risk_pct: 0,
        root_cause_chain: ["The persisted projection is complete."],
        why_not_opposite: "Evidence does not support directional exposure.",
        invalidation: "A material market regime change invalidates this result.",
        unavailable_data: [],
        manual_execution_required: true,
        expires_in_seconds: 14_400,
      },
      evidence_verdict: {
        sufficient: true,
        confidence_cap: 0.7,
        missing_required: [],
        missing_optional: [],
        warnings: [],
      },
      risk_verdict: {
        allowed: true,
        blocked_reasons: [],
        warnings: [],
        confidence_cap: 0.7,
      },
      source_references: [],
    },
    errors: [],
    agent_stream: null,
    market_snapshot: null,
    web_evidence: [],
    pending_interrupts: null,
  };
}
