import { z } from "zod";

import type { OfficialProgressItem } from "./official-run-stream";

const eventIdentitySchema = z.object({
  schema_version: z.literal("1.0"),
  event_id: z.string().regex(/^[0-9a-f]{64}$/),
  sequence: z.number().int().positive(),
  correlation_id: z.string().trim().min(1).max(255),
  task_id: z.string().trim().min(1).max(255),
  run_id: z.string().trim().min(1).max(255),
  thread_id: z.string().trim().min(1).max(255),
  request_id: z.string().trim().min(1).max(255),
}).strict();

const taskProgressEventSchema = eventIdentitySchema.extend({
  name: z.literal("task_progress"),
  phase: z.string().regex(/^[a-z0-9_]+$/).max(64),
  status: z.enum(["active", "complete", "blocked", "failed"]),
}).strict();

const artifactEventSchema = eventIdentitySchema.extend({
  name: z.literal("artifact"),
  status: z.enum(["draft", "committed"]),
  content_version: z.number().int().positive(),
}).strict();

const evidenceEventSchema = eventIdentitySchema.extend({
  name: z.literal("evidence"),
  stage: z.enum(["collected", "validated"]),
  verified_source_count: z.number().int().min(0).max(1000),
  sufficient: z.boolean().nullable().optional().default(null),
}).strict();

const usageEventSchema = eventIdentitySchema.extend({
  name: z.literal("usage"),
  model_call_count: z.number().int().min(0).max(1000),
  input_tokens: z.number().int().nonnegative().nullable().optional().default(null),
  output_tokens: z.number().int().nonnegative().nullable().optional().default(null),
  total_tokens: z.number().int().nonnegative().nullable().optional().default(null),
  prompt_versions: z.array(z.string().trim().min(1).max(255)).max(16).default([]),
}).strict();

const notificationEventSchema = eventIdentitySchema.extend({
  name: z.literal("notification"),
  status: z.enum(["requested", "not_requested"]),
}).strict();

const qualityEventSchema = eventIdentitySchema.extend({
  name: z.literal("quality"),
  evidence_sufficient: z.boolean(),
  risk_allowed: z.boolean(),
  warning_count: z.number().int().min(0).max(1000),
  blocked_reason_count: z.number().int().min(0).max(1000),
}).strict();

export const productCustomEventSchema = z.discriminatedUnion("name", [
  taskProgressEventSchema,
  artifactEventSchema,
  evidenceEventSchema,
  usageEventSchema,
  notificationEventSchema,
  qualityEventSchema,
]);

export type ProductCustomEvent = z.infer<typeof productCustomEventSchema>;

export const productCustomChannels = [
  "custom:task_progress",
  "custom:artifact",
  "custom:evidence",
  "custom:usage",
  "custom:notification",
  "custom:quality",
] as const;

const phaseProjection: Record<string, OfficialProgressItem> = {
  request_validated: { id: "lifecycle", label: "执行阶段", detail: "分析请求已校验", tone: "active" },
  market_collection: { id: "market_snapshot", label: "市场快照", detail: "市场数据获取失败", tone: "danger" },
  market_collected: { id: "market_snapshot", label: "市场快照", detail: "市场数据已获取", tone: "complete" },
  research_collection: { id: "web_evidence", label: "Web 证据", detail: "Web 研究未完成", tone: "danger" },
  research_collected: { id: "web_evidence", label: "Web 证据", detail: "Web 研究已完成", tone: "complete" },
  analysis: { id: "analysis", label: "分析判断", detail: "分析推演未完成", tone: "danger" },
  analysis_completed: { id: "analysis", label: "分析判断", detail: "分析推演已完成", tone: "complete" },
  evidence_validated: { id: "evidence_verdict", label: "证据门禁", detail: "证据门禁已完成", tone: "complete" },
  risk_validated: { id: "risk_verdict", label: "风险门禁", detail: "风险门禁已完成", tone: "complete" },
  artifact_built: { id: "artifact", label: "分析报告", detail: "分析报告草稿已生成", tone: "active" },
  artifact_committed: { id: "artifact", label: "分析报告", detail: "分析报告已提交", tone: "complete" },
  completed: { id: "run", label: "执行阶段", detail: "官方执行已完成", tone: "complete" },
  completed_blocked: { id: "run", label: "执行阶段", detail: "官方执行已被门禁阻断", tone: "warning" },
  completed_rejected: { id: "run", label: "执行阶段", detail: "人工审核已拒绝本次结果", tone: "warning" },
  completed_failed: { id: "run", label: "执行阶段", detail: "官方执行未完成", tone: "danger" },
};

