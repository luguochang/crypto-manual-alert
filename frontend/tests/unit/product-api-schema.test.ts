import { describe, expect, it } from "vitest";

import {
  analysisSubmissionSchema,
  interruptResponseSchema,
  productRunListSchema,
  productTaskSchema,
  runStatusSchema,
} from "../../src/lib/schemas/product-api";

const allStatuses = [
  "queued",
  "running",
  "waiting_human",
  "succeeded",
  "blocked",
  "failed",
  "cancelled",
] as const;

describe("Product API schemas", () => {
  it("strictly parses the tenant-scoped Run list projection", () => {
    const parsed = productRunListSchema.parse({
      items: [
        {
          run_id: "11111111-1111-4111-8111-111111111111",
          task_id: "22222222-2222-4222-8222-222222222222",
          attempt: 1,
          status: "succeeded",
          symbol: "BTC-USDT-SWAP",
          horizon: "4h",
          created_at: "2026-07-13T08:30:00Z",
          finished_at: "2026-07-13T08:35:00Z",
          main_action: "no_trade",
        },
      ],
      limit: 25,
    });

    expect(parsed.items[0]).toMatchObject({
      attempt: 1,
      status: "succeeded",
      main_action: "no_trade",
    });
    expect(() => productRunListSchema.parse({
      items: [{ ...parsed.items[0], browser_owned_actor: "attacker" }],
      limit: 25,
    })).toThrow();
  });

  it("accepts exactly the supported analysis request fields", () => {
    const parsed = analysisSubmissionSchema.parse({
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      query_text: "Assess the next BTC move with current macro risk.",
      notify: false,
    });

    expect(parsed).toEqual({
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      query_text: "Assess the next BTC move with current macro risk.",
      notify: false,
    });
    expect(() =>
      analysisSubmissionSchema.parse({
        symbol: "DOGE-USDT-SWAP",
        horizon: "4h",
        query_text: "Assess DOGE.",
      }),
    ).toThrow();
  });

  it.each(allStatuses)("accepts the %s Product status", (status) => {
    expect(runStatusSchema.parse(status)).toBe(status);
  });

  it("persists a pending cancellation timestamp in the task projection", () => {
    const pending = productTaskSchema.parse({
      ...taskProjection("running"),
      cancel_requested_at: "2026-07-14T15:30:00Z",
    });

    expect(pending.cancel_requested_at).toBe("2026-07-14T15:30:00Z");
    expect(productTaskSchema.parse(taskProjection("running")).cancel_requested_at).toBeNull();
  });

  it("strictly parses a nullable official Agent stream binding", () => {
    const task = {
      ...taskProjection("running"),
      agent_stream: {
        protocol: "langgraph-v2",
        assistant_id: " crypto-analysis ",
        thread_id: " 6b83a8ca-80f8-4e73-8d3e-f1fd919222b7 ",
        run_id: " 70a9077b-4ff4-43ec-8f71-6d086ccde870 ",
      },
    };

    expect(productTaskSchema.parse(task).agent_stream).toEqual({
      protocol: "langgraph-v2",
      assistant_id: "crypto-analysis",
      thread_id: "6b83a8ca-80f8-4e73-8d3e-f1fd919222b7",
      run_id: "70a9077b-4ff4-43ec-8f71-6d086ccde870",
    });
    expect(productTaskSchema.parse(taskProjection("queued")).agent_stream).toBeNull();
    expect(productTaskSchema.parse({
      ...taskProjection("queued"),
      agent_stream: null,
    }).agent_stream).toBeNull();
  });

  it.each([
    { protocol: "langgraph-v1", assistant_id: "assistant", thread_id: "thread", run_id: "run" },
    { protocol: "langgraph-v2", assistant_id: "", thread_id: "thread", run_id: "run" },
    { protocol: "langgraph-v2", assistant_id: "assistant", thread_id: "thread", run_id: "run", extra: true },
    { protocol: "langgraph-v2", assistant_id: "assistant", thread_id: "thread" },
    { protocol: "langgraph-v2", assistant_id: "x".repeat(256), thread_id: "thread", run_id: "run" },
  ])("rejects a malformed Agent stream binding %#", (agentStream) => {
    expect(() => productTaskSchema.parse({
      ...taskProjection("running"),
      agent_stream: agentStream,
    })).toThrow();
  });

  it("normalizes a successful Product artifact into typed numeric fields", () => {
    const parsed = productTaskSchema.parse(successTask());

    expect(parsed.artifact?.analysis.reference_price).toBe(67250.5);
    expect(parsed.artifact?.analysis.entry_trigger).toBe(67400);
    expect(parsed.artifact?.analysis.target_2).toBe(70100);
    expect(parsed.artifact?.analysis.probability).toBe(0.68);
    expect(parsed.artifact?.source_references).toEqual([
      "https://example.com/market/btc",
      "https://example.com/macro/fed",
    ]);
  });

  it("strictly parses typed market and Web evidence projections without raw provider payloads", () => {
    const task = successTask();
    Object.assign(task, researchProjection());

    const parsed = productTaskSchema.parse(task);

    expect(parsed.market_snapshot).toMatchObject({
      symbol: "BTC-USDT-SWAP",
      source_level: "exchange_native",
      mark_price: 67250.5,
      index_price: 67198.25,
      funding_rate: 0.0001,
      open_interest: 48210.75,
      ticker: {
        last: 67248.2,
        bid: 67247.9,
        ask: 67248.4,
        volume_24h: 18750.25,
      },
    });
    expect(parsed.web_evidence).toEqual([
      expect.objectContaining({
        title: "Fed calendar keeps event risk elevated",
        source: "openai_web_search",
        final_url: "https://example.com/markets/fed-calendar",
        fetched_at: "2026-07-13T08:28:00Z",
        published_at: "2026-07-13T07:45:00Z",
        excerpt: "A scheduled policy speech may lift intraday volatility.",
      }),
    ]);

    const rawSnapshot = successTask();
    const rawResearch = researchProjection();
    Object.assign(rawResearch.market_snapshot, { private_exchange_payload: { instId: "BTC" } });
    Object.assign(rawSnapshot, rawResearch);
    expect(() => productTaskSchema.parse(rawSnapshot)).toThrow();
  });

  it("defaults absent research projections for tasks created before typed evidence was added", () => {
    const parsed = productTaskSchema.parse(taskProjection("running"));

    expect(parsed.market_snapshot).toBeNull();
    expect(parsed.web_evidence).toEqual([]);
  });

  it("accepts only the allowlisted provider failure diagnostics", () => {
    const task = {
      ...taskProjection("failed"),
      errors: [{
        code: "research_unavailable",
        message: "检索服务没有返回可验证来源，当前未生成分析结果。",
        retryable: true,
        provider: "builtin_web_search",
        error_type: "UnverifiedServerToolCall",
        attempt: 3,
      }],
    };

    expect(productTaskSchema.parse(task).errors[0]).toEqual(task.errors[0]);
    expect(() => productTaskSchema.parse({
      ...task,
      errors: [{ ...task.errors[0], raw_response: "must-not-cross-the-BFF" }],
    })).toThrow();
  });

  it.each([
    ["javascript:alert(1)", "2026-07-13T08:28:00Z"],
    ["https://example.com/source", "not-a-time"],
  ])("rejects unsafe or malformed Web evidence (%s, %s)", (finalUrl, fetchedAt) => {
    const task = successTask();
    const research = researchProjection();
    research.web_evidence[0].final_url = finalUrl;
    research.web_evidence[0].fetched_at = fetchedAt;
    Object.assign(task, research);

    expect(() => productTaskSchema.parse(task)).toThrow();
  });

  it("accepts sparse string and status values allowed by the backend WebEvidence type", () => {
    const task = successTask();
    const research = researchProjection();
    Object.assign(research.web_evidence[0], {
      query: "",
      http_status: 0,
      content_hash: "",
      parser_version: "",
      title: "",
      author: "",
      source: "",
      excerpt: "",
      evidence_relation: "",
    });
    Object.assign(task, research);

    expect(productTaskSchema.parse(task).web_evidence[0]).toMatchObject({
      http_status: 0,
      title: "",
      author: "",
      source: "",
      excerpt: "",
    });
  });

  it.each(["draft", "streaming", "failed"] as const)(
    "rejects a succeeded task with a %s artifact",
    (artifactStatus) => {
      const task = successTask();
      task.artifact.status = artifactStatus;

      expect(() => productTaskSchema.parse(task)).toThrow();
    },
  );

  it("rejects a succeeded task without an artifact", () => {
    expect(() => productTaskSchema.parse({ ...successTask(), artifact: null })).toThrow();
  });

  it.each(["queued", "running", "waiting_human", "blocked", "failed", "cancelled"] as const)(
    "keeps a previously committed artifact readable while the latest run is %s",
    (taskStatus) => {
      const task = successTask();
      task.status = taskStatus;

      expect(productTaskSchema.parse(task).artifact?.status).toBe("committed");
    },
  );

  it("accepts a reviewable draft artifact on a blocked task", () => {
    const task = blockedDraftTask();

    expect(productTaskSchema.parse(task).artifact?.status).toBe("draft");
  });

  it("rejects a blocked draft whose risk verdict is allowed", () => {
    const task = blockedDraftTask();
    task.artifact.risk_verdict.allowed = true;
    task.artifact.risk_verdict.blocked_reasons = [];

    expect(() => productTaskSchema.parse(task)).toThrow();
  });

  it("rejects a committed artifact with a blocked risk verdict", () => {
    const task = successTask();
    task.artifact.risk_verdict.allowed = false;
    task.artifact.risk_verdict.blocked_reasons = ["risk.limit"];

    expect(() => productTaskSchema.parse(task)).toThrow();
  });

  it("rejects a committed artifact with insufficient evidence", () => {
    const task = successTask();
    task.artifact.evidence_verdict.sufficient = false;
    task.artifact.evidence_verdict.confidence_cap = 0;
    task.artifact.evidence_verdict.missing_required = ["order_book"];

    expect(() => productTaskSchema.parse(task)).toThrow();
  });

  it.each([
    ["instrument", "ETH-USDT-SWAP"],
    ["horizon", "1d"],
  ] as const)("rejects an artifact whose %s does not match its task", (field, value) => {
    const task = successTask();
    task.artifact.analysis[field] = value;

    expect(() => productTaskSchema.parse(task)).toThrow();
  });

  it("rejects inconsistent evidence verdicts", () => {
    const sufficientWithMissingData = successTask();
    sufficientWithMissingData.artifact.evidence_verdict.missing_required = ["order_book"];

    const insufficientWithoutMissingData = blockedDraftTask();
    insufficientWithoutMissingData.artifact.evidence_verdict.missing_required = [];

    expect(() => productTaskSchema.parse(sufficientWithMissingData)).toThrow();
    expect(() => productTaskSchema.parse(insufficientWithoutMissingData)).toThrow();
  });

  it("rejects inconsistent risk verdicts", () => {
    const allowedWithReasons = successTask();
    allowedWithReasons.artifact.risk_verdict.blocked_reasons = ["risk.limit"];

    const blockedWithoutReasons = blockedDraftTask();
    blockedWithoutReasons.artifact.risk_verdict.blocked_reasons = [];

    expect(() => productTaskSchema.parse(allowedWithReasons)).toThrow();
    expect(() => productTaskSchema.parse(blockedWithoutReasons)).toThrow();
  });

  it("rejects unsafe source links", () => {
    const task = successTask();
    task.artifact.source_references = ["javascript:alert(1)"];

    expect(() => productTaskSchema.parse(task)).toThrow();
  });

  it("strictly parses the official pending artifact review projection", () => {
    const task = waitingHumanTask("pending");
    const parsed = productTaskSchema.parse(task);

    expect(parsed.pending_interrupts).toEqual([
      expect.objectContaining({
        task_id: task.task_id,
        interrupt_id: "interrupt-review-1",
        response_version: 3,
        status: "pending",
        response: null,
        expires_at: "2026-07-15T18:30:00+08:00",
      }),
    ]);
    expect(parsed.pending_interrupts[0]?.payload.artifact.status).toBe("draft");

    const withRawPayload = waitingHumanTask("pending");
    Object.assign(withRawPayload.pending_interrupts[0].payload, {
      raw_agent_interrupt: { resumable: true },
    });
    expect(() => productTaskSchema.parse(withRawPayload)).toThrow();
  });

  it("parses a responding projection whose persisted response has no response_version", () => {
    const task = waitingHumanTask("responding");
    task.pending_interrupts[0].response = {
      action: "edit",
      comment: "Reduce risk before the next gate.",
      edits: {
        regime: null,
        factor_scores: null,
        total_score: null,
        main_action: "open_long",
        reference_price: null,
        entry_trigger: null,
        stop_price: null,
        target_1: null,
        target_2: null,
        probability: 0.61,
        position_size_class: "light",
        max_leverage: 2,
        risk_pct: "0.005",
        root_cause_chain: ["Momentum remains positive", "Event risk is elevated"],
        why_not_opposite: "Downside confirmation is incomplete.",
        invalidation: "A close below support invalidates the thesis.",
        unavailable_data: null,
        manual_execution_required: null,
        expires_in_seconds: null,
      },
    };
    task.pending_interrupts[0].responded_at = "2026-07-15T10:20:00Z";

    const parsed = productTaskSchema.parse(task);

    expect(parsed.pending_interrupts[0]?.response).toMatchObject({
      action: "edit",
      edits: { risk_pct: 0.005 },
    });
  });

  it("strictly validates approve, reject, and controlled edit submissions", () => {
    expect(interruptResponseSchema.parse({
      response_version: 3,
      action: "approve",
      comment: null,
    })).toEqual({
      response_version: 3,
      action: "approve",
      comment: null,
    });
    expect(interruptResponseSchema.parse({
      response_version: 3,
      action: "reject",
      edits: null,
      comment: "Evidence quality is too low.",
    }).action).toBe("reject");

    const edited = interruptResponseSchema.parse({
      response_version: 3,
      action: "edit",
      comment: "Use a smaller position.",
      edits: {
        main_action: "open_long",
        probability: "0.61",
        position_size_class: "light",
        max_leverage: 125,
        risk_pct: "0.005",
        root_cause_chain: ["Momentum remains positive"],
        why_not_opposite: "Downside confirmation is incomplete.",
        invalidation: "A close below support invalidates the thesis.",
      },
    });
    expect(edited).toMatchObject({
      action: "edit",
      edits: { probability: 0.61, risk_pct: 0.005, max_leverage: 125 },
    });

    expect(() => interruptResponseSchema.parse({
      response_version: 3,
      action: "edit",
      edits: {},
    })).toThrow();
    expect(() => interruptResponseSchema.parse({
      response_version: 3,
      action: "approve",
      edits: { main_action: "open_long" },
    })).toThrow();
    expect(() => interruptResponseSchema.parse({
      response_version: 3,
      action: "edit",
      edits: { main_action: "open_long", raw_agent_state: true },
    })).toThrow();
  });

  it("requires absolute server timestamps and coherent pending/responding states", () => {
    const localTimestamp = waitingHumanTask("pending");
    localTimestamp.pending_interrupts[0].expires_at = "2026-07-15T18:30:00";

    const pendingWithResponse = waitingHumanTask("pending");
    pendingWithResponse.pending_interrupts[0].response = {
      action: "approve",
      comment: null,
      edits: null,
    };

    const respondingWithoutResponse = waitingHumanTask("responding");

    expect(() => productTaskSchema.parse(localTimestamp)).toThrow();
    expect(() => productTaskSchema.parse(pendingWithResponse)).toThrow();
    expect(() => productTaskSchema.parse(respondingWithoutResponse)).toThrow();
  });
});

