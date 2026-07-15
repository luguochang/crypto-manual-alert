import { describe, expect, it } from "vitest";

import { inboxViewSchema } from "../../src/lib/schemas/product-api";

describe("Inbox Product schema", () => {
  it("strictly parses an Inbox view and its official review payload", () => {
    const parsed = inboxViewSchema.parse({
      items: [inboxItem()],
      next_cursor: "eyJzdGF0dXMiOiJhY3RpdmUiLCJ2IjoxfQ",
    });

    expect(parsed.items[0]).toMatchObject({
      status: "pending",
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      member_count: 2,
    });
    expect(parsed.items[0]?.payload.artifact.analysis.reference_price).toBe(67250.5);
  });

  it.each([
    { mutate: (item: ReturnType<typeof inboxItem>) => Object.assign(item, { raw_row_id: "private" }) },
    { mutate: (item: ReturnType<typeof inboxItem>) => Object.assign(item, { status: "unknown" }) },
    { mutate: (item: ReturnType<typeof inboxItem>) => Object.assign(item.payload, { raw_agent_state: {} }) },
    { mutate: (item: ReturnType<typeof inboxItem>) => delete (item.payload as Partial<typeof item.payload>).artifact },
    { mutate: (item: ReturnType<typeof inboxItem>) => Object.assign(item, { horizon: "1h" }) },
  ])("rejects an unknown, incomplete, or inconsistent Inbox item %#", ({ mutate }) => {
    const item = inboxItem();
    mutate(item);

    expect(() => inboxViewSchema.parse({ items: [item], next_cursor: null })).toThrow();
  });

  it("requires coherent response state for resolved and pending items", () => {
    const resolvedWithoutResponse = inboxItem();
    resolvedWithoutResponse.status = "resolved";

    const pendingWithResponse = inboxItem();
    pendingWithResponse.responded_at = "2026-07-15T10:10:00Z";

    expect(() => inboxViewSchema.parse({
      items: [resolvedWithoutResponse],
      next_cursor: null,
    })).toThrow();
    expect(() => inboxViewSchema.parse({
      items: [pendingWithResponse],
      next_cursor: null,
    })).toThrow();
  });

  it("accepts an unanswered expired projection from the persistence contract", () => {
    const expired = inboxItem();
    expired.status = "expired";

    const parsed = inboxViewSchema.parse({ items: [expired], next_cursor: null });

    expect(parsed.items[0]).toMatchObject({
      status: "expired",
      responded_at: null,
    });
  });

  it("rejects extra view fields and malformed opaque cursors", () => {
    expect(() => inboxViewSchema.parse({
      items: [],
      next_cursor: "cursor with spaces",
    })).toThrow();
    expect(() => inboxViewSchema.parse({
      items: [],
      next_cursor: null,
      total: 1,
    })).toThrow();
  });
});

function inboxItem() {
  return {
    task_id: "22222222-2222-4222-8222-222222222222",
    pause_id: "33333333-3333-4333-8333-333333333333",
    pause_version: 1,
    status: "pending" as
      | "pending"
      | "responding"
      | "resolved"
      | "expired"
      | "resume_failed"
      | "cancelled",
    member_count: 2,
    payload: {
      kind: "artifact_review",
      schema_version: "1.0",
      allowed_actions: ["approve", "reject", "edit"],
      review_iteration: 2,
      artifact: {
        artifact_type: "analysis_report",
        schema_version: "1.0",
        content_version: 1,
        status: "draft",
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
          root_cause_chain: ["Momentum improved", "Event risk remains contained"],
          why_not_opposite: "Short momentum lacks confirmation.",
          invalidation: "A 4h close below 65800 invalidates the setup.",
          unavailable_data: [],
          manual_execution_required: true,
          expires_in_seconds: 14400,
        },
        evidence_verdict: {
          sufficient: true,
          confidence_cap: 0.72,
          missing_required: [],
          missing_optional: ["options_skew"],
          warnings: [],
        },
        risk_verdict: {
          allowed: true,
          blocked_reasons: [],
          warnings: ["Use light sizing around event risk."],
          confidence_cap: 0.7,
        },
        source_references: [],
      },
    },
    expires_at: "2026-07-15T18:30:00+08:00",
    responded_at: null as string | null,
    created_at: "2026-07-15T09:30:00Z",
    updated_at: "2026-07-15T09:31:00Z",
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    query_text: "Assess BTC around the next macro event.",
  };
}
