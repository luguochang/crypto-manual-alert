import type { EvalRunSummary, FinancialQualityGate } from "@/lib/schemas/eval";

type SummaryCardProps = {
  latestRun?: EvalRunSummary;
  compact?: boolean;
};

type SummaryItem = {
  label: string;
  value: string;
  hint?: string;
  tone?: "ok" | "warn" | "danger" | "neutral";
};

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function boolValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function percentValue(value: unknown): string | undefined {
  const num = numberValue(value);
  if (num == null) return undefined;
  const normalized = Math.abs(num) <= 1 ? num * 100 : num;
  return `${Math.round(normalized)}%`;
}

function signedValue(value: unknown, suffix = ""): string | undefined {
  const num = numberValue(value);
  if (num == null) return undefined;
  const sign = num > 0 ? "+" : "";
  return `${sign}${num}${suffix}`;
}

function firstDefined(...values: Array<string | undefined>): string {
  return values.find((item) => item && item !== "undefined") ?? "-";
}

function statusLabel(value: string | undefined): string {
  if (!value) return "-";
  const labels: Record<string, string> = {
    passed: "通过",
    completed: "已完成",
    failed: "未通过",
    error: "执行异常",
    clean: "无异常副作用",
    unexpected_side_effects: "存在异常副作用",
    not_enough_samples: "样本不足",
    baseline_reference: "基线参考",
    not_configured: "未配置",
    none: "不影响生产"
  };
  return labels[value] ?? "已记录";
}

function targetLabel(value: string | undefined): string {
  if (!value) return "-";
  const labels: Record<string, string> = {
    legacy_final: "最终建议链路",
    swarm_candidate_final: "候选建议链路",
    hold_no_trade: "不操作对照",
    no_trade: "不操作对照"
  };
  return labels[value] ?? "其他对照";
}

function targetsText(values: string[] | undefined): string {
  return values?.length ? values.map(targetLabel).join(" / ") : "-";
}

function replayItems(replay: Record<string, unknown>, run?: EvalRunSummary): SummaryItem[] {
  const total = numberValue(replay.case_count) ?? numberValue(replay.total) ?? run?.case_count;
  const passed = numberValue(replay.pass_count) ?? numberValue(replay.passed) ?? run?.pass_count;
  const failed = numberValue(replay.fail_count) ?? numberValue(replay.failed) ?? run?.fail_count;
  const errored = numberValue(replay.error_count) ?? numberValue(replay.errors);
  const duration = numberValue(replay.duration_ms);
  const status = stringValue(replay.status) ?? run?.status;

  return [
    { label: "回放状态", value: firstDefined(statusLabel(status)), tone: status === "passed" ? "ok" : failed && failed > 0 ? "danger" : "neutral" },
    { label: "样本覆盖", value: total != null ? String(total) : "-", hint: passed != null || failed != null ? `通过 ${passed ?? 0} / 未通过 ${failed ?? 0}` : undefined },
    { label: "错误", value: errored != null ? String(errored) : "0", tone: errored && errored > 0 ? "danger" : "ok" },
    { label: "耗时", value: duration != null ? `${duration} ms` : "-" }
  ];
}

function deltaItems(delta: Record<string, unknown>): SummaryItem[] {
  const created = numberValue(delta.created) ?? numberValue(delta.created_count);
  const updated = numberValue(delta.updated) ?? numberValue(delta.updated_count);
  const deleted = numberValue(delta.deleted) ?? numberValue(delta.deleted_count);
  const unexpected = numberValue(delta.unexpected) ?? numberValue(delta.unexpected_count);
  const status = stringValue(delta.status) ?? (unexpected && unexpected > 0 ? "unexpected_side_effects" : "clean");

  return [
    { label: "副作用状态", value: statusLabel(status), tone: status === "clean" ? "ok" : "warn" },
    { label: "新增记录", value: created != null ? String(created) : "0" },
    { label: "更新 / 删除", value: `${updated ?? 0} / ${deleted ?? 0}` },
    { label: "异常写入", value: unexpected != null ? String(unexpected) : "0", tone: unexpected && unexpected > 0 ? "danger" : "ok" }
  ];
}

