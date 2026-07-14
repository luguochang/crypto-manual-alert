import {
  CircleAlert,
  ExternalLink,
  Globe2,
  LoaderCircle,
  RadioTower,
} from "lucide-react";

import type { AnalysisResearchViewModel } from "@/features/analysis/analysis-view-model";

export function ResearchEvidence({ research }: { research: AnalysisResearchViewModel }) {
  return (
    <section className="research-evidence" aria-labelledby="research-evidence-title">
      <header className="research-evidence-header">
        <div>
          <span className="research-evidence-icon" aria-hidden="true"><Globe2 size={19} /></span>
          <div>
            <p className="section-kicker">Verified context</p>
            <h2 id="research-evidence-title">市场与研究证据</h2>
          </div>
        </div>
        <ResearchState state={research.state} count={research.webEvidence.length} />
      </header>

      {research.marketSnapshot ? (
        <section className="market-snapshot" aria-labelledby="market-snapshot-title">
          <div className="research-subheading">
            <div>
              <RadioTower size={17} aria-hidden="true" />
              <h3 id="market-snapshot-title">市场摘要</h3>
            </div>
            <span>
              {research.marketSnapshot.provider} · <Time value={research.marketSnapshot.fetchedAt} />
            </span>
          </div>
          <p className="market-summary">{research.marketSnapshot.summary}</p>
          {research.marketSnapshot.metrics.length > 0 ? (
            <dl className="market-metrics">
              {research.marketSnapshot.metrics.map((metric) => (
                <div key={metric.label}>
                  <dt>{metric.label}</dt>
                  <dd>{metric.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </section>
      ) : null}

      <section className="web-evidence" aria-labelledby="web-evidence-title">
        <div className="research-subheading">
          <div>
            <Globe2 size={17} aria-hidden="true" />
            <h3 id="web-evidence-title">Web 来源</h3>
          </div>
          <span>{research.webEvidence.length} 条</span>
        </div>

        {research.webEvidence.length > 0 ? (
          <ol className="web-evidence-list">
            {research.webEvidence.map((evidence) => (
              <li key={evidence.href}>
                <article>
                  <div className="evidence-source-row">
                    <span>{evidence.provider}</span>
                    <span>{relationLabel(evidence.relation)}</span>
                  </div>
                  <h4>
                    <a href={evidence.href} target="_blank" rel="noreferrer">
                      {evidence.title}
                      <ExternalLink size={15} aria-hidden="true" />
                    </a>
                  </h4>
                  <p>{evidence.summary}</p>
                  <dl className="evidence-metadata">
                    {evidence.author ? <Metadata label="作者" value={evidence.author} /> : null}
                    {evidence.publishedAt ? (
                      <Metadata label="发布时间" value={<Time value={evidence.publishedAt} />} />
                    ) : (
                      <Metadata label="发布时间" value="未提供" />
                    )}
                    <Metadata label="抓取时间" value={<Time value={evidence.fetchedAt} />} />
                  </dl>
                </article>
              </li>
            ))}
          </ol>
        ) : <ResearchEmptyState state={research.state} hasMarket={research.marketSnapshot !== null} />}
      </section>
    </section>
  );
}

function ResearchState({
  state,
  count,
}: {
  state: AnalysisResearchViewModel["state"];
  count: number;
}) {
  if (state === "unavailable") {
    return <span className="research-state is-unavailable"><CircleAlert size={15} aria-hidden="true" />检索不可用</span>;
  }
  if (state === "collecting") {
    return <span className="research-state is-collecting"><LoaderCircle className="spinning-icon" size={15} aria-hidden="true" />证据收集中</span>;
  }
  if (state === "available") {
    return <span className="research-state is-available">已验证 {count} 条来源</span>;
  }
  return <span className="research-state is-empty">暂无可验证来源</span>;
}

function ResearchEmptyState({
  state,
  hasMarket,
}: {
  state: AnalysisResearchViewModel["state"];
  hasMarket: boolean;
}) {
  if (state === "unavailable") {
    return (
      <div className="research-empty is-unavailable" role="status">
        <CircleAlert size={18} aria-hidden="true" />
        <div>
          <strong>本次检索未返回可验证来源</strong>
          <p>{hasMarket ? "市场快照仍可查看，但本次没有形成新的研究结论。" : "本次没有形成新的研究结论或分析建议。"}</p>
        </div>
      </div>
    );
  }
  if (state === "collecting") {
    return <p className="research-empty-copy">正在等待可验证的 Web 来源。</p>;
  }
  return <p className="research-empty-copy">本次运行没有可展示的 Web 来源。</p>;
}

function Metadata({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Time({ value }: { value: string }) {
  return <time dateTime={value}>{formatDateTime(value)}</time>;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function relationLabel(value: string): string {
  return ({
    supports: "支持判断",
    contradicts: "反向证据",
    context: "背景信息",
  } as Record<string, string>)[value] ?? value;
}
