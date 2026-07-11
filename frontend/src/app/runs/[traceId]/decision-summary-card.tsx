import {
  DIRECTION_LABEL,
  DIRECTION_TONE,
  classifyDirection,
  formatPercent,
  formatPrice
} from "@/app/shared/direction";
import {
  productDecisionLabel,
  productDisplayItems,
  productDisplayText,
  productEnumLabel
} from "@/app/shared/product-copy";
import {
  EvidenceSummaryPanel,
  GenerationSummaryPanel,
  ModelConclusionPanel,
  ModelReviewPanel,
  ProofLevelPanel,
  TradingDataStatusPanel
} from "@/app/shared/summary-projections";
import { safeReasonBullets, type BusinessSummary } from "@/lib/schemas/manual-run";
import type { AgentAuditView } from "@/lib/schemas/runs";

type DecisionSummaryCardProps = {
  mainAction: string | null | undefined;
  probability: number | null | undefined;
  referencePrice: number | null | undefined;
  entryTrigger: number | null | undefined;
  stopPrice: number | null | undefined;
  target1: number | null | undefined;
  target2: number | null | undefined;
  allowed: boolean | null | undefined;
  symbol: string | null | undefined;
  horizon: string | null | undefined;
  executionMode: string | null | undefined;
  productionFinalInputMode: string | null | undefined;
  analysis: Record<string, unknown>;
  verdictReasons: unknown;
  factsGate?: Record<string, unknown>;
  productionControlGate?: Record<string, unknown>;
  runContext?: Record<string, unknown>;
  finalInputSelection?: Record<string, unknown>;
  llmStatus?: string;
  notificationStatus?: string;
  businessSummary?: BusinessSummary;
  focusText?: string;
  evidenceSources?: AgentAuditView["evidence_sources"];
  sourceFreshness?: AgentAuditView["source_freshness"];
};

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function extractBlockingReasons(
  analysis: Record<string, unknown>,
  verdictReasons: unknown
): string[] {
  const ladder = analysis.decision_ladder;
  if (Array.isArray(ladder)) {
    for (const entry of ladder) {
      if (entry && typeof entry === "object" && (entry as { stage?: string }).stage === "risk_gate") {
        const reasons = toStringArray((entry as { reasons?: unknown }).reasons);
        if (reasons.length > 0) return safeReasonBullets(reasons);
      }
    }
  }
  return safeReasonBullets(toStringArray(verdictReasons));
}

function dataGapCount(analysis: Record<string, unknown>): number {
  const gaps = analysis.data_gaps;
  return Array.isArray(gaps) ? gaps.length : 0;
}

function recordValue(record: Record<string, unknown> | undefined, key: string): unknown {
  return record && Object.prototype.hasOwnProperty.call(record, key) ? record[key] : undefined;
}

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return String(value);
  if (typeof value === "string" || typeof value === "boolean") return productEnumLabel(value);
  return "已记录";
}

function positionText(position: unknown): string {
  if (!position || typeof position !== "object") return "未说明";
  const record = position as Record<string, unknown>;
  const parts = [
    textValue(record.side),
    record.entry_price !== undefined ? `均价 ${textValue(record.entry_price)}` : null,
    record.leverage !== undefined ? `杠杆 ${textValue(record.leverage)}` : null,
    record.size !== undefined ? `规模 ${textValue(record.size)}` : null
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "未说明";
}

function notificationTone(status: string | undefined): string {
  if (status === "sent") return "badge-success";
  if (status === "failed") return "badge-failed";
  return "badge-pending";
}

function notificationLabel(status: string | undefined): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  if (status === "disabled") return "通知未启用";
  return "未记录";
}

