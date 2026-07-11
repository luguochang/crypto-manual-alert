import type { BusinessSummary } from "@/lib/schemas/manual-run";
import type { AgentAuditView } from "@/lib/schemas/runs";
import { productDisplayItems, productDisplayText, productEnumLabel } from "@/app/shared/product-copy";

type GenerationSummary = BusinessSummary["generation_summary"];
type MarketDataStatus = BusinessSummary["market_data_status"];
type EvidenceSource = AgentAuditView["evidence_sources"][number];
type SourceFreshness = AgentAuditView["source_freshness"][number];
type ProofLevelTone = "local" | "mock" | "staging" | "production";

function displayValue(value: string | null | undefined, fallback = "未记录"): string {
  const text = productDisplayText(value);
  return text || fallback;
}

function generationRows(summary: GenerationSummary): Array<[string, string]> {
  return [
    ["模型状态", displayValue(summary.status_label)],
    ["接口", displayValue(summary.provider_label)],
    ["模型", displayValue(summary.model)],
    ["耗时", displayValue(summary.duration_text)],
    ["Token", displayValue(summary.token_text)],
    ["完成状态", displayValue(summary.finish_reason)]
  ];
}

function rawCompletionText(summary: GenerationSummary): string {
  return displayValue(summary.raw_completion_excerpt, "");
}

function marketStatusTone(status: string): string {
  if (status === "ok" || status === "success") return "badge-success";
  if (status === "failed") return "badge-failed";
  return "badge-pending";
}

function proofLevel(summary: BusinessSummary): { label: string; detail: string; tone: ProofLevelTone } {
  const modeLabel = summary.generation_summary.mode_label;
  const modeNotice = summary.mode_notice;
  const notificationSent = summary.notification.status === "sent";
  const modelReturned = summary.generation_summary.status_label.includes("模型已返回");
  if (modeNotice.includes("本地/预发")) {
    return {
      label: "本地预发人工复核",
      detail: "本地或预发证据可验证提醒链路；不是生产成功。",
      tone: "staging"
    };
  }
  if (modeLabel.includes("模型链路演练")) {
    return {
      label: "模型链路演练",
      detail: "已验证模型调用、解析和页面呈现；不是生产成功。",
      tone: "mock"
    };
  }
  if (
    modeLabel.includes("真实模型链路") &&
    modelReturned &&
    notificationSent &&
    summary.market_data_status.execution_facts_ready
  ) {
    return {
      label: "生产可复核证据已记录",
      detail: "真实模型、证据和通知状态已进入本次提醒；仍需人工核对后手动执行。",
      tone: "production"
    };
  }
  return {
    label: "本地流程验证",
    detail: "当前只证明本地提醒流程和页面呈现；不是生产成功。",
    tone: "local"
  };
}

function notificationStatusText(status: string): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "通知失败";
  if (status === "disabled") return "通知未启用";
  return "通知未记录";
}

export function ProofLevelPanel({ summary }: { summary: BusinessSummary }) {
  const proof = proofLevel(summary);
  const modelStatus = productDisplayText(summary.generation_summary.status_label) || "模型状态未记录";
  const notificationStatus = notificationStatusText(summary.notification.status);

  return (
    <section className={`proof-level-strip proof-${proof.tone}`} aria-label="提醒证据级别">
      <div>
        <span>证据级别</span>
        <strong>{proof.label}</strong>
        <p>{proof.detail}</p>
      </div>
      <dl>
        <div>
          <dt>模型</dt>
          <dd>{modelStatus}</dd>
        </div>
        <div>
          <dt>通知</dt>
          <dd>{notificationStatus}</dd>
        </div>
        <div>
          <dt>执行边界</dt>
          <dd>人工核对后手动执行</dd>
        </div>
      </dl>
    </section>
  );
}

