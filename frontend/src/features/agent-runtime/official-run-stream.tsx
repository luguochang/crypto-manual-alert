"use client";

import { useStream } from "@langchain/react";
import { Activity, CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";

import type { AgentStreamBinding } from "@/lib/schemas/product-api";

interface OfficialRunStreamProps {
  binding: AgentStreamBinding;
  onCompleted: () => void;
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
  id: "lifecycle" | "market_snapshot" | "web_evidence" | "analysis" | "evidence_verdict" | "risk_verdict";
  label: string;
  detail: string;
  tone: "active" | "complete" | "warning" | "danger";
}

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

const lifecycleProjection: Record<string, Pick<OfficialProgressItem, "detail" | "tone">> = {
  request_validated: { detail: "分析请求已校验", tone: "active" },
  market_collected: { detail: "市场快照已获取", tone: "active" },
  research_collected: { detail: "Web 证据已汇总", tone: "active" },
  analysis_completed: { detail: "分析推演已完成", tone: "active" },
  evidence_validated: { detail: "证据门禁已完成", tone: "active" },
  risk_validated: { detail: "风险门禁已完成", tone: "active" },
  artifact_built: { detail: "分析报告正在提交", tone: "active" },
  completed: { detail: "官方执行已完成", tone: "complete" },
  completed_blocked: { detail: "官方执行已被门禁阻断", tone: "warning" },
  completed_failed: { detail: "官方执行未完成", tone: "danger" },
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
    const mapped = lifecycleProjection[lifecycle]
      ?? { detail: "执行状态已更新", tone: "active" as const };
    projection.push({ id: "lifecycle", label: "执行阶段", ...mapped });
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

  return projection;
}

export function OfficialRunStream({ binding, onCompleted }: OfficialRunStreamProps) {
  const { assistant_id: assistantId, thread_id: threadId } = binding;
  const stream = useStream<OfficialExecutionValues>({
    assistantId,
    threadId,
    apiUrl: officialAgentApiUrl(window.location.origin),
    transport: "sse",
    optimistic: false,
    onCompleted,
  });
  const progress = projectOfficialValues(stream.values);
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

  return (
    <section className="official-run-stream" data-testid="official-run-stream" aria-live="polite">
      <div className="official-stream-heading">
        <div>
          <span className="official-stream-icon" aria-hidden="true"><Activity size={18} /></span>
          <div>
            <h2>官方执行进度</h2>
            <p>{subtitle}</p>
          </div>
        </div>
        <span className="official-stream-status" data-tone={connectionStatus.tone}>
          {connectionStatus.tone === "active" ? <LoaderCircle className="spinning-icon" size={15} aria-hidden="true" /> : null}
          {connectionStatus.tone === "warning" ? <CircleAlert size={15} aria-hidden="true" /> : null}
          {connectionStatus.label}
        </span>
      </div>

      {stream.error ? (
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
        <p className="official-stream-empty">正在等待官方执行事件。</p>
      )}
    </section>
  );
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
