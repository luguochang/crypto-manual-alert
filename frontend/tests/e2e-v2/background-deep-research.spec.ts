import { expect, test, type Page, type TestInfo } from "@playwright/test";
import axe from "axe-core";

const taskId = "22222222-2222-4222-8222-222222222222";
const runId = "11111111-1111-4111-8111-111111111111";

test("restores one persisted Deep Research report after browser rejoin", async ({ page }, testInfo) => {
  let taskReads = 0;
  await page.route(`**/api/product/api/v2/tasks/${taskId}*`, async (route) => {
    taskReads += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(deepResearchTask()),
    });
  });

  await page.goto(`/work?task=${taskId}`);
  await assertResearchReport(page);

  await page.goto("about:blank");
  await page.goto(`/work?task=${taskId}`);
  await assertResearchReport(page);

  expect(taskReads).toBeGreaterThanOrEqual(2);
  await assertPageQuality(page, testInfo);
});

async function assertResearchReport(page: Page) {
  await expect(page.getByTestId("deep-research-projection")).toBeVisible();
  await expect(page.getByRole("heading", { name: "深度研究已完成" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "研究结论" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "检索覆盖" })).toBeVisible();
  await expect(page.getByText("1 / 2 条查询返回了可验证来源", { exact: true }))
    .toBeVisible();
  await page.getByText("查看未完成查询", { exact: true }).click();
  await expect(page.getByText("查询 2：检索超时（第 3 次）", { exact: true }))
    .toBeVisible();
  await expect(page.getByText("BTC 机构采用仍在推进。", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "机构采用" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "可验证来源" })).toBeVisible();
  await expect(page.getByRole("link", {
    name: "Verified institutional source",
    exact: true,
  }))
    .toHaveAttribute("href", "https://example.com/verified-institutional-source");
  await expect(page.locator("pre")).toHaveCount(0);
  await expect(page.getByText(/\{\s*"(?:report|sources|artifact_type)"/)).toHaveCount(0);
}

async function assertPageQuality(page: Page, testInfo: TestInfo) {
  await page.getByRole("heading", { name: "可验证来源" }).scrollIntoViewIfNeeded();
  await page.addScriptTag({ content: axe.source });
  const audit = await page.evaluate(async () => {
    const runtime = (window as typeof window & {
      axe: { run: () => Promise<{
        violations: Array<{
          id: string;
          nodes: Array<{ target: string[]; failureSummary?: string }>;
        }>;
      }> };
    }).axe;
    const result = await runtime.run();
    const duplicateIds = Array.from(document.querySelectorAll<HTMLElement>("[id]"))
      .map((element) => element.id)
      .filter((id, index, ids) => ids.indexOf(id) !== index);
    const unnamedControls = Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea"),
    ).filter((element) => {
      const labelledBy = (element.getAttribute("aria-labelledby") ?? "")
        .split(/\s+/)
        .filter(Boolean)
        .map((id) => document.getElementById(id)?.textContent ?? "")
        .join(" ");
      const labels = "labels" in element
        ? Array.from((element as HTMLInputElement).labels ?? [])
            .map((label) => label.textContent ?? "")
            .join(" ")
        : "";
      const name = element.getAttribute("aria-label")
        || labelledBy
        || labels
        || element.textContent
        || "";
      return !name.trim();
    }).length;
    return {
      violations: result.violations.map((item) => ({
        id: item.id,
        nodes: item.nodes.map((node) => ({
          target: node.target,
          failureSummary: node.failureSummary,
        })),
      })),
      viewportOverflow: document.documentElement.scrollWidth - window.innerWidth,
      duplicateIds,
      unnamedControls,
      rawJson: document.body.innerText.includes("artifact_type")
        || document.body.innerText.includes("source_indexes"),
    };
  });

  expect(audit.violations).toEqual([]);
  expect(audit.viewportOverflow).toBeLessThanOrEqual(0);
  expect(audit.duplicateIds).toEqual([]);
  expect(audit.unnamedControls).toBe(0);
  expect(audit.rawJson).toBe(false);
  await testInfo.attach(`deep-research-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
}

function deepResearchTask() {
  const now = "2026-07-19T12:05:00Z";
  const evidence = {
    query: "BTC institutional adoption",
    final_url: "https://example.com/verified-institutional-source",
    redirect_chain: [],
    http_status: 200,
    fetched_at: "2026-07-19T12:00:00Z",
    published_at: "2026-07-19T08:00:00Z",
    content_hash: "a".repeat(64),
    parser_version: "test-v1",
    title: "Verified institutional source",
    author: "Research Desk",
    source: "test_search",
    excerpt: "A verified source records continued institutional product activity.",
    evidence_relation: "supports",
  };
  return {
    task_id: taskId,
    task_type: "deep_research",
    correlation_id: "33333333-3333-4333-8333-333333333333",
    status: "succeeded",
    symbol: "BTC-USDT-SWAP",
    horizon: "7d",
    query_text: "研究 BTC 机构采用趋势和主要反证。",
    created_at: "2026-07-19T12:00:00Z",
    completed_at: now,
    cancel_requested_at: null,
    artifact: null,
    deep_research_artifact: {
      artifact_type: "deep_research_report",
      schema_version: "1.0",
      status: "committed",
      harness_mode: "deepagents",
      search_coverage: {
        status: "partial",
        attempted_queries: 2,
        successful_queries: 1,
        failed_queries: [{
          query_index: 2,
          provider: "builtin_web_search",
          error_kind: "timeout",
          retryable: true,
          attempt: 3,
        }],
      },
      report: {
        executive_summary: "BTC 机构采用仍在推进。",
        sections: [{
          title: "机构采用",
          summary: "可验证来源支持该趋势，但样本窗口仍然有限。",
          findings: [{
            claim: "机构产品活动保持增长。",
            source_indexes: [1],
          }],
        }],
        risk_notes: ["事件窗口可能快速改变当前判断。"],
        evidence_gaps: ["缺少跨周期资金流样本。"],
      },
      sources: [{ index: 1, evidence }],
      model_audits: [],
    },
    errors: [],
    completion_scope: {
      analysis: "complete",
      notification: "not_requested",
      observability: "not_enabled",
    },
    warnings: [],
    agent_stream: null,
    stage_history: {
      run_id: runId,
      stages: [
        {
          sequence: 1,
          stage: "web_evidence",
          status: "committed",
          recorded_at: now,
          source: "product_projection",
        },
        {
          sequence: 2,
          stage: "analysis",
          status: "committed",
          recorded_at: now,
          source: "product_projection",
        },
        {
          sequence: 3,
          stage: "artifact",
          status: "committed",
          recorded_at: now,
          source: "product_projection",
        },
        {
          sequence: 4,
          stage: "run",
          status: "succeeded",
          recorded_at: now,
          source: "product_projection",
        },
      ],
      product_event_cursor: 4,
      official_stream_cursor: null,
      official_stream_cursor_at: null,
    },
    market_snapshot: null,
    web_evidence: [evidence],
    pending_interrupts: null,
    projection_scope: { mode: "latest", selected_run_id: null },
  };
}