export function DecisionSummaryCard(props: DecisionSummaryCardProps) {
  const direction = classifyDirection(props.mainAction);
  const allowed = props.allowed === true;
  const blocked = props.allowed === false;
  const reasons = extractBlockingReasons(props.analysis, props.verdictReasons);
  const gaps = dataGapCount(props.analysis);
  const factsPassed = recordValue(props.factsGate, "passed");
  const factsSeverity = recordValue(props.factsGate, "severity");
  const missingFacts = toStringArray(recordValue(props.factsGate, "missing_execution_facts"));
  const productionAllowed = recordValue(props.productionControlGate, "allowed");
  const position = recordValue(props.runContext, "position");
  const riskMode = recordValue(props.runContext, "risk_mode");
  const summary = props.businessSummary;
  const decisionLabel = productDecisionLabel(summary?.decision_label) ?? (allowed ? "可人工复核" : blocked ? "已阻断" : "未知");
  const actionText = productDisplayText(summary?.action_text ?? props.mainAction) || "—";
  const factCheckText = factsPassed === true
    ? "通过"
    : missingFacts.length > 0
      ? `缺少 ${productDisplayItems(missingFacts).join("、")}`
      : textValue(factsSeverity);
  const reviewGateText = productionAllowed === true ? "通过" : productionAllowed === false ? "未通过" : "—";

  return (
    <section className={`decision-card ${allowed ? "decision-allowed" : ""} ${blocked ? "decision-blocked" : ""}`} aria-label="提醒建议摘要">
      <div className="decision-card-header">
        <span className={`direction-badge ${DIRECTION_TONE[direction]}`}>
          {DIRECTION_LABEL[direction]}
        </span>
        <div className="decision-card-title">
          <div className="decision-action">{actionText}</div>
          <div className="decision-meta">
            {props.symbol ? <span>{props.symbol}</span> : null}
            {props.horizon ? <span> · 周期 {props.horizon}</span> : null}
            {props.probability !== null && props.probability !== undefined ? (
              <span> · 概率 {formatPercent(props.probability)}</span>
            ) : null}
          </div>
        </div>
        <span className={`decision-status ${allowed ? "status-allowed" : "status-blocked"}`}>
          {decisionLabel}
        </span>
      </div>
      {summary ? <ModelConclusionPanel summary={summary.generation_summary} /> : null}

      <dl className="detail-list price-grid">
        <div>
          <dt>参考价</dt>
          <dd>{formatPrice(props.referencePrice)}</dd>
        </div>
        <div>
          <dt>触发价</dt>
          <dd>{formatPrice(props.entryTrigger)}</dd>
        </div>
        <div>
          <dt>止损</dt>
          <dd>{formatPrice(props.stopPrice)}</dd>
        </div>
        <div>
          <dt>目标 1</dt>
          <dd>{formatPrice(props.target1)}</dd>
        </div>
        <div>
          <dt>目标 2</dt>
          <dd>{formatPrice(props.target2)}</dd>
        </div>
        <div>
          <dt>数据缺口</dt>
          <dd>{summary ? summary.data_gap_bullets.length : gaps}</dd>
        </div>
        <div>
          <dt>当前持仓</dt>
          <dd>{positionText(position)}</dd>
        </div>
        <div>
          <dt>风险模式</dt>
          <dd>{textValue(riskMode)}</dd>
        </div>
        <div>
          <dt>事实检查</dt>
          <dd>{factCheckText}</dd>
        </div>
        <div>
          <dt>复核门槛</dt>
          <dd>{reviewGateText}</dd>
        </div>
        <div>
          <dt>通知</dt>
          <dd>
            {summary ? (
              <span className={`badge ${notificationTone(summary.notification.status)}`}>
                {notificationLabel(summary.notification.status)}
              </span>
            ) : props.notificationStatus ?? "未启用或未记录"}
          </dd>
        </div>
      </dl>
      {summary ? (
        <div className="mode-notice">
          <strong>{decisionLabel}</strong>
          <span>{productDisplayText(summary.mode_notice)}</span>
        </div>
      ) : null}
      {summary ? <TradingDataStatusPanel status={summary.market_data_status} /> : null}
      {summary ? <ProofLevelPanel summary={summary} /> : null}

      {summary ? (
        <div className="analysis-grid compact-summary-grid">
          <div>
            <h3>为什么</h3>
            <ul>{productDisplayItems(summary.reason_bullets, 4).map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <div>
            <h3>风险 / 缺口</h3>
            <ul>{productDisplayItems([...summary.risk_bullets, ...summary.data_gap_bullets], 5).map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <EvidenceSummaryPanel bullets={summary.evidence_bullets} />
          <ModelReviewPanel
            summary={summary.generation_summary}
            evidenceBullets={summary.evidence_bullets}
            focusText={props.focusText}
            evidenceSources={props.evidenceSources}
            sourceFreshness={props.sourceFreshness}
          />
          <div>
            <h3>生成链路</h3>
            <span className="badge badge-info">{productDisplayText(summary.generation_summary.mode_label)}</span>
            <strong className="analysis-text">{productDisplayText(summary.generation_summary.status_label)}</strong>
            <p className="analysis-text">{productDisplayText(summary.generation_summary.response_summary)}</p>
            <ul>{productDisplayItems(summary.generation_summary.detail_bullets, 5).map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <GenerationSummaryPanel summary={summary.generation_summary} />
          <div>
            <h3>下一步</h3>
            <ul>{productDisplayItems(summary.next_steps).map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </div>
      ) : reasons.length > 0 ? (
        <div className="verdict-reasons">
          <h3>{allowed ? "提示" : "阻断理由"}</h3>
          <ul>
            {productDisplayItems(reasons).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="decision-card-footer">
        {summary ? <span>{productDisplayText(summary.safety_notice)}</span> : null}
        {allowed ? <span>允许仅表示可进入人工复核，不是下单许可或收益保证。</span> : null}
        {blocked ? <span>已阻断：禁止作为操作依据，需补齐证据或调整配置后重新评估。</span> : null}
      </div>
    </section>
  );
}