function successTask() {
  return {
    task_id: "task-success",
    status: "succeeded",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    errors: [],
    artifact: {
      artifact_type: "analysis_report",
      schema_version: "1.0",
      content_version: 1,
      status: "committed",
      analysis: {
        regime: "risk_on",
        factor_scores: { momentum: 2, macro: 1 },
        total_score: 3,
        main_action: "open_long",
        instrument: "BTC-USDT-SWAP",
        horizon: "4h",
        reference_price: "67250.5",
        entry_trigger: "67400",
        stop_price: "65800",
        target_1: "68800",
        target_2: "70100",
        probability: 0.68,
        position_size_class: "light",
        max_leverage: 2,
        risk_pct: "0.01",
        root_cause_chain: ["Momentum improved", "Macro event risk is contained"],
        why_not_opposite: "Short momentum lacks confirmation.",
        invalidation: "A 4h close below 65800 invalidates the setup.",
        unavailable_data: [],
        manual_execution_required: true,
        expires_in_seconds: 14400,
      },
      evidence_verdict: {
        sufficient: true,
        confidence_cap: 0.72,
        missing_required: [] as string[],
        missing_optional: ["options_skew"],
        warnings: ["US session liquidity has not opened."],
      },
      risk_verdict: {
        allowed: true,
        blocked_reasons: [] as string[],
        warnings: ["Use light sizing around event risk."],
        confidence_cap: 0.7,
      },
      source_references: [
        "https://example.com/market/btc",
        "https://example.com/macro/fed",
      ],
    },
  };
}

