"use client";

import { useChannel, useStream } from "@langchain/react";
import { Activity, CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";

import type {
  AgentStreamBinding,
  TaskStage,
  TaskStageHistory,
} from "@/lib/schemas/product-api";
import {
  productCustomChannels,
  projectProductCustomEvents,
} from "@/features/agent-runtime/product-custom-events";

interface OfficialRunStreamProps {
  binding: AgentStreamBinding;
  stageHistory?: TaskStageHistory | null;
}

interface DurableRunProgressProps {
  history: TaskStageHistory;
  historical?: boolean;
}

interface OfficialExecutionValues extends Record<string, unknown> {
  lifecycle?: unknown;
  market_snapshot?: unknown;
  web_evidence?: unknown;
  analysis?: unknown;
  evidence_verdict?: unknown;
  risk_verdict?: unknown;
}

export interface OfficialProgressItem {
  id: "lifecycle" | "usage" | "quality" | TaskStage["stage"];
  label: string;
  detail: string;
  tone: "active" | "complete" | "warning" | "danger";
}

const progressOrder: readonly OfficialProgressItem["id"][] = [
  "lifecycle",
  "market_snapshot",
  "web_evidence",
  "analysis",
  "usage",
  "evidence_verdict",
  "risk_verdict",
  "quality",
  "artifact",
  "notification",
  "run",
];

const stageLabels: Record<TaskStage["stage"], string> = {
  market_snapshot: "市场快照",
  web_evidence: "Web 证据",
  analysis: "分析判断",
  evidence_verdict: "证据门禁",
  risk_verdict: "风险门禁",
  artifact: "分析报告",
  notification: "通知发送",
  run: "执行阶段",
};

const terminalLifecyclePresentation: Record<string, { label: string; subtitle: string }> = {
  completed: {
    label: "执行已完成",
    subtitle: "本次官方执行已完成，最终状态已同步。",
  },
  completed_blocked: {
    label: "执行已阻断",
    subtitle: "本次官方执行已被门禁阻断，最终状态已同步。",
  },
  completed_failed: {
    label: "执行失败",
    subtitle: "本次官方执行失败，最终状态已同步。",
  },
};

export function officialAgentApiUrl(origin: string): string {
  const baseUrl = new URL(origin);
  if (baseUrl.protocol !== "http:" && baseUrl.protocol !== "https:") {
    throw new Error("Official Agent BFF requires an HTTP origin");
  }
  return new URL("/api/agent", baseUrl).toString();
}

export function officialConnectionStatus(
  isThreadLoading: boolean,
  error: unknown,
  lifecycle?: unknown,
): { label: string; tone: "active" | "connected" | "warning" } {
  if (error) return { label: "连接已中断", tone: "warning" };
  if (isThreadLoading) return { label: "正在连接", tone: "active" };
  const terminal = terminalLifecycle(lifecycle);
  if (terminal) return { label: terminal.label, tone: "connected" };
  return { label: "实时同步中", tone: "connected" };
}

export function officialStreamSubtitle(
  isThreadLoading: boolean,
  error: unknown,
  lifecycle?: unknown,
): string {
  if (error) return "实时执行连接已中断，产品状态仍会继续更新。";
  if (isThreadLoading) return "正在连接官方执行流。";
  return terminalLifecycle(lifecycle)?.subtitle ?? "正在同步本次分析的最新执行状态。";
}

const lifecycleProjection: Record<string, OfficialProgressItem> = {
  request_validated: { id: "lifecycle", label: "执行阶段", detail: "分析请求已校验", tone: "active" },
  market_collected: { id: "market_snapshot", label: "市场快照", detail: "市场快照已获取", tone: "active" },
  research_collected: { id: "web_evidence", label: "Web 证据", detail: "Web 证据已汇总", tone: "active" },
  analysis_completed: { id: "analysis", label: "分析判断", detail: "分析推演已完成", tone: "active" },
  evidence_validated: { id: "evidence_verdict", label: "证据门禁", detail: "证据门禁已完成", tone: "active" },
  risk_validated: { id: "risk_verdict", label: "风险门禁", detail: "风险门禁已完成", tone: "active" },
  artifact_built: { id: "artifact", label: "分析报告", detail: "分析报告正在提交", tone: "active" },
  completed: { id: "run", label: "执行阶段", detail: "官方执行已完成", tone: "complete" },
  completed_blocked: { id: "run", label: "执行阶段", detail: "官方执行已被门禁阻断", tone: "warning" },
  completed_failed: { id: "run", label: "执行阶段", detail: "官方执行未完成", tone: "danger" },
};

const actionLabels: Record<string, string> = {
  open_long: "偏向开多",
  open_short: "偏向开空",
  hold_long: "继续持有多头",
  hold_short: "继续持有空头",
  close_long: "考虑平多",
  close_short: "考虑平空",
  flip_long_to_short: "由多转空",
  flip_short_to_long: "由空转多",
  trigger_long: "等待多头触发",
  trigger_short: "等待空头触发",
  no_trade: "暂不操作",
};

export function projectOfficialValues(values: OfficialExecutionValues): OfficialProgressItem[] {
  const {
    lifecycle,
    market_snapshot: marketSnapshot,
    web_evidence: webEvidence,
    analysis,
    evidence_verdict: evidenceVerdict,
    risk_verdict: riskVerdict,
  } = values;
  const projection: OfficialProgressItem[] = [];

  if (typeof lifecycle === "string") {
    projection.push(lifecycleProjection[lifecycle] ?? {
      id: "lifecycle",
      label: "执行阶段",
      detail: "执行状态已更新",
      tone: "active",
    });
  }

  if (isRecord(marketSnapshot)) {
    const symbol = typeof marketSnapshot.symbol === "string"
      ? marketSnapshot.symbol
      : null;
    const price = finiteNumber(marketSnapshot.mark_price)
      ?? (isRecord(marketSnapshot.ticker) ? finiteNumber(marketSnapshot.ticker.last) : null);
    if (symbol || price !== null) {
      const detail = symbol && price !== null
        ? `${symbol} · 标记价格 ${formatPrice(price)}`
        : symbol
          ? `${symbol} · 行情数据已获取`
          : `标记价格 ${formatPrice(price ?? 0)}`;
      projection.push({
        id: "market_snapshot",
        label: "市场快照",
        detail,
        tone: "complete",
      });
    }
  }

  if (Array.isArray(webEvidence)) {
    projection.push({
      id: "web_evidence",
      label: "Web 证据",
      detail: webEvidence.length > 0
        ? `已汇总 ${webEvidence.length} 条来源`
        : "暂未汇总到可用来源",
      tone: webEvidence.length > 0 ? "complete" : "warning",
    });
  }

  if (isRecord(analysis)) {
    const action = typeof analysis.main_action === "string"
      ? actionLabels[analysis.main_action]
      : undefined;
    const probability = ratio(analysis.probability);
    const detail = [
      action,
      probability === null ? undefined : `置信度 ${formatPercentage(probability)}`,
    ].filter((part): part is string => Boolean(part)).join(" · ");
    if (detail) {
      projection.push({
        id: "analysis",
        label: "分析判断",
        detail,
        tone: "complete",
      });
    }
  }

  if (isRecord(evidenceVerdict) && typeof evidenceVerdict.sufficient === "boolean") {
    const confidenceCap = ratio(evidenceVerdict.confidence_cap);
    const missingCount = Array.isArray(evidenceVerdict.missing_required)
      ? evidenceVerdict.missing_required.length
      : 0;
    const detail = evidenceVerdict.sufficient
      ? [
          "证据充分",
          confidenceCap === null ? undefined : `置信度上限 ${formatPercentage(confidenceCap)}`,
        ].filter((part): part is string => Boolean(part)).join(" · ")
      : missingCount > 0
        ? `证据不足 · 缺少 ${missingCount} 项必要数据`
        : "证据不足";
    projection.push({
      id: "evidence_verdict",
      label: "证据门禁",
      detail,
      tone: evidenceVerdict.sufficient ? "complete" : "warning",
    });
  }

  if (isRecord(riskVerdict) && typeof riskVerdict.allowed === "boolean") {
    const warningCount = Array.isArray(riskVerdict.warnings)
      ? riskVerdict.warnings.length
      : 0;
    const blockedCount = Array.isArray(riskVerdict.blocked_reasons)
      ? riskVerdict.blocked_reasons.length
      : 0;
    const detail = riskVerdict.allowed
      ? warningCount > 0
        ? `允许进入人工决策 · ${warningCount} 条风险提示`
        : "允许进入人工决策"
      : blockedCount > 0
        ? `风险门禁阻断 · ${blockedCount} 项原因`
        : "风险门禁阻断";
    projection.push({
      id: "risk_verdict",
      label: "风险门禁",
      detail,
      tone: riskVerdict.allowed ? "complete" : "danger",
    });
  }

  return orderLatestProgress(projection);
}

export function mergeExecutionProgress(
  stageHistory: TaskStageHistory | null | undefined,
  liveProgress: readonly OfficialProgressItem[],
): OfficialProgressItem[] {
  const latestDurableStages = latestDurableStagesByName(stageHistory);
  const merged = new Map<OfficialProgressItem["id"], OfficialProgressItem>();

  for (const item of projectDurableStageHistory(latestDurableStages)) {
    merged.set(item.id, item);
  }
  for (const item of liveProgress) {
    const durableStage = isDurableStageName(item.id)
      ? latestDurableStages.get(item.id)
      : undefined;
    const durableItem = merged.get(item.id);
    if (
      durableStage !== undefined
      && durableItem !== undefined
      && durableStage.status !== "planned"
      && item.tone !== durableItem.tone
    ) {
      continue;
    }
    merged.set(item.id, item);
  }
  return orderLatestProgress([...merged.values()]);
}

function isDurableStageName(
  value: OfficialProgressItem["id"],
): value is TaskStage["stage"] {
  return value in stageLabels;
}

function latestDurableStagesByName(
  history: TaskStageHistory | null | undefined,
): Map<TaskStage["stage"], TaskStage> {
  const latest = new Map<TaskStage["stage"], TaskStage>();
  for (const stage of history?.stages ?? []) {
    const current = latest.get(stage.stage);
    if (current === undefined || stage.sequence > current.sequence) {
      latest.set(stage.stage, stage);
    }
  }
  return latest;
}

function projectDurableStageHistory(
  latestStages: ReadonlyMap<TaskStage["stage"], TaskStage>,
): OfficialProgressItem[] {
  return orderLatestProgress([...latestStages.values()].map((stage) => ({
    id: stage.stage,
    label: stageLabels[stage.stage],
    detail: durableStageDetail(stage),
    tone: durableStageTone(stage.status),
  })));
}

function durableStageDetail(stage: TaskStage): string {
  if (stage.stage === "run") {
    return {
      committed: "执行状态已保存",
      planned: "执行已进入计划",
      succeeded: "执行已完成",
      blocked: "执行已阻断",
      failed: "执行失败",
      cancelled: "执行已取消",
    }[stage.status];
  }
  if (stage.stage === "notification" && stage.status === "planned") {
    return "通知已进入发送队列";
  }
  const label = stageLabels[stage.stage];
  return {
    committed: `${label}已保存`,
    planned: `${label}已进入计划`,
    succeeded: `${label}已完成`,
    blocked: `${label}已阻断`,
    failed: `${label}失败`,
    cancelled: `${label}已取消`,
  }[stage.status];
}

function durableStageTone(status: TaskStage["status"]): OfficialProgressItem["tone"] {
  if (status === "committed" || status === "succeeded") return "complete";
  if (status === "planned") return "active";
  if (status === "blocked") return "warning";
  return "danger";
}

function orderLatestProgress(
  progress: readonly OfficialProgressItem[],
): OfficialProgressItem[] {
  const latest = new Map<OfficialProgressItem["id"], OfficialProgressItem>();
  for (const item of progress) latest.set(item.id, item);
  return progressOrder.flatMap((id) => {
    const item = latest.get(id);
    return item === undefined ? [] : [item];
  });
}

export function OfficialRunStream({ binding, stageHistory = null }: OfficialRunStreamProps) {
  const { assistant_id: assistantId, thread_id: threadId } = binding;
  const stream = useStream<OfficialExecutionValues>({
    assistantId,
    threadId,
    apiUrl: officialAgentApiUrl(window.location.origin),
    transport: "sse",
    optimistic: false,
  });
  const customEvents = useChannel(stream, productCustomChannels, undefined, {
    bufferSize: 256,
    replay: true,
  });
  const progress = mergeExecutionProgress(
    stageHistory,
    [
      ...projectOfficialValues(stream.values),
      ...projectProductCustomEvents(customEvents, stageHistory?.run_id),
    ],
  );
  const connectionStatus = officialConnectionStatus(
    stream.isThreadLoading,
    stream.error,
    stream.values.lifecycle,
  );
  const subtitle = officialStreamSubtitle(
    stream.isThreadLoading,
    stream.error,
    stream.values.lifecycle,
  );
  const subagents = Array.from(stream.subagents.values())
    .filter((subagent) => subagent.name === "verified-source-researcher")
    .map((subagent) => ({
      id: subagent.id,
      status: subagent.status,
    }));

  return <ExecutionProgressPanel
    testId="official-run-stream"
    title="官方执行进度"
    subtitle={subtitle}
    status={connectionStatus}
    progress={progress}
    subagents={subagents}
    streamInterrupted={Boolean(stream.error)}
    emptyMessage="正在等待官方执行事件。"
  />;
}

export function DurableRunProgress({
  history,
  historical = false,
}: DurableRunProgressProps) {
  return <ExecutionProgressPanel
    testId="durable-run-progress"
    title={historical ? "历史运行进度" : "执行进度"}
    subtitle={historical
      ? "所选运行的已保存执行阶段。"
      : "本次执行的已保存阶段。"}
    status={{ label: "已保存", tone: "connected" }}
    progress={mergeExecutionProgress(history, [])}
    subagents={[]}
    streamInterrupted={false}
    emptyMessage="暂未保存执行阶段。"
  />;
}

interface ExecutionProgressPanelProps {
  testId: "official-run-stream" | "durable-run-progress";
  title: string;
  subtitle: string;
  status: { label: string; tone: "active" | "connected" | "warning" };
  progress: readonly OfficialProgressItem[];
  subagents: readonly {
    id: string;
    status: "running" | "complete" | "error";
  }[];
  streamInterrupted: boolean;
  emptyMessage: string;
}

function ExecutionProgressPanel({
  testId,
  title,
  subtitle,
  status,
  progress,
  subagents,
  streamInterrupted,
  emptyMessage,
}: ExecutionProgressPanelProps) {
  return (
    <section className="official-run-stream" data-testid={testId} aria-live="polite">
      <div className="official-stream-heading">
        <div>
          <span className="official-stream-icon" aria-hidden="true"><Activity size={18} /></span>
          <div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
        </div>
        <span className="official-stream-status" data-tone={status.tone}>
          {status.tone === "active" ? <LoaderCircle className="spinning-icon" size={15} aria-hidden="true" /> : null}
          {status.tone === "warning" ? <CircleAlert size={15} aria-hidden="true" /> : null}
          {status.label}
        </span>
      </div>

      {streamInterrupted ? (
        <div className="official-stream-notice" role="status">
          <CircleAlert size={17} aria-hidden="true" />
          <span>实时执行连接暂时中断；产品状态仍会继续更新。</span>
        </div>
      ) : null}

      {progress.length > 0 ? (
        <ol className="official-progress-list">
          {progress.map((item) => (
            <li key={item.id} data-tone={item.tone}>
              <span className="official-progress-marker" aria-hidden="true">
                {item.tone === "active"
                  ? <LoaderCircle className="spinning-icon" size={16} />
                  : item.tone === "danger" || item.tone === "warning"
                    ? <CircleAlert size={16} />
                    : <CircleCheck size={16} />}
              </span>
              <span>
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="official-stream-empty">{emptyMessage}</p>
      )}

      {subagents.length > 0 ? (
        <div className="official-subagent-section" aria-label="研究子任务">
          <h3>来源研究</h3>
          <ul>
            {subagents.map((subagent) => (
              <li key={subagent.id} data-status={subagent.status}>
                <span aria-hidden="true">
                  {subagent.status === "running"
                    ? <LoaderCircle className="spinning-icon" size={15} />
                    : subagent.status === "complete"
                      ? <CircleCheck size={15} />
                      : <CircleAlert size={15} />}
                </span>
                <strong>可验证来源研究员</strong>
                <small>{subagentStatusLabel(subagent.status)}</small>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function subagentStatusLabel(status: "running" | "complete" | "error") {
  return {
    running: "正在核验来源",
    complete: "来源核验完成",
    error: "来源核验失败",
  }[status];
}

function terminalLifecycle(lifecycle: unknown) {
  return typeof lifecycle === "string"
    ? terminalLifecyclePresentation[lifecycle]
    : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown): number | null {
  const parsed = typeof value === "number"
    ? value
    : typeof value === "string" && value.trim()
      ? Number(value)
      : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

function ratio(value: unknown): number | null {
  const parsed = finiteNumber(value);
  return parsed !== null && parsed >= 0 && parsed <= 1 ? parsed : null;
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercentage(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value);
}
