"use client";

import {
  ChevronDown,
  CircleAlert,
  ExternalLink,
  Globe2,
  LoaderCircle,
  RadioTower,
} from "lucide-react";
import { useId, useState } from "react";

import type { AnalysisResearchViewModel } from "@/features/analysis/analysis-view-model";

const summaryPreviewCharacterLimit = 120;
const summaryPreviewMinimumBoundary = 72;

type WebEvidence = AnalysisResearchViewModel["webEvidence"][number];

export interface EvidenceSummaryDisclosure {
  full: string;
  preview: string;
  truncated: boolean;
}

export function evidenceSummaryDisclosure(summary: string): EvidenceSummaryDisclosure {
  const characters = Array.from(summary);
  if (characters.length <= summaryPreviewCharacterLimit) {
    return { full: summary, preview: summary, truncated: false };
  }

  let boundary = summaryPreviewCharacterLimit;
  for (let index = boundary - 1; index >= summaryPreviewMinimumBoundary; index -= 1) {
    if (/[.!?。！？；;]/.test(characters[index] ?? "")) {
      boundary = index + 1;
      break;
    }
  }
  if (boundary === summaryPreviewCharacterLimit) {
    for (let index = boundary - 1; index >= summaryPreviewMinimumBoundary; index -= 1) {
      if (/\s/.test(characters[index] ?? "")) {
        boundary = index;
        break;
      }
    }
  }

  return {
    full: summary,
    preview: `${characters.slice(0, boundary).join("").trimEnd()}…`,
    truncated: true,
  };
}

export function ResearchEvidence({ research }: { research: AnalysisResearchViewModel }) {
  const excludedCount = research.webEvidence.filter(
    (evidence) => evidence.relation.trim().toLowerCase() === "excluded",
  ).length;
  const effectiveCount = research.webEvidence.length - excludedCount;

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
        <ResearchState
          state={research.state}
          effectiveCount={effectiveCount}
          excludedCount={excludedCount}
        />
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
          {research.marketSnapshot.disclosure ? (
            <div className="research-empty is-unavailable" role="note">
              <CircleAlert size={18} aria-hidden="true" />
              <div>
                <strong>市场来源说明</strong>
                <p>{research.marketSnapshot.disclosure}</p>
              </div>
            </div>
          ) : null}
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
          <span>
            {effectiveCount} 条可用
            {excludedCount > 0 ? ` · ${excludedCount} 条已排除` : ""}
          </span>
        </div>

        {research.webEvidence.length > 0 ? (
          <ol className="web-evidence-list">
            {research.webEvidence.map((evidence, index) => (
              <li key={`${evidence.href}:${evidence.fetchedAt}:${index}`}>
                <EvidenceCard evidence={evidence} />
              </li>
            ))}
          </ol>
        ) : <ResearchEmptyState state={research.state} hasMarket={research.marketSnapshot !== null} />}
      </section>
    </section>
  );
}

function EvidenceCard({ evidence }: { evidence: WebEvidence }) {
  const [expanded, setExpanded] = useState(false);
  const summaryId = useId();
  const disclosure = evidenceSummaryDisclosure(evidence.summary);
  const summary = expanded ? disclosure.full : disclosure.preview;
  const action = expanded ? "收起" : "展开";
  const excluded = evidence.relation.trim().toLowerCase() === "excluded";

  return (
    <article
      className={`web-evidence-card${excluded ? " is-excluded" : ""}`}
      data-evidence-relation={evidence.relation}
    >
      <div className="evidence-source-row">
        <span>{evidence.provider}</span>
        <span className={excluded ? "is-excluded" : undefined}>
          {relationLabel(evidence.relation)}
        </span>
      </div>
      <h4>
        <a href={evidence.href} target="_blank" rel="noreferrer">
          {evidence.title}
          <ExternalLink size={15} aria-hidden="true" />
        </a>
      </h4>
      <p className="evidence-summary" id={summaryId} data-expanded={expanded}>
        {summary}
      </p>
      {disclosure.truncated ? (
        <button
          className="evidence-summary-toggle"
          type="button"
          aria-controls={summaryId}
          aria-expanded={expanded}
          aria-label={`${action}“${evidence.title}”的完整摘要`}
          onClick={() => setExpanded((current) => !current)}
        >
          <ChevronDown size={16} aria-hidden="true" />
          <span>{expanded ? "收起完整摘要" : "展开完整摘要"}</span>
        </button>
      ) : null}
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
  );
}

function ResearchState({
  state,
  effectiveCount,
  excludedCount,
}: {
  state: AnalysisResearchViewModel["state"];
  effectiveCount: number;
  excludedCount: number;
}) {
  if (state === "unavailable") {
    return <span className="research-state is-unavailable"><CircleAlert size={15} aria-hidden="true" />检索不可用</span>;
  }
  if (state === "collecting") {
    return <span className="research-state is-collecting"><LoaderCircle className="spinning-icon" size={15} aria-hidden="true" />证据收集中</span>;
  }
  if (state === "partial") {
    return <span className="research-state is-partial"><CircleAlert size={15} aria-hidden="true" />已保留 {effectiveCount} 条来源，研究未完成</span>;
  }
  if (state === "available") {
    return (
      <span className="research-state is-available">
        已验证 {effectiveCount} 条来源
        {excludedCount > 0 ? `，另排除 ${excludedCount} 条` : ""}
      </span>
    );
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
    market_snapshot: "市场行情",
    excluded: "已排除（相关性不足）",
  } as Record<string, string>)[value] ?? value;
}