function financialItems(gate: FinancialQualityGate | undefined): SummaryItem[] {
  const targetCount = gate?.target_gates?.length ?? 0;
  const blockingTargets = gate?.target_gates?.filter((item) => item.blocking).length ?? 0;
  const targets = targetsText(gate?.evaluation_targets);
  const reasons = gate?.blocking_reasons?.length ? gate.blocking_reasons.slice(0, 2).join("；") : undefined;

  return [
    { label: "金融质量", value: statusLabel(gate?.status), tone: gate?.blocking ? "danger" : gate?.status === "not_enough_samples" ? "warn" : "ok", hint: reasons },
    { label: "评估目标", value: targetCount ? String(targetCount) : "-", hint: targets },
    { label: "阻断目标", value: String(blockingTargets), tone: blockingTargets > 0 ? "danger" : "ok" },
    { label: "生产影响", value: statusLabel(gate?.decision_effect) }
  ];
}

function baselineItems(metadata: Record<string, unknown>): SummaryItem[] {
  const baseline = Object.keys(objectValue(metadata.baseline)).length > 0 ? objectValue(metadata.baseline) : objectValue(metadata.baseline_delta);
  const noTrade = Object.keys(objectValue(metadata.no_trade_baseline)).length > 0 ? objectValue(metadata.no_trade_baseline) : objectValue(metadata.no_trade_delta);
  const delta = signedValue(baseline.delta_pct, "%") ?? signedValue(noTrade.delta_pct, "%") ?? signedValue(baseline.delta) ?? signedValue(noTrade.delta);
  const coverage = percentValue(metadata.outcome_coverage) ?? percentValue(baseline.outcome_coverage) ?? percentValue(noTrade.outcome_coverage);
  const pending = numberValue(metadata.pending_outcomes) ?? numberValue(baseline.pending_count) ?? numberValue(noTrade.pending_count);
  const target = stringValue(baseline.target) ?? stringValue(noTrade.target) ?? "hold_no_trade";

  return [
    { label: "对照目标", value: targetLabel(target), hint: "最终建议 / 候选建议 / 不操作对照" },
    { label: "差值", value: delta ?? "待样本", tone: delta?.startsWith("-") ? "danger" : delta ? "ok" : "warn" },
    { label: "结果覆盖", value: coverage ?? "待成熟", tone: coverage ? "ok" : "warn" },
    { label: "待成熟", value: pending != null ? String(pending) : "-", tone: pending && pending > 0 ? "warn" : "neutral" }
  ];
}

function SummaryGrid({ title, description, items }: { title: string; description: string; items: SummaryItem[] }) {
  return (
    <section className="eval-summary-block">
      <div className="section-heading-row compact-heading">
        <div>
          <h3>{title}</h3>
          <p className="muted">{description}</p>
        </div>
      </div>
      <div className="eval-summary-grid">
        {items.map((item) => (
          <article key={`${title}-${item.label}`} className={`eval-summary-cell tone-${item.tone ?? "neutral"}`}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {item.hint ? <small>{item.hint}</small> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

export function EvalRunEvidenceSummary({ latestRun, compact = false }: SummaryCardProps) {
  if (!latestRun) {
    return <p className="muted">暂无复盘结果。运行工程复盘后会在这里显示回放、副作用守卫、对照样本与金融质量摘要。</p>;
  }

  const metadata = latestRun.metadata ?? {};
  const replay = objectValue(metadata.replay);
  const sideEffectDeltas = objectValue(metadata.side_effect_deltas);
  const financialQuality = metadata.financial_quality_gate;

  return (
    <div className={compact ? "eval-summary-stack compact" : "eval-summary-stack"}>
      <SummaryGrid
        title="回放覆盖"
        description="基于冻结输入回放样本覆盖与失败情况；失败不代表生产副作用。"
        items={replayItems(replay, latestRun)}
      />
      <SummaryGrid
        title="副作用守卫"
        description="确认工程复盘没有写生产提醒、通知或订单副作用。"
        items={deltaItems(sideEffectDeltas)}
      />
      <SummaryGrid
        title="结果与对照"
        description="真实结果样本与不操作对照；观察窗口未成熟时不计输赢。"
        items={baselineItems(metadata)}
      />
      <SummaryGrid
        title="发布质量门禁"
        description="金融质量是 advisory/release gate 证据，样本不足必须显式展示。"
        items={financialItems(financialQuality)}
      />
    </div>
  );
}
