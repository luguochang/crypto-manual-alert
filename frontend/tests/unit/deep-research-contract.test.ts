import { describe, expect, it } from "vitest";

import {
  deepResearchArtifactSchema,
  deepResearchReviewPayloadSchema,
  deepResearchSubmissionSchema,
  interruptResponseSchema,
  pendingInterruptSchema,
  productTaskSchema,
  validateInterruptResponseForPayload,
} from "@/lib/schemas/product-api";

const source = {
  query: "BTC institutional adoption",
  final_url: "https://example.com/verified-research-source",
  redirect_chain: [],
  http_status: 200,
  fetched_at: "2026-07-19T12:00:00Z",
  published_at: null,
  content_hash: "c".repeat(64),
  parser_version: "test-v1",
  title: "Verified research source",
  author: null,
  source: "test_search",
  excerpt: "A provider-verified source excerpt.",
  evidence_relation: "supports",
};

const artifact = {
  artifact_type: "deep_research_report" as const,
  schema_version: "1.0" as const,
  status: "committed" as const,
  harness_mode: "deepagents" as const,
  search_coverage: {
    status: "complete" as const,
    attempted_queries: 1,
    successful_queries: 1,
    failed_queries: [],
  },
  report: {
    executive_summary: "BTC 机构采用仍在推进。",
    sections: [
      {
        title: "机构采用",
        summary: "可验证来源支持该趋势。",
        findings: [
          {
            claim: "机构采用仍在推进。",
            source_indexes: [1],
          },
        ],
      },
    ],
    risk_notes: [],
    evidence_gaps: [],
  },
  sources: [{ index: 1, evidence: source }],
  model_audits: [],
};

