import { expect, test } from "@playwright/test";
import {
  evalCandidateCategoryText,
  evalCandidateDatasetText,
  evalCandidateSeverityText,
  evalCandidateStatusText,
  evalCandidateActualBehaviorText,
  evalCandidateExpectedBehaviorText,
  evalCandidatesErrorMessage
} from "../../src/app/eval/eval-candidates-table";
import {
  evalJudgeFailureCategoryText,
  evalJudgeNameText,
  evalJudgeSeverityText,
  evalJudgeTypeText,
  evalJudgeEvidenceText,
  evalJudgeReasonText,
  evalJudgeScoresErrorMessage
} from "../../src/app/eval/eval-judge-scores-table";
import { evalReplayErrorMessage, evalReplayResultText } from "../../src/app/eval/eval-replay-table";
import { financialQualityOutcomeErrorMessage } from "../../src/app/eval/financial-quality-panel";
import { formatJson, redactJsonForDisplay } from "../../src/app/shared/json-details";
import { productDisplayItems, productDisplayText } from "../../src/app/shared/product-copy";
import { safeDisplayError } from "../../src/app/shared/safe-error";
import { manualRunResponseSchema } from "../../src/lib/schemas/manual-run";
import { runDetailSchema, runListSchema } from "../../src/lib/schemas/runs";