export function GenerationSummaryPanel({ summary }: { summary: GenerationSummary }) {
  const rawCompletion = rawCompletionText(summary);
  const rawCompletionLabel = displayValue(summary.raw_completion_label, "模型原始返回摘录");

  return (
    <section className="summary-projection" aria-label="模型返回摘要">
      <h3>模型返回摘要</h3>
      <span className="badge badge-info">{productDisplayText(summary.mode_label)}</span>
      <dl className="detail-list compact-list summary-projection-list">
        {generationRows(summary).map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="analysis-text">摘要：{productDisplayText(summary.response_summary)}</p>
      {rawCompletion ? (
        <div className="model-raw-excerpt" aria-label="模型原始返回摘录">
          <strong>{rawCompletionLabel}</strong>
          <p>{rawCompletion}</p>
        </div>
      ) : null}
      {summary.detail_bullets.length > 0 ? (
        <ul>
          {productDisplayItems(summary.detail_bullets, 5).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function ModelConclusionPanel({ summary }: { summary: GenerationSummary }) {
  const conclusion = displayValue(summary.response_summary, "模型结论暂未形成可读摘录。");
  const status = displayValue(summary.status_label, "模型状态未记录");

  return (
    <section className="model-conclusion-panel" aria-label="模型结论">
      <div className="model-conclusion-heading">
        <h3>模型结论</h3>
      </div>
      <p>{conclusion}</p>
      <dl>
        <div>
          <dt>状态</dt>
          <dd>{status}</dd>
        </div>
        <div>
          <dt>执行边界</dt>
          <dd>仅供人工复核，不自动下单</dd>
        </div>
      </dl>
    </section>
  );
}

function modelReviewFocus(summary: GenerationSummary, focusText?: string): string {
  const focus = displayValue(focusText, "");
  if (focus) {
    return `本次关注：${focus}`;
  }
  if (summary.status_label.includes("未调用")) {
    return "用户关注点已写入本次复核备注；本次未调用外部模型，适合验证提醒流程与页面呈现。";
  }
  if (summary.status_label.includes("失败")) {
    return "用户关注点已写入本次复核备注；模型调用失败，本次不能当作成功提醒结论。";
  }
  return "用户关注点已写入本次复核备注；模型输出仅作为人工复核材料，系统不会自动下单。";
}

function modelReviewExcerpt(summary: GenerationSummary): string {
  const summaryText = displayValue(summary.response_summary, "");
  if (summaryText) {
    return summaryText;
  }
  return displayValue(summary.status_label, "模型结论暂未形成可读摘录。");
}

function modelRawCompletionExcerpt(summary: GenerationSummary): string {
  return rawCompletionText(summary) || "模型原始返回安全摘录暂未记录；请以模型结论和交易数据状态为准。";
}

function sourceEvidenceText(source: EvidenceSource): string {
  const sourceType = productEnumLabel(source.source_type ?? "证据来源");
  const tier = source.source_tier === null || source.source_tier === undefined ? "" : productDisplayText(String(source.source_tier));
  const freshness = productEnumLabel(source.freshness_status ?? "新鲜度未记录");
  const factText = source.can_satisfy_execution_fact ? "可支撑执行事实" : "仅作人工复核参考";
  return `证据来源：${[sourceType, tier].filter(Boolean).join(" / ") || "已记录"}，${freshness}，${factText}`;
}

function freshnessEvidenceText(row: SourceFreshness): string {
  const sourceType = productEnumLabel(row.source_type);
  const tier = row.source_tier === null || row.source_tier === undefined ? "" : productDisplayText(String(row.source_tier));
  const freshness = productEnumLabel(row.freshness_status);
  return `证据来源：${[sourceType, tier].filter(Boolean).join(" / ") || "已记录"}，${freshness}，${row.count} 条记录`;
}

function modelReviewEvidence(
  evidenceBullets: string[] | undefined,
  detailBullets: string[],
  evidenceSources: EvidenceSource[] = [],
  sourceFreshness: SourceFreshness[] = []
): string {
  const sourceRows = evidenceSources.slice(0, 2).map(sourceEvidenceText);
  if (sourceRows.length > 0) {
    return sourceRows.join("；");
  }
  const freshnessRows = sourceFreshness.slice(0, 2).map(freshnessEvidenceText);
  if (freshnessRows.length > 0) {
    return freshnessRows.join("；");
  }
  const evidence = productDisplayItems(evidenceBullets ?? [], 3);
  if (evidence.length > 0) {
    return `证据摘要：${evidence.join("；")}`;
  }
  const details = productDisplayItems(detailBullets, 3);
  if (details.length > 0) {
    return `证据摘要：${details.join("；")}`;
  }
  return "引用与证据摘要暂未记录；请以价格、风险和后续复盘面板为准。";
}

export function ModelReviewPanel({
  summary,
  evidenceBullets = [],
  focusText,
  evidenceSources = [],
  sourceFreshness = []
}: {
  summary: GenerationSummary;
  evidenceBullets?: string[];
  focusText?: string;
  evidenceSources?: EvidenceSource[];
  sourceFreshness?: SourceFreshness[];
}) {
  const rows: Array<[string, string]> = [
    ["用户关注点", modelReviewFocus(summary, focusText)],
    ["模型结论摘录", modelReviewExcerpt(summary)],
    ["模型原始返回摘录", modelRawCompletionExcerpt(summary)],
    ["引用与证据", modelReviewEvidence(evidenceBullets, summary.detail_bullets, evidenceSources, sourceFreshness)]
  ];

  return (
    <section className="summary-projection model-review" aria-label="模型审阅">
      <h3>模型审阅</h3>
      <dl className="detail-list compact-list summary-projection-list">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{productDisplayText(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="analysis-text">
        这里展示可读摘录和证据指向；原始请求、原始返回和密钥字段不会出现在默认产品页。
      </p>
    </section>
  );
}

export function TradingDataStatusPanel({ status }: { status: MarketDataStatus }) {
  const items = status.items.slice(0, 7);
  const statusText = status.execution_facts_ready ? "执行事实就绪" : "执行事实不完整";
  const statusTone = status.execution_facts_ready ? "badge-success" : "badge-pending";

  return (
    <section className="summary-projection trading-data-status" aria-label="交易数据状态">
      <div className="trading-status-heading">
        <h3>交易数据状态</h3>
        <span className={`badge ${statusTone}`}>{statusText}</span>
      </div>
      <p className="analysis-text">{productDisplayText(status.summary)}</p>
      <dl className="trading-status-counts">
        <div>
          <dt>来源</dt>
          <dd>{displayValue(status.provider_label, "未记录")}</dd>
        </div>
        <div>
          <dt>成功</dt>
          <dd>{status.success_count}</dd>
        </div>
        <div>
          <dt>失败</dt>
          <dd>{status.failed_count}</dd>
        </div>
        <div>
          <dt>缺失</dt>
          <dd>{status.missing_count}</dd>
        </div>
      </dl>
      {items.length > 0 ? (
        <ul className="trading-status-list">
          {items.map((item) => {
            const detail = item.error_type || item.failure_reason || item.value_text || item.source_label || "未记录可展示详情";
            return (
              <li key={item.name} className={`market-status-${item.status}`}>
                <span className="trading-status-name">{productDisplayText(item.label)}</span>
                <span className={`badge ${marketStatusTone(item.status)}`}>{productDisplayText(item.status_label)}</span>
                <span>{productDisplayText(detail)}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">交易数据状态暂未记录。</p>
      )}
    </section>
  );
}

export function EvidenceSummaryPanel({ bullets }: { bullets: string[] }) {
  const items = productDisplayItems(bullets, 5);
  return (
    <section className="summary-projection" aria-label="证据摘要">
      <h3>证据</h3>
      <ul>
        {(items.length > 0 ? items : ["证据摘要暂未记录；请先以提醒摘要、价位、风险和通知状态为准。"]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