export function parseProductCustomEvents(
  events: readonly unknown[],
  expectedRunId?: string | null,
): ProductCustomEvent[] {
  const byEventId = new Map<string, ProductCustomEvent>();
  for (const candidate of events) {
    const payload = customPayload(candidate);
    const parsed = productCustomEventSchema.safeParse(payload);
    if (!parsed.success) continue;
    if (expectedRunId && parsed.data.run_id !== expectedRunId) continue;
    byEventId.set(parsed.data.event_id, parsed.data);
  }
  return [...byEventId.values()].sort((left, right) => left.sequence - right.sequence);
}

export function projectProductCustomEvents(
  events: readonly unknown[],
  expectedRunId?: string | null,
): OfficialProgressItem[] {
  const latest = new Map<OfficialProgressItem["id"], OfficialProgressItem>();
  for (const event of parseProductCustomEvents(events, expectedRunId)) {
    const item = projectEvent(event);
    latest.set(item.id, item);
  }
  return [...latest.values()];
}

function customPayload(candidate: unknown): unknown {
  if (!isRecord(candidate) || candidate.method !== "custom") return candidate;
  const params = isRecord(candidate.params) ? candidate.params : null;
  return params?.data;
}

function projectEvent(event: ProductCustomEvent): OfficialProgressItem {
  if (event.name === "task_progress") {
    const known = phaseProjection[event.phase];
    if (known) return {
      ...known,
      tone: event.status === "failed"
        ? "danger"
        : event.status === "blocked"
          ? "warning"
          : event.status === "complete"
            ? "complete"
            : "active",
    };
    return {
      id: "lifecycle",
      label: "执行阶段",
      detail: "执行状态已更新",
      tone: event.status === "failed"
        ? "danger"
        : event.status === "blocked"
          ? "warning"
          : event.status === "complete"
            ? "complete"
            : "active",
    };
  }
  if (event.name === "artifact") return {
    id: "artifact",
    label: "分析报告",
    detail: event.status === "committed"
      ? `第 ${event.content_version} 版报告已提交`
      : `第 ${event.content_version} 版报告草稿已生成`,
    tone: event.status === "committed" ? "complete" : "active",
  };
  if (event.name === "evidence") return {
    id: event.stage === "validated" ? "evidence_verdict" : "web_evidence",
    label: event.stage === "validated" ? "证据门禁" : "Web 证据",
    detail: event.stage === "validated"
      ? event.sufficient
        ? `证据门禁通过 · ${event.verified_source_count} 条可验证来源`
        : `证据不足 · ${event.verified_source_count} 条可验证来源`
      : `已汇总 ${event.verified_source_count} 条可验证来源`,
    tone: event.stage === "validated" && !event.sufficient ? "warning" : "complete",
  };
  if (event.name === "usage") return {
    id: "usage",
    label: "模型用量",
    detail: event.total_tokens === null
      ? `已完成 ${event.model_call_count} 次模型调用`
      : `${event.model_call_count} 次模型调用 · ${event.total_tokens.toLocaleString("zh-CN")} tokens`,
    tone: "complete",
  };
  if (event.name === "notification") return {
    id: "notification",
    label: "通知发送",
    detail: event.status === "requested" ? "本次任务已请求完成通知" : "本次任务未请求通知",
    tone: event.status === "requested" ? "active" : "complete",
  };
  return {
    id: "quality",
    label: "质量门禁",
    detail: event.risk_allowed
      ? event.warning_count > 0
        ? `门禁通过 · ${event.warning_count} 条风险提示`
        : "证据与风险门禁通过"
      : event.blocked_reason_count > 0
        ? `门禁阻断 · ${event.blocked_reason_count} 项原因`
        : "风险门禁阻断",
    tone: event.risk_allowed && event.evidence_sufficient ? "complete" : "warning",
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
