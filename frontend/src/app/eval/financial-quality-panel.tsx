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

function statusLabel(status: string) {
  if (status === "passed") return "通过";
  if (status === "failed") return "未通过";
  if (status === "not_configured") return "未配置";
  if (status === "not_enough_samples") return "样本不足";
  if (status === "baseline_reference") return "基线参考";
  return status ? "状态已记录" : "未知";
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

function decisionEffectLabel(value: string) {
  if (value === "none") return "不影响本次提醒";
  if (value === "advisory") return "仅作人工复盘参考";
  if (value === "release_blocking") return "阻断发布";
  return value ? "需人工复核" : "未知";
}

function blockingLabel(value: boolean) {
  return value ? "会阻断" : "不阻断";
}

function targetLabel(value: string) {
  if (value === "legacy_final") return "最终建议链路";
  if (value === "candidate") return "候选建议链路";
  if (value === "swarm_candidate_final") return "候选建议链路";
  if (value === "hold_no_trade") return "不操作基线";
  if (value === "no_trade") return "不操作基线";
  return value ? "其他复盘目标" : "-";
}

function sampleIdLabel(index: number) {
  return `样本 ${index + 1}`;
}

function sourceLabel(value: string | null | undefined) {
  if (value === "mocked_outcome") return "本地展示样本";
  if (value === "exchange_native") return "交易所原生样本";
  return value ? "其他样本来源" : "-";
}

function actionLabel(value: string) {
  if (value === "trigger long") return "触发做多";
  if (value === "trigger short") return "触发做空";
  if (value === "hold no trade" || value === "no trade") return "暂不操作";
  if (value === "close long") return "平多";
  if (value === "close short") return "平空";
  return value ? "未识别动作" : "-";
}

function unscoredReasonLabel(value: string | null | undefined) {
  if (!value) return "-";
  if (value === "price_source_not_exchange_native") {
    return "价格不是交易所原生样本";
  }
  if (value === "window_not_matured") return "观察窗口尚未成熟";
  if (value === "no_trade_action") return "不操作基线，不纳入交易命中评分";
  if (value === "missing_trade_levels") return "缺少交易价位，暂不评分";
  if (value === "unsupported_action") return "动作不适用于交易命中评分";
  return "暂未分类原因";
}

function scoreLabel(value: string | null | undefined) {
  if (!value) return "-";
  if (value === "window_direction_hit") return "窗口方向命中";
  if (value === "no_trade_counterfactual") return "不操作反事实基线";
  return "其他评分标签";
}

function isPendingOutcome(item: EvalOutcome) {
  return !item.can_score && (item.window.matured === false || item.unscored_reason === "window_not_matured" || item.window.unscored_reason === "window_not_matured");
}

export function financialQualityOutcomeErrorMessage(error?: string): string | undefined {
  return error ? "结果样本暂时无法加载，请稍后重试。" : undefined;
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
  const pendingOutcomes = (outcomes ?? []).filter(isPendingOutcome);
  const unscoredOutcomes = (outcomes ?? []).filter((item) => !item.can_score && !isPendingOutcome(item));
  const safeOutcomesError = financialQualityOutcomeErrorMessage(outcomesError);

  return (
    <section className="panel section-gap">
      <div className="panel-heading">
        <div>
          <h2>金融质量</h2>
          <p className="muted">基于已成熟结果样本的滞后复盘；真实金融质量必须来自交易所原生样本。</p>
        </div>
        <span className={`badge ${statusClass(qualityGate.status)}`}>{statusLabel(qualityGate.status)}</span>
      </div>

      <dl className="detail-list">
        <div>
          <dt>决策影响</dt>
          <dd>{decisionEffectLabel(qualityGate.decision_effect)}</dd>
        </div>
        <div>
          <dt>结构阻断</dt>
          <dd>{blockingLabel(qualityGate.structural_release_gate_blocking)}</dd>
        </div>
        <div>
          <dt>质量阻断</dt>
          <dd>{blockingLabel(qualityGate.blocking)}</dd>
        </div>
        <div>
          <dt>复盘目标</dt>
          <dd>{qualityGate.evaluation_targets.length ? qualityGate.evaluation_targets.map((target) => targetLabel(target)).join(" / ") : "-"}</dd>
        </div>
        <div>
          <dt>已收集结果样本</dt>
          <dd>
            {outcomes ? outcomes.length : "-"}（可评分 {scoredOutcomes.length} / 待成熟 {pendingOutcomes.length} / 不可评分 {unscoredOutcomes.length}）
          </dd>
        </div>
      </dl>

      {qualityGate.target_gates.length === 0 ? (
        <p className="muted">暂无离线结果样本；需要先写入交易所原生结果样本后再评估预测质量。</p>
      ) : (
        <div className="table-wrap section-gap">
          <table className="compact-table" aria-label="金融质量目标门禁">
            <thead>
              <tr>
                <th>评分目标</th>
                <th>状态</th>
                <th>可评分样本</th>
                <th>待成熟样本</th>
                <th>方向命中率</th>
                <th>Brier</th>
                <th>平均收益</th>
                <th>风险收益倍数</th>
                <th>评分标签</th>
              </tr>
            </thead>
            <tbody>
              {qualityGate.target_gates.map((targetGate) => (
                <tr key={targetGate.evaluation_target}>
                  <td>{targetLabel(targetGate.evaluation_target)}</td>
                  <td>
                    <span className={`badge ${statusClass(targetGate.status)}`}>{statusLabel(targetGate.status)}</span>
                  </td>
                  <td>
                    {targetGate.observed_scored_count} / {targetGate.minimum_scored_count}
                  </td>
                  <td>{targetGate.metrics.pending_count}</td>
                  <td>{formatRate(targetGate.metrics.direction_hit_rate)}</td>
                  <td>{formatNumber(targetGate.metrics.brier_score)}</td>
                  <td>{formatSignedPct(targetGate.metrics.average_pnl_pct)}</td>
                  <td>{formatNumber(targetGate.metrics.average_r_multiple)}</td>
                  <td>{scoreLabel(targetGate.brier_event_label)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="section-gap">
        <h3>已收集结果样本</h3>
        <p className="muted">
          数据来自后台结果采集任务或显式本地展示样本；该旁路复盘不会影响生产提醒。只有交易所原生真实成熟样本才进入真实金融质量评分。
        </p>
        {safeOutcomesError ? (
          <div className="error-state" role="alert">{safeOutcomesError}</div>
        ) : !outcomes || outcomes.length === 0 ? (
          <p className="muted">
            暂无结果样本。生成若干手动提醒后，等待观察窗口成熟并运行结果采集，即可在此看到复盘样本；本地展示样本只证明展示链路，不代表真实预测命中。
          </p>
        ) : (
          <div className="table-wrap">
            <table className="compact-table" aria-label="已收集结果样本">
              <thead>
                <tr>
                  <th>结果样本</th>
                  <th>评分目标</th>
                  <th>交易对</th>
                  <th>建议动作</th>
                  <th>来源</th>
                  <th>入场 / 止损</th>
                  <th>窗口收盘价</th>
                  <th>可评分</th>
                  <th>未评分原因</th>
                </tr>
              </thead>
              <tbody>
                {outcomes.map((item, index) => (
                  <tr key={`${item.decision_ref}:${item.evaluation_target}:${item.window.name}`}>
                    <td>{sampleIdLabel(index)}</td>
                    <td>{targetLabel(item.evaluation_target)}</td>
                    <td>{item.symbol}</td>
                    <td>{actionLabel(item.action)}</td>
                    <td>{sourceLabel(item.window.source_type)}</td>
                    <td>
                      {formatPrice(item.entry_price)} / {formatPrice(item.stop_price)}
                    </td>
                    <td>{formatPrice(item.window.close_price)}</td>
                    <td>{item.can_score ? "是" : "否"}</td>
                    <td>{unscoredReasonLabel(item.unscored_reason ?? item.window.unscored_reason)}</td>
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
