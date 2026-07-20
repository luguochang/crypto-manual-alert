import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  HumanReviewPanel,
  isReviewActionAvailable,
  isServerExpiredReviewConflict,
  reviewItemIdentity,
  resolveAvailableReviewActions,
  resolveReviewDeadlineHint,
  resolveReviewInteractionState,
  resolveReviewStateAnnouncement,
  resolveReviewSourceReference,
} from "../../src/features/work/human-review-panel";
import type { AnalysisPendingInterrupt } from "../../src/lib/schemas/product-api";

const allReviewActions = ["approve", "reject", "edit"] as const;

describe("human review panel", () => {
  describe("risk action policy", () => {
    it("removes approve while retaining reject and edit when risk is blocked", () => {
      expect(resolveAvailableReviewActions(allReviewActions, false)).toEqual([
        "reject",
        "edit",
      ]);
      expect(isReviewActionAvailable(allReviewActions, false, "approve")).toBe(false);
      expect(isReviewActionAvailable(allReviewActions, false, "reject")).toBe(true);
      expect(isReviewActionAvailable(allReviewActions, false, "edit")).toBe(true);
    });

    it("preserves the Product-declared actions when risk allows approval", () => {
      expect(resolveAvailableReviewActions(allReviewActions, true)).toEqual(allReviewActions);
    });

    it("does not render an approve control for a risk-blocked artifact", () => {
      const html = renderReview(reviewInterrupt({ riskAllowed: false }));

      expect(html).not.toContain("is-approve");
      expect(html).toContain("is-reject");
      expect(html).toContain("is-edit");
      expect(html).toContain("风险门禁未通过，不能批准；请拒绝或修改后重新审核。");
      expect(html.match(/aria-expanded="false"/g)).toHaveLength(2);
      expect(html.match(/aria-controls="[^"]+"/g)).toHaveLength(2);
    });

    it("connects every available trigger to its two-stage panel", () => {
      const html = renderReview(reviewInterrupt({ riskAllowed: true }));
      const controlledIds = [...html.matchAll(/aria-controls="([^"]+)"/g)]
        .map((match) => match[1]);

      expect(html).toContain("is-approve");
      expect(controlledIds).toHaveLength(3);
      expect(new Set(controlledIds).size).toBe(2);
      expect(html.match(/aria-expanded="false"/g)).toHaveLength(3);
    });
  });

  describe("state announcements", () => {
    it("keeps the per-second pending countdown out of live regions", () => {
      expect(resolveReviewStateAnnouncement("pending")).toEqual({
        role: undefined,
        ariaLive: "off",
      });

      const badge = stateBadgeTag(renderReview(reviewInterrupt({ riskAllowed: true })));
      expect(badge).toContain('aria-live="off"');
      expect(badge).not.toContain('role="status"');
      expect(badge).not.toContain("aria-atomic");
    });

    it.each([
      "responding",
      "submitting",
      "accepted",
      "conflict",
      "expired",
      "network_error",
      "auth_error",
      "invalid_request",
    ] as const)("keeps %s available as a polite status announcement", (state) => {
      expect(resolveReviewStateAnnouncement(state)).toEqual({
        role: "status",
        ariaLive: "polite",
      });
    });

    it("renders a responding badge as an atomic polite status", () => {
      const interrupt = reviewInterrupt({ riskAllowed: true });
      interrupt.status = "responding";
      interrupt.response = { action: "approve", comment: null, edits: null };
      interrupt.responded_at = "2026-07-15T10:00:30Z";

      const badge = stateBadgeTag(renderReview(interrupt));
      expect(badge).toContain('role="status"');
      expect(badge).toContain('aria-live="polite"');
      expect(badge).toContain('aria-atomic="true"');
    });

    it("renders a controlled member decision without raw contract coordinates", () => {
      const html = renderReview(reviewInterrupt({ riskAllowed: true }), {
        decision: { action: "approve", comment: null, edits: null },
        deferSubmission: true,
        announceSubmissionState: false,
      });

      expect(html).toContain("已在本页选择批准，尚未提交到服务端");
      expect(html).not.toMatch(
        /(?:interrupt-review|response_version|pause_id|namespace|checkpoint_id)/,
      );
      expect(stateBadgeTag(html)).toContain('aria-live="off"');
    });

    it("gives every aggregate review control a unique business-facing name", () => {
      const interrupt = reviewInterrupt({ riskAllowed: true });
      const identity = reviewItemIdentity(interrupt, { index: 2, total: 3 });
      const html = renderReview(interrupt, {
        deferSubmission: true,
        reviewPosition: { index: 2, total: 3 },
      });

      expect(identity).toBe("审核项 2/3，BTC-USDT-SWAP，4h，第 1 轮");
      expect(html).toContain(`分析草稿待人工确认：${identity}`);
      expect(html).toContain(`aria-label="${identity}的审核决定"`);
      expect(html).toContain(`aria-label="${identity}：批准"`);
      expect(html).toContain(`aria-label="${identity}：拒绝"`);
      expect(html).toContain(`aria-label="${identity}：修改后重审"`);
      expect(html).not.toMatch(/(?:namespace|checkpoint_id|checkpoint_map|projection_id)/);
    });
  });

  describe("source reference safety", () => {
    it.each([
      ["https://example.com/review?q=btc#evidence", "https://example.com/review?q=btc#evidence"],
      ["http://example.com", "http://example.com/"],
    ])("allows an explicit HTTP(S) source %s", (reference, expectedHref) => {
      expect(resolveReviewSourceReference(reference)).toEqual({
        text: reference,
        href: expectedHref,
        issue: null,
      });
    });

    it.each([
      ["javascript:alert(1)", "unsupported"],
      ["data:text/html,unsafe", "unsupported"],
      ["ftp://example.com/file", "unsupported"],
      ["//example.com/protocol-relative", "invalid"],
      ["not a URL", "invalid"],
      ["https://user:secret@example.com/private", "invalid"],
    ] as const)("keeps unsafe source %s as non-clickable text", (reference, issue) => {
      expect(resolveReviewSourceReference(reference)).toEqual({
        text: reference,
        href: null,
        issue,
      });
    });

    it("renders only safe links and escapes invalid source text", () => {
      const html = renderReview(reviewInterrupt({
        riskAllowed: true,
        sources: [
          "https://example.com/evidence",
          "http://example.net/context",
          "javascript:alert(1)",
          "<img src=x onerror=alert(1)>",
          "https://user:secret@example.org/private",
        ],
      }));

      expect(html).toContain('href="https://example.com/evidence"');
      expect(html).toContain('href="http://example.net/context"');
      expect(html.match(/target="_blank"/g)).toHaveLength(2);
      expect(html.match(/rel="noopener noreferrer"/g)).toHaveLength(2);
      expect(html).not.toContain('href="javascript:');
      expect(html).not.toContain('href="https://user:secret@');
      expect(html).toContain("javascript:alert(1)");
      expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
      expect(html).toContain("非 HTTP(S) 来源");
      expect(html).toContain("无法解析的来源");
      expect(html).not.toContain('"source_references"');
    });
  });

  describe("deadline authority", () => {
    const now = Date.parse("2026-07-15T10:00:00Z");

    it("formats a future server deadline as a local countdown", () => {
      expect(resolveReviewDeadlineHint("2026-07-15T10:01:05Z", now)).toEqual({
        countdown: "01:05",
        locallyElapsed: false,
      });
      expect(resolveReviewDeadlineHint("2026-07-15T11:01:05Z", now)).toEqual({
        countdown: "01:01:05",
        locallyElapsed: false,
      });
    });

    it("marks local countdown completion without changing the interaction state", () => {
      expect(resolveReviewDeadlineHint("2026-07-15T09:59:59Z", now)).toEqual({
        countdown: "00:00",
        locallyElapsed: true,
      });
      expect(resolveReviewInteractionState({ status: "pending" }, "idle")).toBe("pending");
      expect(resolveReviewInteractionState({ status: "pending" }, "network_error")).toBe(
        "network_error",
      );
    });

    it("enters expired only after the server conflict has been classified as expiry", () => {
      expect(isServerExpiredReviewConflict(409, "Interrupt response window has expired.")).toBe(true);
      expect(isServerExpiredReviewConflict(409, "审核窗口已经过期。")).toBe(true);
      expect(isServerExpiredReviewConflict(409, "Interrupt response_version is stale.")).toBe(false);
      expect(isServerExpiredReviewConflict(503, "Interrupt response window has expired.")).toBe(false);
      expect(resolveReviewInteractionState({ status: "pending" }, "expired")).toBe("expired");
    });

    it("keeps responding projection state ahead of local submission phases", () => {
      expect(resolveReviewInteractionState({ status: "responding" }, "network_error")).toBe(
        "responding",
      );
    });
  });
});

function renderReview(
  interrupt: AnalysisPendingInterrupt,
  overrides: Partial<ComponentProps<typeof HumanReviewPanel>> = {},
) {
  return renderToStaticMarkup(createElement(HumanReviewPanel, {
    interrupt,
    expiresAt: "2026-07-15T10:05:00Z",
    onDecide: () => undefined,
    ...overrides,
  }));
}

function stateBadgeTag(html: string) {
  const match = html.match(/<span class="hitl-review-state"[^>]*>/);
  if (match === null) throw new Error("review state badge was not rendered");
  return match[0];
}

function reviewInterrupt({
  riskAllowed,
  sources = ["https://example.com/evidence"],
}: {
  riskAllowed: boolean;
  sources?: string[];
}): AnalysisPendingInterrupt {
  return {
    interrupt_id: "interrupt-review-1",
    response_version: 1,
    status: "pending",
    payload: {
      kind: "artifact_review",
      schema_version: "1.0",
      allowed_actions: ["approve", "reject", "edit"],
      review_iteration: 1,
      artifact: {
        artifact_type: "analysis_report",
        schema_version: "1.0",
        content_version: 1,
        status: "draft",
        analysis: {
          regime: "risk_on",
          factor_scores: { momentum: 2 },
          total_score: 2,
          main_action: "open_long",
          instrument: "BTC-USDT-SWAP",
          horizon: "4h",
          reference_price: 67250.5,
          entry_trigger: 67400,
          stop_price: 65800,
          target_1: 68800,
          target_2: 70100,
          probability: 0.68,
          position_size_class: "light",
          max_leverage: 2,
          risk_pct: 0.01,
          root_cause_chain: ["Momentum improved", "Event risk remains contained"],
          why_not_opposite: "Short momentum lacks confirmation.",
          invalidation: "A 4h close below 65800 invalidates the setup.",
          unavailable_data: [],
          manual_execution_required: true,
          expires_in_seconds: 14400,
        },
        evidence_verdict: {
          sufficient: riskAllowed,
          confidence_cap: riskAllowed ? 0.72 : 0,
          missing_required: riskAllowed ? [] : ["order_book"],
          missing_optional: [],
          warnings: [],
        },
        risk_verdict: {
          allowed: riskAllowed,
          blocked_reasons: riskAllowed ? [] : ["evidence.insufficient:order_book"],
          warnings: [],
          confidence_cap: riskAllowed ? 0.7 : 0,
        },
        source_references: sources,
      },
    },
    response: null,
    responded_at: null,
  };
}
