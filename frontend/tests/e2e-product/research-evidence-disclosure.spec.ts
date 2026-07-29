import {
  expect,
  test,
  type Locator,
  type Page,
  type Request,
  type TestInfo,
} from "@playwright/test";

const taskId = "22222222-2222-4222-8222-222222222222";
const taskPath = `/api/product/api/v2/tasks/${taskId}`;
const firstTail = "FIRST-SOURCE-FULL-CONTENT-END";
const secondTail = "SECOND-SOURCE-FULL-CONTENT-END";
const writeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

test("fixture projection progressively discloses each Web evidence summary", async ({ page }, testInfo) => {
  const writes: Array<{ method: string; pathname: string }> = [];
  page.on("request", (request) => {
    const observed = observedRequest(request);
    if (writeMethods.has(observed.method)) writes.push(observed);
  });
  await page.emulateMedia({ reducedMotion: "reduce" });

  await page.route(`**${taskPath}/notifications`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ task_id: taskId, items: [] }),
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

  const research = page.locator("section.research-evidence");
  const cards = research.locator(".web-evidence-card");
  await expect(cards).toHaveCount(2);
  const first = cards.nth(0);
  const second = cards.nth(1);
  const firstSummary = first.locator(".evidence-summary");
  const firstToggle = first.getByRole("button", { name: /第一来源.*完整摘要/ });
  const secondToggle = second.getByRole("button", { name: /第二来源.*完整摘要/ });

  await expect(first.getByRole("link", { name: /第一来源/ })).toHaveAttribute(
    "href",
    "https://example.com/evidence/first",
  );
  await expect(first).toContainText("OpenAI Web Search");
  await expect(first).toContainText("支持判断");
  await expect(first).toContainText("发布时间");
  await expect(first).toContainText("抓取时间");
  await expect(second).toContainText("背景信息");
  await expect(firstToggle).toHaveAttribute("aria-expanded", "false");
  await expect(secondToggle).toHaveAttribute("aria-expanded", "false");
  await expect(firstSummary).not.toContainText(firstTail);
  expect(Array.from(await firstSummary.innerText()).length).toBeLessThanOrEqual(121);
  expect(await firstSummary.getAttribute("id")).toBe(await firstToggle.getAttribute("aria-controls"));

  const target = await firstToggle.boundingBox();
  expect(target?.height ?? 0).toBeGreaterThanOrEqual(44);
  await assertNoEvidenceOverflow(page);
  await attachEvidenceScreenshot(page, testInfo, "collapsed");
  await firstToggle.focus();
  await page.keyboard.press("Enter");

  await expect(firstToggle).toHaveAttribute("aria-expanded", "true");
  await expect(firstSummary).toContainText(firstTail);
  await expect(secondToggle).toHaveAttribute("aria-expanded", "false");
  await expect(second).not.toContainText(secondTail);
  await assertNoEvidenceOverflow(page);
  await assertReducedMotion(firstToggle);
  await attachEvidenceScreenshot(page, testInfo, "expanded");

  await page.keyboard.press("Space");
  await expect(firstToggle).toHaveAttribute("aria-expanded", "false");
  await expect(firstSummary).not.toContainText(firstTail);
  expect(writes).toEqual([]);
});

function observedRequest(request: Request) {
  return {
    method: request.method().toUpperCase(),
    pathname: new URL(request.url()).pathname,
  };
}

async function assertNoEvidenceOverflow(page: Page) {
  const audit = await page.evaluate(() => {
    const root = document.documentElement;
    const cards = Array.from(document.querySelectorAll<HTMLElement>(".web-evidence-card"));
    const controls = Array.from(document.querySelectorAll<HTMLElement>(".evidence-summary-toggle"));
    return {
      pageOverflow: Math.max(root.scrollWidth, document.body.scrollWidth) - root.clientWidth,
      cardOverflow: cards.map((card) => card.scrollWidth - card.clientWidth),
      clippedControls: controls.filter((control) => {
        const rect = control.getBoundingClientRect();
        return rect.left < -0.5 || rect.right > root.clientWidth + 0.5;
      }).length,
    };
  });
  expect(audit.pageOverflow).toBeLessThanOrEqual(0);
  expect(audit.cardOverflow.every((overflow) => overflow <= 1)).toBe(true);
  expect(audit.clippedControls).toBe(0);
}

async function assertReducedMotion(toggle: Locator) {
  const transitionSeconds = await toggle.locator("svg").evaluate((icon) => {
    const duration = getComputedStyle(icon).transitionDuration.split(",")[0] ?? "0s";
    return duration.endsWith("ms")
      ? Number.parseFloat(duration) / 1000
      : Number.parseFloat(duration);
  });
  expect(transitionSeconds).toBeLessThanOrEqual(0.001);
}

async function attachEvidenceScreenshot(page: Page, testInfo: TestInfo, phase: "collapsed" | "expanded") {
  await testInfo.attach(`research-evidence-${phase}-${testInfo.project.name}`, {
    body: await page.screenshot({ animations: "disabled", fullPage: true }),
    contentType: "image/png",
  });
}

function succeededTask() {
  return {
    task_id: taskId,
    correlation_id: "99999999-9999-4999-8999-999999999999",
    status: "succeeded",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    query_text: "Assess evidence quality without hiding source details.",
    created_at: "2026-07-17T08:00:00Z",
    completed_at: "2026-07-17T08:15:00Z",
    cancel_requested_at: null,
    artifact: committedArtifact(),
    errors: [],
    agent_stream: null,
    market_snapshot: null,
    web_evidence: [
      evidenceFixture({
        url: "https://example.com/evidence/first",
        title: "第一来源：宏观流动性与风险资产",
        relation: "supports",
        publishedAt: "2026-07-17T07:30:00Z",
        summary: `${"宏观流动性变化仍是风险资产定价的重要变量。".repeat(18)}${firstTail}`,
      }),
      evidenceFixture({
        url: "https://example.com/evidence/second",
        title: "第二来源：衍生品市场结构",
        relation: "context",
        publishedAt: null,
        summary: `${"衍生品持仓与资金费率为当前市场提供独立背景。".repeat(18)}${secondTail}`,
      }),
    ],
    pending_interrupts: null,
  };
}

function evidenceFixture({
  url,
  title,
  relation,
  publishedAt,
  summary,
}: {
  url: string;
  title: string;
  relation: "supports" | "context";
  publishedAt: string | null;
  summary: string;
}) {
  return {
    query: "BTC market evidence",
    final_url: url,
    redirect_chain: [],
    http_status: 200,
    fetched_at: "2026-07-17T08:10:00Z",
    published_at: publishedAt,
    content_hash: "a".repeat(64),
    parser_version: "fixture-evidence-v1",
    title,
    author: "Fixture research desk",
    source: "openai_builtin_web_search",
    excerpt: summary,
    evidence_relation: relation,
  };
}

function committedArtifact() {
  return {
    artifact_type: "analysis_report",
    schema_version: "1.0",
    content_version: 1,
    status: "committed",
    analysis: {
      regime: "event_compression",
      factor_scores: { evidence: 1 },
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
      root_cause_chain: ["Evidence remains mixed."],
      why_not_opposite: "No directional edge is sufficiently confirmed.",
      invalidation: "New verified evidence invalidates this neutral result.",
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
    source_references: [
      "https://example.com/evidence/first",
      "https://example.com/evidence/second",
    ],
  };
}
