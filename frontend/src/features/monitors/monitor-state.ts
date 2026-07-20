import { MonitorApiError } from "@/lib/api/monitor-client";
import { stableFingerprint } from "@/lib/stable-fingerprint";
import {
  createMonitorRequestSchema,
  type CreateMonitorRequest,
  type MonitorCondition,
  type MonitorSchedule,
} from "@/lib/schemas/monitor-api";

export type MonitorSourceInput = {
  artifactId: string;
  artifactVersionId: string;
};

export type MonitorFormDraft = {
  name: string;
  runTaskType: "market_analysis" | "deep_research";
  condition: MonitorCondition;
  schedule: MonitorSchedule;
  timezone: string;
  expiresAtLocal: string;
  quietHours: { start: string; end: string } | null;
  destinationIds: string[];
};

type PreparedMonitorRequest =
  | { success: true; request: CreateMonitorRequest; fingerprint: string }
  | { success: false; message: string };

export function prepareMonitorRequest(
  source: MonitorSourceInput,
  draft: MonitorFormDraft,
): PreparedMonitorRequest {
  const expiresAt = new Date(draft.expiresAtLocal);
  if (!draft.expiresAtLocal || Number.isNaN(expiresAt.getTime())) {
    return { success: false, message: "请选择有效的结束时间。" };
  }
  if (expiresAt.getTime() <= Date.now()) {
    return { success: false, message: "有效期必须晚于当前时间。" };
  }

  const parsed = createMonitorRequestSchema.safeParse({
    name: draft.name,
    artifact_id: source.artifactId,
    artifact_version_id: source.artifactVersionId,
    run_task_type: draft.runTaskType,
    condition: draft.condition,
    schedule: draft.schedule,
    timezone: draft.timezone,
    expires_at: expiresAt.toISOString(),
    quiet_hours: draft.quietHours,
    destination_ids: draft.destinationIds,
  });
  if (!parsed.success) {
    return { success: false, message: "请检查名称、条件、频率和时间设置。" };
  }
  return {
    success: true,
    request: parsed.data,
    fingerprint: stableFingerprint(parsed.data),
  };
}

export function monitorErrorMessage(reason: unknown, fallback: string): string {
  if (!(reason instanceof MonitorApiError)) return fallback;
  if (reason.status === 401) return "登录状态已失效，请重新登录后再试。";
  if (reason.status === 403) return "当前工作区没有管理持续监控的权限。";
  if (reason.status === 409) return "监控已被其他操作更新，请刷新后重试。";
  if (reason.status === 422) return "提交内容未通过校验，请检查条件、时间与通知目标。";
  if (reason.status === 429) return "当前工作区的定时任务额度已用尽，请稍后再试或调整额度。";
  if (reason.status === 502) return "Monitor 服务返回了无效响应，请稍后重试。";
  if (reason.status === 503) return "Monitor 调度服务暂时不可用，请稍后重试。";
  return reason.message || fallback;
}

export function mutationIdentity(
  action: "create" | "pause" | "resume" | "trigger" | "delete",
  resource: unknown,
): string {
  return stableFingerprint([action, resource]);
}

export function idempotencyKeyFor(
  previous: { identity: string; key: string } | null,
  identity: string,
  createKey: () => string = () => crypto.randomUUID(),
): { identity: string; key: string } {
  return previous?.identity === identity
    ? previous
    : { identity, key: createKey() };
}
