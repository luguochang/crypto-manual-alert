import type { EvalOutcome, FinancialQualityGate } from "@/lib/schemas/eval";

function statusClass(status: string) {
  if (status === "passed") {
    return "badge-success";
  }
  if (status === "failed") {
    return "badge-failed";
  }
  return "badge-pending";
}

function formatRate(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "-";
  }
  return `${Math.round(value * 1000) / 10}%`;
}

function formatNumber(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(3);
}

function formatSignedPct(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "-";
  }
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function formatPrice(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

export function FinancialQualityPanel({
  gate,
  outcomes,
  outcomesError
}: {
  gate: FinancialQualityGate | undefined;
  outcomes?: EvalOutcome[];
  outcomesError?: string;
}) {
  const qualityGate =
    gate ?? {
      schema_version: 1,
      status: "not_configured",
      decision_effect: "none",
      structural_release_gate_blocking: false,
      blocking: false,
      blocking_reasons: [],
      evaluation_targets: [],
      target_gates: []
    };
  const scoredOutcomes = (outcomes ?? []).filter((item) => item.can_score);
  const pendingOutcomes = (outcomes ?? []).filter((item) => !item.can_score);

  return (
    <section className="panel section-gap">
      <div className="panel-heading">
        <div>
          <h2>Financial Quality</h2>
          <p className="muted">滞后 outcome 评测；不作为结构安全 hard gate。</p>
        </div>
        <span className={`badge ${statusClass(qualityGate.status)}`}>{qualityGate.status}</span>
      </div>

      <dl className="detail-list">
        <div>
          <dt>Decision Effect</dt>
          <dd>{qualityGate.decision_effect}</dd>
        </div>
        <div>
          <dt>Structural Blocking</dt>
          <dd>{qualityGate.structural_release_gate_blocking ? "true" : "false"}</dd>
        </div>
        <div>
          <dt>Quality Blocking</dt>
          <dd>{qualityGate.blocking ? "true" : "false"}</dd>
        </div>
        <div>
          <dt>Targets</dt>
          <dd>{qualityGate.evaluation_targets.length ? qualityGate.evaluation_targets.join(", ") : "-"}</dd>
        </div>
        <div>
          <dt>已收集 Outcome</dt>
          <dd>
            {outcomes ? outcomes.length : "-"}（可评分 {scoredOutcomes.length} / 待成熟 {pendingOutcomes.length}）
          </dd>
        </div>
      </dl>

      {qualityGate.target_gates.length === 0 ? (
        <p className="muted">暂无离线 outcome 样本；需要先写入 exchange-native outcome 后再评估预测质量。</p>
      ) : (
        <div className="table-wrap section-gap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Target</th>
                <th>状态</th>
                <th>Scored</th>
                <th>Pending</th>
                <th>Direction Hit</th>
                <th>Brier</th>
                <th>PnL</th>
                <th>R Multiple</th>
                <th>Label</th>
              </tr>
            </thead>
            <tbody>
              {qualityGate.target_gates.map((targetGate) => (
                <tr key={targetGate.evaluation_target}>
                  <td>{targetGate.evaluation_target}</td>
                  <td>
                    <span className={`badge ${statusClass(targetGate.status)}`}>{targetGate.status}</span>
                  </td>
                  <td>
                    {targetGate.observed_scored_count} / {targetGate.minimum_scored_count}
                  </td>
                  <td>{targetGate.metrics.pending_count}</td>
                  <td>{formatRate(targetGate.metrics.direction_hit_rate)}</td>
                  <td>{formatNumber(targetGate.metrics.brier_score)}</td>
                  <td>{formatSignedPct(targetGate.metrics.average_pnl_pct)}</td>
                  <td>{formatNumber(targetGate.metrics.average_r_multiple)}</td>
                  <td>{targetGate.brier_event_label ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="section-gap">
        <h3>已收集 Outcome 样本</h3>
        <p className="muted">
          数据来自 <code>crypto-alert collect-outcomes</code> 写入的 OutcomeStore（旁路 eval sidecar，不影响生产）。
        </p>
        {outcomesError ? (
          <div className="error-state">{outcomesError}</div>
        ) : !outcomes || outcomes.length === 0 ? (
          <p className="muted">
            暂无 outcome 样本。生成若干手动 run 后，待 horizon 成熟运行 collect-outcomes 即可在此看到真实预测命中情况。
          </p>
        ) : (
          <div className="table-wrap">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Decision Ref</th>
                  <th>Target</th>
                  <th>Symbol</th>
                  <th>Action</th>
                  <th>Entry / Stop</th>
                  <th>窗口 Close</th>
                  <th>可评分</th>
                  <th>未评分原因</th>
                </tr>
              </thead>
              <tbody>
                {outcomes.map((item) => (
                  <tr key={`${item.decision_ref}:${item.window.name}`}>
                    <td>{item.decision_ref}</td>
                    <td>{item.evaluation_target}</td>
                    <td>{item.symbol}</td>
                    <td>{item.action}</td>
                    <td>
                      {formatPrice(item.entry_price)} / {formatPrice(item.stop_price)}
                    </td>
                    <td>{formatPrice(item.window.close_price)}</td>
                    <td>{item.can_score ? "是" : "否"}</td>
                    <td>{item.unscored_reason ?? item.window.unscored_reason ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