describe("deep research Product contract", () => {
  it("validates submission and a typed succeeded Task", () => {
    expect(deepResearchSubmissionSchema.parse({
      symbol: "BTC-USDT-SWAP",
      horizon: "7d",
      query_text: "研究 BTC 机构采用趋势和主要反证。",
    }).task_type).toBe("deep_research");

    const task = productTaskSchema.parse({
      task_id: "11111111-1111-4111-8111-111111111111",
      task_type: "deep_research",
      correlation_id: "22222222-2222-4222-8222-222222222222",
      status: "succeeded",
      symbol: "BTC-USDT-SWAP",
      horizon: "7d",
      query_text: "研究 BTC 机构采用趋势和主要反证。",
      created_at: "2026-07-19T12:00:00Z",
      completed_at: "2026-07-19T12:05:00Z",
      cancel_requested_at: null,
      artifact: null,
      deep_research_artifact: artifact,
      errors: [],
      market_snapshot: null,
      web_evidence: [source],
      pending_interrupts: null,
    });

    expect(task.deep_research_artifact?.report.sections[0]?.findings[0]
      ?.source_indexes).toEqual([1]);
  });

  it.each(["draft", "committed"] as const)(
    "accepts a typed %s research artifact while rejecting non-lifecycle states",
    (status) => {
      expect(deepResearchArtifactSchema.parse({ ...artifact, status }).status).toBe(status);
    },
  );

  it("requires a scoped draft in the research review payload", () => {
    const payload = deepResearchReviewPayload();

    expect(deepResearchReviewPayloadSchema.parse(payload)).toMatchObject({
      kind: "deep_research_review",
      symbol: "BTC-USDT-SWAP",
      horizon: "7d",
      review_iteration: 2,
      artifact: { status: "draft" },
    });
    expect(() => deepResearchReviewPayloadSchema.parse({
      ...payload,
      artifact: { ...payload.artifact, status: "committed" },
    })).toThrow();
    expect(() => deepResearchArtifactSchema.parse({ ...artifact, status: "failed" })).toThrow();
  });

  it("accepts only a complete report replacement for research edits", () => {
    const payload = deepResearchReviewPayload();
    const editedReport = {
      ...payload.artifact.report,
      executive_summary: "人工复核后收窄了结论范围。",
    };
    const response = validateInterruptResponseForPayload(payload, {
      action: "edit",
      comment: "收窄结论",
      edits: { report: editedReport },
    });

    expect(response).toEqual({
      action: "edit",
      comment: "收窄结论",
      edits: { report: editedReport },
    });
    expect(() => validateInterruptResponseForPayload(payload, {
      action: "edit",
      edits: { main_action: "no_trade" },
    })).toThrow();
    expect(() => interruptResponseSchema.parse({
      action: "edit",
      edits: {
        report: editedReport,
        sources: [],
      },
    })).toThrow();
    expect(() => validateInterruptResponseForPayload(payload, {
      action: "edit",
      edits: { report: payload.artifact.report },
    })).toThrow("Deep research edits must change the report");
  });

  it("revalidates edited citations against the server-owned source catalog", () => {
    const payload = deepResearchReviewPayload();
    const report = structuredClone(payload.artifact.report);
    report.sections[0]!.findings[0]!.source_indexes = [2];

    expect(() => validateInterruptResponseForPayload(payload, {
      action: "edit",
      edits: { report },
    })).toThrow();
  });

  it("pairs persisted responses with their payload kind", () => {
    const payload = deepResearchReviewPayload();
    const editedReport = {
      ...payload.artifact.report,
      executive_summary: "持久化的人工修订结论。",
    };
    const base = {
      interrupt_id: "research-review-1",
      response_version: 1,
      status: "responding" as const,
      payload,
      responded_at: "2026-07-19T12:04:00Z",
    };

    expect(pendingInterruptSchema.parse({
      ...base,
      response: { action: "edit", edits: { report: editedReport } },
    }).response).toMatchObject({ action: "edit" });
    expect(() => pendingInterruptSchema.parse({
      ...base,
      response: { action: "edit", edits: { main_action: "no_trade" } },
    })).toThrow();
  });

  it("validates waiting research Task scope and accepts the 4000-character query boundary", () => {
    const payload = deepResearchReviewPayload();
    const task = waitingResearchTask(payload, "x".repeat(4000));

    expect(productTaskSchema.parse(task).pending_interrupts?.members[0]?.payload.kind)
      .toBe("deep_research_review");
    expect(() => productTaskSchema.parse({
      ...task,
      task_type: "market_analysis",
    })).toThrow();
    expect(() => productTaskSchema.parse({
      ...task,
      symbol: "ETH-USDT-SWAP",
    })).toThrow();
    expect(() => productTaskSchema.parse({
      ...task,
      query_text: "x".repeat(4001),
    })).toThrow();
  });

  it.each([[[0]], [[9]], [[1, 1]], [[2]]])(
    "rejects invalid citation indexes %j",
    (sourceIndexes) => {
      expect(() => deepResearchArtifactSchema.parse({
        ...artifact,
        report: {
          ...artifact.report,
          sections: [
            {
              ...artifact.report.sections[0],
              findings: [{
                claim: "Invalid citation.",
                source_indexes: sourceIndexes,
              }],
            },
          ],
        },
      })).toThrow();
    },
  );
});

function deepResearchReviewPayload() {
  return deepResearchReviewPayloadSchema.parse({
    kind: "deep_research_review" as const,
    schema_version: "1.0" as const,
    allowed_actions: ["approve", "reject", "edit"],
    symbol: "BTC-USDT-SWAP" as const,
    horizon: "7d",
    review_iteration: 2,
    artifact: {
      ...structuredClone(artifact),
      status: "draft" as const,
    },
  });
}

function waitingResearchTask(
  payload: ReturnType<typeof deepResearchReviewPayload>,
  queryText: string,
) {
  return {
    task_id: "11111111-1111-4111-8111-111111111111",
    task_type: "deep_research" as const,
    correlation_id: "22222222-2222-4222-8222-222222222222",
    status: "waiting_human" as const,
    symbol: "BTC-USDT-SWAP" as const,
    horizon: "7d",
    query_text: queryText,
    created_at: "2026-07-19T12:00:00Z",
    completed_at: null,
    cancel_requested_at: null,
    artifact: null,
    deep_research_artifact: null,
    errors: [],
    market_snapshot: null,
    web_evidence: [source],
    pending_interrupts: {
      pause_id: "33333333-3333-4333-8333-333333333333",
      pause_version: 1,
      status: "pending" as const,
      expires_at: "2026-07-19T12:10:00Z",
      members: [{
        interrupt_id: "research-review-1",
        response_version: 1,
        status: "pending" as const,
        payload,
        response: null,
        responded_at: null,
      }],
    },
  };
}