function blockedDraftTask() {
  const task = successTask();
  task.status = "blocked";
  task.artifact.status = "draft";
  task.artifact.evidence_verdict.sufficient = false;
  task.artifact.evidence_verdict.confidence_cap = 0;
  task.artifact.evidence_verdict.missing_required = ["order_book"];
  task.artifact.risk_verdict.allowed = false;
  task.artifact.risk_verdict.confidence_cap = 0;
  task.artifact.risk_verdict.blocked_reasons = ["evidence.insufficient:order_book"];
  return task;
}

function waitingHumanTask(status: "pending" | "responding") {
  const task = blockedDraftTask();
  return {
    ...task,
    status: "waiting_human",
    pending_interrupts: [{
      task_id: task.task_id,
      run_id: "11111111-1111-4111-8111-111111111111",
      interrupt_id: "interrupt-review-1",
      namespace: "review",
      checkpoint_id: "checkpoint-review-1",
      response_version: 3,
      status,
      payload: {
        kind: "artifact_review",
        schema_version: "1.0",
        allowed_actions: ["approve", "reject", "edit"],
        review_iteration: 2,
        artifact: structuredClone(task.artifact),
      },
      response: null as null | Record<string, unknown>,
      expires_at: "2026-07-15T18:30:00+08:00",
      responded_at: null as string | null,
    }],
  };
}

