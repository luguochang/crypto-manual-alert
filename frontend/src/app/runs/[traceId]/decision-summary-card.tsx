import {
  DIRECTION_LABEL,
  DIRECTION_TONE,
  classifyDirection,
  formatPercent,
  formatPrice
} from "@/app/shared/direction";

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
        if (reasons.length > 0) return reasons;
      }
    }
  }
  return toStringArray(verdictReasons);
}

function dataGapCount(analysis: Record<string, unknown>): number {
  const gaps = analysis.data_gaps;
  return Array.isArray(gaps) ? gaps.length : 0;
}

export function DecisionSummaryCard(props: DecisionSummaryCardProps) {
  const direction = classifyDirection(props.mainAction);
  const allowed = props.allowed === true;
  const blocked = props.allowed === false;
  const reasons = extractBlockingReasons(props.analysis, props.verdictReasons);
  const gaps = dataGapCount(props.analysis);
  const isProductionInput = props.productionFinalInputMode === "decision_input";

  return (
    <section className={`decision-card ${allowed ? "decision-allowed" : ""} ${blocked ? "decision-blocked" : ""}`} aria-label="Decision summary">
      <div className="decision-card-header">
        <span className={`direction-badge ${DIRECTION_TONE[direction]}`}>
          {DIRECTION_LABEL[direction]}
        </span>
        <div className="decision-card-title">
          <div className="decision-action">{props.mainAction ?? "—"}</div>
          <div className="decision-meta">
            {props.symbol ? <span>{props.symbol}</span> : null}
            {props.horizon ? <span> · 周期 {props.horizon}</span> : null}
            {props.probability !== null && props.probability !== undefined ? (
              <span> · 概率 {formatPercent(props.probability)}</span>
            ) : null}
          </div>
        </div>
        <span className={`decision-status ${allowed ? "status-allowed" : "status-blocked"}`}>
          {allowed ? "允许手动核对" : blocked ? "已阻断" : "未知"}
        </span>
      </div>

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
          <dd>{gaps}</dd>
        </div>
      </dl>

      {reasons.length > 0 ? (
        <div className="verdict-reasons">
          <h3>{allowed ? "提示" : "阻断理由"}</h3>
          <ul>
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="decision-card-footer">
        {props.executionMode ? <span>模式: {props.executionMode}</span> : null}
        <span className={isProductionInput ? "tone-warning" : "tone-muted"}>
          {isProductionInput ? "生产最终输入: decision_input" : "生产最终输入: legacy_prompt（候选未切换）"}
        </span>
      </div>
    </section>
  );
}