test.describe("product copy safety", () => {
  const fallbackSummary = "内容已记录，当前摘要不可读";
  const fallbackContent = "内容已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";
  const fallbackReason = "风控结论已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";
  const unsafeError =
    "SQLITE_ERROR at /srv/app/data/eval/crypto-outcomes.db trace_id=abc request_json payload BARK_DEVICE_KEY=secret https://api.day.app/device/body Bearer raw-secret api_key=secret";

  function completeBusinessSummary(text = "人工复核提醒") {
    return {
      title: text,
      mode_notice: text,
      decision_label: "可人工复核",
      action_text: "trigger long",
      confidence_text: text,
      price_levels: {
        reference_price: 3500,
        entry_trigger: 3510,
        stop_price: 3435,
        target_1: 3580,
        target_2: 3660,
        expires_at: "2026-07-09T12:00:00+08:00"
      },
      reason_bullets: [text],
      risk_bullets: [text],
      evidence_bullets: [text],
      data_gap_bullets: [text],
      next_steps: [text],
      safety_notice: text,
      generation_summary: {
        mode_label: text,
        provider_label: text,
        model: text,
        status_label: text,
        duration_text: text,
        token_text: text,
        finish_reason: text,
        response_summary: text,
        detail_bullets: [text]
      },
      notification: {
        enabled: true,
        channel: "bark",
        status: "failed",
        status_code: 500,
        sent_at: null,
        error: text,
        message: text
      }
    };
  }

  function runDetailPayload(planRunOverrides: Record<string, unknown> = {}, traceOverrides: Record<string, unknown> = {}) {
    return {
      trace: {
        trace_id: "partial-detail-trace",
        status: "blocked",
        run_type: "manual",
        symbol: "ETH-USDT-SWAP",
        created_at: "2026-07-09T10:00:00+08:00",
        ended_at: null,
        final_plan_id: "partial-detail-plan",
        final_action: "trigger long",
        allowed: false,
        span_count: 0,
        llm_interaction_count: 0,
        ...traceOverrides
      },
      plan_run: {
        plan_id: "partial-detail-plan",
        status: "blocked",
        parsed_plan: {
          plan_id: "partial-detail-plan",
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
          reasons: [unsafeError],
          warnings: []
        },
        business_summary: null,
        payload_keys: [],
        ...planRunOverrides
      },
      analysis: {},
      spans: [],
      llm_interactions: [],
      badcases: [],
      notification_history: []
    };
  }

  const productionIntentMainPathContract = {
    schema_version: "2026-07-09.main-path-contract.v1",
    runtime_role: "production_main",
    proof_level: "production-intent-contract",
    production_success: false,
    hosted_proof_required: true,
    does_not_prove: "hosted_prod_actionable",
    final_input_contract: {
      mode: "legacy_prompt",
      production_final_input_mode: "legacy_prompt",
      legacy_prompt_required: true,
      candidate_sidecar_mode: "disabled",
      candidate_sidecar_can_replace_final_input: false
    },
    manual_only: {
      manual_execution_required: true,
      auto_order_enabled: false,
      order_submission: "disabled"
    },
    query_contract: {
      mode: "audit_note",
      drives_final_input: false,
      drives_execution_facts: false
    }
  };

  test("unknown internal tokens fall back to product language", () => {
    expect(productDisplayText("trigger long")).toBe("触发做多");
    expect(productDisplayText("manual_execution_required")).toBe("人工手动执行要求");
    expect(productDisplayText("new_internal_gate_reason")).toBe(fallbackSummary);
    expect(productDisplayText("candidate.confidence_cap_exceeded")).toBe(fallbackSummary);
    expect(productDisplayText("BARK_DEVICE_KEY")).toBe(fallbackSummary);
    expect(productDisplayText("OPENAI_API_KEY")).toBe(fallbackSummary);
    expect(productDisplayText("REQUEST_JSON")).toBe(fallbackSummary);
    expect(productDisplayText("PRODUCTION_CONTROL_GATE")).toBe(fallbackSummary);
    expect(productDisplayText("production_control.candidate.confidence_cap_exceeded")).toBe(fallbackSummary);
    expect(productDisplayItems(["new_internal_gate_reason", "trigger short"])).toEqual([
      fallbackSummary,
      "触发做空"
    ]);
  });

  test("model free-text keeps market indicator names instead of hiding the whole excerpt", () => {
    const text =
      "模型结论：funding_rate 回落、open_interest 降温，BTC.D 未继续走强，ETH 可等待 trigger long 后人工复核。";

    const rendered = productDisplayText(text);

    expect(rendered).toContain("funding_rate 回落");
    expect(rendered).toContain("open_interest 降温");
    expect(rendered).toContain("BTC.D 未继续走强");
    expect(rendered).toContain("触发做多");
    expect(rendered).not.toContain(fallbackSummary);
  });

  test("real model mode notice translates provider tokens without unreadable fallback", () => {
    const text = "当前配置使用 openai_compatible 决策引擎，但行情仍为 fixture；本次只证明模型调用链路。";

    const rendered = productDisplayText(text);

    expect(rendered).toContain("当前配置使用外部模型决策引擎");
    expect(rendered).toContain("行情仍为 演练数据");
    expect(rendered).not.toContain("openai_compatible");
    expect(rendered).not.toContain(fallbackSummary);
  });

  test("financial quality product error hides backend internals", () => {
    const message = financialQualityOutcomeErrorMessage(
      "SQLITE_ERROR: no such table eval_decision_outcomes at /srv/app/data/eval/crypto-outcomes.db trace_id=abc request_json payload"
    );

    expect(message).toBe("结果样本暂时无法加载，请稍后重试。");
    expect(message).not.toContain("SQLITE_ERROR");
    expect(message).not.toContain("/srv/app");
    expect(message).not.toContain("crypto-outcomes.db");
    expect(message).not.toContain("trace_id");
    expect(message).not.toContain("request_json");
  });

  test("shared error copy hides backend internals but keeps local validation", () => {
    const message = safeDisplayError(unsafeError, "复盘请求暂时无法完成，请稍后重试。");

    expect(message).toBe("复盘请求暂时无法完成，请稍后重试。");
    expect(message).not.toContain("SQLITE_ERROR");
    expect(message).not.toContain("/srv/app");
    expect(message).not.toContain("trace_id");
    expect(message).not.toContain("request_json");
    expect(message).not.toContain("BARK_DEVICE_KEY");
    expect(message).not.toContain("api.day.app");
    expect(safeDisplayError("Badcase IDs 只能填写英文逗号分隔的正整数，例如 12, 18, 23。")).toBe(
      "Badcase IDs 只能填写英文逗号分隔的正整数，例如 12, 18, 23。"
    );
    expect(
      safeDisplayError(
        "Traceback at /Users/chase/project/app.py Authorization: Basic raw-secret",
        "复盘请求暂时无法完成，请稍后重试。"
      )
    ).toBe("复盘请求暂时无法完成，请稍后重试。");
    expect(
      safeDisplayError(
        "failed opening C:\\Users\\chase\\secret\\payload.json",
        "复盘请求暂时无法完成，请稍后重试。"
      )
    ).toBe("复盘请求暂时无法完成，请稍后重试。");
    expect(safeDisplayError("321 tokens")).toBe("321 tokens");
    expect(safeDisplayError("token=hidden", "复盘请求暂时无法完成，请稍后重试。")).toBe(
      "复盘请求暂时无法完成，请稍后重试。"
    );
  });

  test("manual run partial projection sanitizes unsafe verdict reasons", () => {
    const parsed = manualRunResponseSchema.parse({
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
        reasons: [unsafeError],
        warnings: []
      },
      business_summary: { title: "partial only" }
    });

    const rendered = [
      ...parsed.verdict.reasons,
      ...parsed.business_summary.reason_bullets
    ].join("\n");

    expect(rendered).toContain(fallbackReason);
    expect(rendered).not.toContain("SQLITE_ERROR");
    expect(rendered).not.toContain("/srv/app");
    expect(rendered).not.toContain("BARK_DEVICE_KEY");
    expect(rendered).not.toContain("api_key");
    expect(parsed.business_summary.generation_summary.mode_label).toBe("摘要暂不可用");
  });

  test("manual run schemas preserve main path proof contract", () => {
    const parsedManualRun = manualRunResponseSchema.parse({
      trace_id: "main-path-contract-trace",
      plan: {
        plan_id: "main-path-contract-plan",
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
        reasons: ["production intent contract recorded"],
        warnings: []
      },
      main_path_contract: productionIntentMainPathContract
    });

    expect((parsedManualRun as Record<string, unknown>).main_path_contract).toMatchObject({
      proof_level: "production-intent-contract",
      production_success: false,
      hosted_proof_required: true,
      does_not_prove: "hosted_prod_actionable"
    });

    const parsedDetail = runDetailSchema.parse(
      runDetailPayload({
        main_path_contract: productionIntentMainPathContract
      })
    );
    expect((parsedDetail.plan_run as Record<string, unknown>).main_path_contract).toMatchObject({
      runtime_role: "production_main",
      final_input_contract: expect.objectContaining({
        mode: "legacy_prompt",
        candidate_sidecar_mode: "disabled"
      }),
      manual_only: expect.objectContaining({
        manual_execution_required: true,
        auto_order_enabled: false
      })
    });
  });

  test("valid business summary projection sanitizes unsafe visible text", () => {
    const parsed = manualRunResponseSchema.parse({
      trace_id: "unsafe-valid-summary-trace",
      plan: {
        plan_id: "unsafe-valid-summary-plan",
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
        reasons: ["visible business reason"],
        warnings: []
      },
      business_summary: completeBusinessSummary(unsafeError)
    });

    const rendered = JSON.stringify(parsed.business_summary);
    expect(rendered).toContain(fallbackContent);
    expect(rendered).not.toContain("SQLITE_ERROR");
    expect(rendered).not.toContain("/srv/app");
    expect(rendered).not.toContain("BARK_DEVICE_KEY");
    expect(rendered).not.toContain("api_key");
    expect(rendered).not.toContain("Bearer");
  });

  test("business summary schema sanitizes model excerpt and trading data status", () => {
    const parsed = manualRunResponseSchema.parse({
      trace_id: "market-status-summary-trace",
      plan: {
        plan_id: "market-status-summary-plan",
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
        reasons: ["visible business reason"],
        warnings: []
      },
      business_summary: {
        ...completeBusinessSummary("人工复核提醒"),
        generation_summary: {
          ...completeBusinessSummary("人工复核提醒").generation_summary,
          raw_completion_label: "模型原始返回摘录",
          raw_completion_excerpt: unsafeError
        },
        market_data_status: {
          provider: "okx_public",
          provider_label: "OKX public",
          symbol: "ETH-USDT-SWAP",
          summary: "OKX public 行情：成功 3 项，失败 1 项；执行事实不完整。",
          execution_facts_ready: false,
          success_count: 1,
          failed_count: 2,
          missing_count: 0,
          items: [
            {
              name: "index",
              label: "index",
              status: "ok",
              status_label: "成功",
              source: "okx_public",
              source_label: "OKX public",
              can_satisfy_execution_fact: true,
              value_text: "3500.00",
              error_type: null,
              failure_reason: null
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
              error_type: "InvalidPayload",
              failure_reason: unsafeError
            },
            {
              name: "order_book",
              label: "order_book",
              status: "failed",
              status_label: "失败",
              source: "okx_public",
              source_label: "OKX public",
              can_satisfy_execution_fact: true,
              value_text: null,
              error_type: "request_json",
              failure_reason: unsafeError
            }
          ],
          failures: [
            {
              name: "mark",
              label: "mark",
              error_type: "InvalidPayload",
              reason: unsafeError
            },
            {
              name: "order_book",
              label: "order_book",
              error_type: "request_json",
              reason: unsafeError
            }
          ]
        }
      }
    });

    const rendered = JSON.stringify(parsed.business_summary);
    expect(parsed.business_summary.generation_summary.raw_completion_label).toBe("模型原始返回摘录");
    expect(parsed.business_summary.generation_summary.raw_completion_excerpt).toBe(fallbackContent);
    expect(parsed.business_summary.market_data_status.provider_label).toBe("OKX public");
    expect(parsed.business_summary.market_data_status.execution_facts_ready).toBe(false);
    expect(parsed.business_summary.market_data_status.items.map((item) => item.name)).toEqual([
      "index",
      "mark",
      "order_book"
    ]);
    expect(parsed.business_summary.market_data_status.items.map((item) => item.label)).toEqual([
      "指数价",
      "标记价",
      "订单簿"
    ]);
    expect(parsed.business_summary.market_data_status.items[1].error_type).toBe("InvalidPayload");
    expect(parsed.business_summary.market_data_status.items[1].failure_reason).toBe(fallbackContent);
    expect(parsed.business_summary.market_data_status.items[2].error_type).toBeNull();
    expect(parsed.business_summary.market_data_status.failures.map((failure) => failure.label)).toEqual([
      "标记价",
      "订单簿"
    ]);
    expect(parsed.business_summary.market_data_status.failures[0].error_type).toBe("InvalidPayload");
    expect(parsed.business_summary.market_data_status.failures[1].error_type).toBeNull();
    expect(parsed.business_summary.market_data_status.failures[0].reason).toBe(fallbackContent);
    expect(rendered).not.toContain("SQLITE_ERROR");
    expect(rendered).not.toContain("/srv/app");
    expect(rendered).not.toContain("trace_id");
    expect(rendered).not.toContain("BARK_DEVICE_KEY");
    expect(rendered).not.toContain("api_key");
    expect(rendered).not.toContain("Bearer");
  });

  test("run detail accepts bad business summary shapes and sanitizes verdict reasons", () => {
    for (const badShape of [null, {}, { title: "partial only" }]) {
      const parsed = runDetailSchema.parse(runDetailPayload({ business_summary: badShape }));

      expect(parsed.plan_run?.business_summary.generation_summary.mode_label).toBe("摘要暂不可用");
      expect(parsed.plan_run?.verdict.reasons).toEqual([fallbackReason]);
      expect(parsed.plan_run?.business_summary.reason_bullets).toEqual([
        fallbackReason
      ]);
    }
  });

  test("run detail schema sanitizes product-visible agent audit reasons", () => {
    const parsed = runDetailSchema.parse(
      runDetailPayload({
        agent_audit_view: {
          available: true,
          facts_gate: {
            reasons: [unsafeError],
            missing_execution_facts: ["active_event_status"]
          },
          gates: {
            production_control_gate: {
              allowed: false,
              reasons: [unsafeError]
            }
          },
          candidate_final_comparison: {
            production_final_input: false,
            production_control_gate: {
              reasons: [unsafeError]
            },
            candidate: {
              diagnosis: {
                blocking_reasons: [unsafeError]
              }
            }
          }
        }
      })
    );

    const rendered = JSON.stringify(parsed.plan_run?.agent_audit_view);
    expect(rendered).toContain(fallbackReason);
    expect(rendered).not.toContain("SQLITE_ERROR");
    expect(rendered).not.toContain("/srv/app");
    expect(rendered).not.toContain("BARK_DEVICE_KEY");
    expect(rendered).not.toContain("api_key");
  });

  test("run list tolerates bad optional projections without hiding the run", () => {
    const parsed = runListSchema.parse({
      items: [
        {
          trace_id: "list-partial-projection-trace",
          status: "blocked",
          run_type: "manual",
          symbol: "ETH-USDT-SWAP",
          created_at: "2026-07-09T10:00:00+08:00",
          ended_at: null,
          final_plan_id: "list-partial-projection-plan",
          final_action: "trigger long",
          allowed: false,
          business_summary: { title: "partial only" },
          result_review: { status: "partial only" },
          span_count: 0,
          llm_interaction_count: 0
        }
      ]
    });

    expect(parsed.items).toHaveLength(1);
    expect(parsed.items[0].business_summary).toBeNull();
    expect(parsed.items[0].result_review).toBeNull();
  });

  test("eval diagnostic tables sanitize list failure messages", () => {
    const html = [
      evalCandidatesErrorMessage(unsafeError),
      evalReplayErrorMessage(unsafeError),
      evalJudgeScoresErrorMessage(unsafeError)
    ].join("\n");

    expect(html).toContain("问题样本暂时无法加载，请稍后重试。");
    expect(html).toContain("回放明细暂时无法加载，请稍后重试。");
    expect(html).toContain("评分明细暂时无法加载，请稍后重试。");
    expect(html).not.toContain("SQLITE_ERROR");
    expect(html).not.toContain("/srv/app");
    expect(html).not.toContain("crypto-outcomes.db");
    expect(html).not.toContain("trace_id");
    expect(html).not.toContain("request_json");
    expect(html).not.toContain("BARK_DEVICE_KEY");
    expect(html).not.toContain("api.day.app");
    expect(html).not.toContain("raw-secret");
  });

  test("eval diagnostic table row text hides backend internals", () => {
    const windowsPathError =
      "Traceback at C:\\Users\\chase\\secret\\payload.json Authorization: Basic raw-secret token=hidden";
    const unixPathError = "SQLITE_ERROR at /Users/chase/project/data/eval.db trace_id=abc";
    const rowText = [
      evalCandidateExpectedBehaviorText(windowsPathError),
      evalCandidateActualBehaviorText(unixPathError),
      evalCandidateCategoryText(unixPathError),
      evalCandidateDatasetText(windowsPathError),
      evalCandidateSeverityText("/private/tmp/leaked-severity"),
      evalCandidateStatusText("payload status trace_id=abc"),
      evalJudgeNameText("llm.evidence_grounding"),
      evalJudgeTypeText("llm"),
      evalJudgeSeverityText("/srv/app/leaked-severity.db"),
      evalJudgeFailureCategoryText("/srv/app/data/eval.db"),
      evalJudgeReasonText(unsafeError),
      evalJudgeEvidenceText({ evidence_refs: [unsafeError] }),
      evalReplayResultText({
        status: "completed",
        mode: "fixture",
        final_action: "/var/app/leaked-plan.json",
        allowed: true,
        output_hash: "hash-1234567890",
        metadata: {}
      })
    ].join("\n");

    expect(rowText).toContain(fallbackContent);
    expect(rowText).not.toContain("SQLITE_ERROR");
    expect(rowText).not.toContain("/Users/chase");
    expect(rowText).not.toContain("/var/app");
    expect(rowText).not.toContain("C:\\Users");
    expect(rowText).not.toContain("trace_id");
    expect(rowText).not.toContain("BARK_DEVICE_KEY");
    expect(rowText).not.toContain("Authorization");
    expect(rowText).not.toContain("Bearer");
    expect(rowText).not.toContain("api_key");
    expect(rowText).not.toContain("raw-secret");
    expect(rowText).not.toContain("llm.evidence_grounding");
    expect(rowText).not.toContain("/srv/app");
    expect(rowText).not.toContain("/private/tmp");
    expect(evalCandidateCategoryText("grounding_error")).toBe("证据支撑不足");
    expect(evalCandidateDatasetText("failure_cases")).toBe("问题样本集");
    expect(evalCandidateSeverityText("high")).toBe("高风险");
    expect(evalCandidateStatusText("open")).toBe("待处理");
    expect(evalJudgeSeverityText("critical")).toBe("严重");
    expect(evalJudgeFailureCategoryText("candidate_gate_failed")).toBe("候选门槛未通过");
  });

  test("diagnostic JSON rendering redacts secret-shaped values defensively", () => {
    const payload = {
      api_key: "sk-live-secret",
      token: "token-secret",
      nested: {
        BARK_DEVICE_KEY: "bark-device-secret",
        Authorization: "Bearer raw-header-secret",
        callback_url: "https://api.day.app/bark-device-secret/title/body?token=url-secret",
        safe_value: "visible product evidence"
      },
      rows: [
        {
          device_key: "row-device-secret",
          message: "free text with Bearer free-text-secret and BARK_DEVICE_KEY: free-text-device"
        }
      ]
    };

    const redacted = redactJsonForDisplay(payload) as Record<string, unknown>;
    const rendered = formatJson(payload);

    expect(redacted.api_key).toBe("[REDACTED]");
    expect(rendered).toContain("visible product evidence");
    expect(rendered).not.toContain("sk-live-secret");
    expect(rendered).not.toContain("token-secret");
    expect(rendered).not.toContain("bark-device-secret");
    expect(rendered).not.toContain("raw-header-secret");
    expect(rendered).not.toContain("url-secret");
    expect(rendered).not.toContain("row-device-secret");
    expect(rendered).not.toContain("free-text-secret");
    expect(rendered).not.toContain("free-text-device");
    expect(rendered).not.toContain("https://api.day.app/bark-device-secret");
  });
});