function taskProjection(status: (typeof allStatuses)[number]) {
  return {
    task_id: "task-schema-1",
    status,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    completed_at: null,
    artifact: null,
    errors: [],
  };
}

function researchProjection() {
  return {
    market_snapshot: {
      symbol: "BTC-USDT-SWAP",
      fetched_at: "2026-07-13T08:29:00Z",
      source_level: "exchange_native",
      ticker: {
        last: "67248.2",
        bid: "67247.9",
        ask: "67248.4",
        volume_24h: "18750.25",
      },
      mark_price: "67250.5",
      index_price: "67198.25",
      funding_rate: "0.0001",
      open_interest: "48210.75",
      order_book: {
        bids: [{ price: "67247.9", size: "2.4" }],
        asks: [{ price: "67248.4", size: "1.8" }],
      },
      candles: [{
        timestamp: "2026-07-13T08:00:00Z",
        open: "67150",
        high: "67310",
        low: "67090",
        close: "67248.2",
        volume: "412.8",
      }],
    },
    web_evidence: [{
      query: "BTC macro event risk",
      final_url: "https://example.com/markets/fed-calendar",
      redirect_chain: [],
      http_status: 200,
      fetched_at: "2026-07-13T08:28:00Z",
      published_at: "2026-07-13T07:45:00Z",
      content_hash: "a".repeat(64),
      parser_version: "openai-responses-citation-v1",
      title: "Fed calendar keeps event risk elevated",
      author: "Markets desk",
      source: "openai_web_search",
      excerpt: "A scheduled policy speech may lift intraday volatility.",
      evidence_relation: "supports",
    }],
  };
}
