import { ExternalLink, History, ShieldCheck, TriangleAlert } from "lucide-react";

import type { AnalysisResultViewModel } from "@/features/analysis/analysis-view-model";

export function AnalysisResult({ result }: { result: AnalysisResultViewModel }) {
  const expired = result.state === "expired";
  const historical = result.state === "historical";

  return (
    <section
      className="analysis-result"
      data-testid="analysis-result"
      data-artifact-state={result.state}
      data-actionable={result.actionable}
      aria-labelledby="result-title"
    >
      <header className="result-header">
        <div>
          <p className="section-kicker">{historical ? "Historical analysis" : expired ? "Expired analysis" : "Committed analysis"}</p>
          <h2 id="result-title">{result.instrument.replace("-USDT-SWAP", "")} · {result.horizon}</h2>
          <span>{regimeLabel(result.regime)}</span>
        </div>
        <div className="decision-summary">
          <span>{expired || historical ? "Status" : "Action"}</span>
          <strong className={expired ? "verdict-label is-danger" : historical ? "verdict-label is-warning" : undefined}>
            {expired
              ? <><TriangleAlert size={16} aria-hidden="true" />已过期</>
              : historical
                ? <><History size={16} aria-hidden="true" />历史成功报告</>
                : result.action}
          </strong>
          <span>
            {expired || historical
              ? `原建议：${result.action} · ${result.probabilityPercent}% probability`
              : `${result.probabilityPercent}% probability`}
          </span>
        </div>
      </header>

      {historical ? (
        <div className="historical-artifact-note" role="note">
          <History size={18} aria-hidden="true" />
          <p>这是此前成功运行保存的报告，不代表本次运行的结果，也不可作为当前计划。</p>
        </div>
      ) : null}

      <div className="trade-plan-grid" aria-label={historical ? "历史分析快照" : expired ? "已过期分析快照" : "交易计划"}>
        <Metric label="Reference" value={formatPrice(result.reference)} />
        <Metric label="Entry" value={formatOptionalPrice(result.entry)} />
        <Metric label="Stop" value={formatOptionalPrice(result.stop)} tone={expired || historical ? undefined : "danger"} />
        <Metric
          label="Targets"
          value={result.targets.length ? result.targets.map(formatPrice).join(" / ") : "未设置"}
          tone={expired || historical ? undefined : "success"}
        />
        <Metric label="Probability" value={`${result.probabilityPercent}%`} />
        <Metric label="TTL" value={`${result.validity.expiresInSeconds} 秒`} />
        <Metric
          label="有效至"
          value={expired ? `已过期 · ${formatValidity(result.validity.expiresAt)}` : formatValidity(result.validity.expiresAt)}
          tone={expired ? "danger" : undefined}
        />
      </div>

      <section className="result-section" aria-labelledby="evidence-heading">
        <div className="result-section-heading">
          <div>
            <p className="section-index">01</p>
            <h2 id="evidence-heading">Evidence</h2>
          </div>
          <span className={`verdict-label ${historical ? "is-warning" : result.evidence.sufficient ? "is-positive" : "is-warning"}`}>
            {historical
              ? <History size={16} aria-hidden="true" />
              : result.evidence.sufficient
                ? <ShieldCheck size={16} aria-hidden="true" />
                : <TriangleAlert size={16} aria-hidden="true" />}
            {historical ? "历史证据记录" : result.evidence.sufficient ? "必要证据完整" : "证据不足"}
          </span>
        </div>
        <div className="detail-grid">
          <Detail label="置信上限" value={`${result.evidence.confidenceCapPercent}%`} />
          <Detail label="缺失必要项" value={joinOrNone(result.evidence.missingRequired)} />
          <Detail label="缺失可选项" value={joinOrNone(result.evidence.missingOptional)} />
          <Detail label="不可用数据" value={joinOrNone(result.unavailableData)} />
        </div>
        {result.evidence.warnings.length ? <NoticeList items={result.evidence.warnings} /> : null}
      </section>

      <section className="result-section" aria-labelledby="risk-heading">
        <div className="result-section-heading">
          <div>
            <p className="section-index">02</p>
            <h2 id="risk-heading">Risk</h2>
          </div>
          <span className={`verdict-label ${historical ? "is-warning" : result.risk.allowed ? "is-positive" : "is-danger"}`}>
            {historical
              ? <History size={16} aria-hidden="true" />
              : result.risk.allowed
                ? <ShieldCheck size={16} aria-hidden="true" />
                : <TriangleAlert size={16} aria-hidden="true" />}
            {historical ? "历史风险记录" : result.risk.allowed ? "风险门禁通过" : "风险门禁阻断"}
          </span>
        </div>
        <div className="detail-grid">
          <Detail label="风险比例" value={`${formatCompact(result.risk.riskPercent)}%`} />
          <Detail label="最大杠杆" value={`${result.risk.maxLeverage}x`} />
          <Detail label="仓位级别" value={positionLabel(result.risk.positionSize)} />
          <Detail label="置信上限" value={`${result.risk.confidenceCapPercent}%`} />
        </div>
        {result.risk.blockedReasons.length ? <NoticeList items={result.risk.blockedReasons} danger /> : null}
        {result.risk.warnings.length ? <NoticeList items={result.risk.warnings} /> : null}
      </section>

      <section className="result-section" aria-labelledby="reasoning-heading">
        <div className="result-section-heading">
          <div>
            <p className="section-index">03</p>
            <h2 id="reasoning-heading">判断依据</h2>
          </div>
        </div>
        <ol className="rationale-list">
          {result.rationale.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
        </ol>
        <div className="reasoning-notes">
          <Detail label="反向判断" value={result.whyNotOpposite} />
          <Detail label="失效条件" value={result.invalidation || "未提供"} />
        </div>
      </section>

      <section className="result-section source-section" aria-labelledby="sources-heading">
        <div className="result-section-heading">
          <div>
            <p className="section-index">04</p>
            <h2 id="sources-heading">来源链接</h2>
          </div>
        </div>
        {result.sources.length ? (
          <ul className="source-list">
            {result.sources.map((source, index) => (
              <li key={`${source.href}:${index}`} data-evidence-matched={source.evidenceMatched}>
                <a href={source.href} target="_blank" rel="noreferrer">
                  <div className="source-copy">
                    <strong>{source.label}</strong>
                    <small>{source.href}</small>
                    {source.evidenceMatched ? (
                      <dl className="source-metadata">
                        <SourceMetadata label="Provider" value={source.provider ?? "未提供"} />
                        <SourceMetadata label="关系" value={relationLabel(source.relation)} />
                        <SourceMetadata
                          label="发布时间"
                          value={source.publishedAt ? <SourceTime value={source.publishedAt} /> : "未提供"}
                        />
                        <SourceMetadata
                          label="抓取时间"
                          value={source.fetchedAt ? <SourceTime value={source.fetchedAt} /> : "未提供"}
                        />
                      </dl>
                    ) : (
                      <span className="source-match-note">未匹配本次 Web 证据，仅按报告引用展示。</span>
                    )}
                  </div>
                  <ExternalLink size={17} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ul>
        ) : <p className="muted-copy">当前结果未提供外部来源链接。</p>}
      </section>
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "danger" | "success" }) {
  return (
    <div className={`metric ${tone ? `metric-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function NoticeList({ items, danger = false }: { items: string[]; danger?: boolean }) {
  return (
    <ul className={`notice-list ${danger ? "is-danger" : ""}`}>
      {items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

function SourceMetadata({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function SourceTime({ value }: { value: string }) {
  return <time dateTime={value}>{formatValidity(value)}</time>;
}

function formatPrice(value: number) {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatOptionalPrice(value: number | null) {
  return value === null ? "未设置" : formatPrice(value);
}

function formatCompact(value: number) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
}

function formatValidity(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    hour12: false,
  }).format(new Date(value));
}

function joinOrNone(values: string[]) {
  return values.length ? values.join("、") : "无";
}

function positionLabel(value: string) {
  return ({ light: "轻仓", standard: "标准", heavy: "重仓", none: "不持仓" } as Record<string, string>)[value] ?? value;
}

function regimeLabel(value: string) {
  return ({
    risk_on: "Risk on",
    risk_off: "Risk off",
    event_compression: "Event compression",
    surprise_repricing: "Surprise repricing",
  } as Record<string, string>)[value] ?? value;
}

function relationLabel(value: string | null) {
  if (!value) return "未提供";
  return ({
    supports: "支持判断",
    contradicts: "反向证据",
    context: "背景信息",
  } as Record<string, string>)[value] ?? value;
}
