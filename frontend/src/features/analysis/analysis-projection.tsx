"use client";

import {
  CircleCheck,
  CircleOff,
  Clock3,
  LoaderCircle,
  OctagonAlert,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AnalysisResult } from "@/features/analysis/analysis-result";
import { ResearchEvidence } from "@/features/analysis/research-evidence";
import { toAnalysisViewModel, type AnalysisStatusViewModel } from "@/features/analysis/analysis-view-model";
import type { ProductTask } from "@/lib/schemas/product-api";

interface AnalysisProjectionProps {
  task: ProductTask;
  onRetry?: () => void;
  retrying?: boolean;
}

export function AnalysisProjection({ task, onRetry, retrying = false }: AnalysisProjectionProps) {
  const [now, setNow] = useState(() => new Date());
  const viewModel = toAnalysisViewModel(task, now);
  const expiresAt = viewModel.result?.validity.expiresAt ?? null;

  useEffect(() => {
    if (!expiresAt) return;
    const remainingMilliseconds = Date.parse(expiresAt) - now.getTime();
    if (remainingMilliseconds <= 0) return;

    const timeout = window.setTimeout(
      () => setNow(new Date()),
      Math.min(remainingMilliseconds + 1, 1_000),
    );
    return () => window.clearTimeout(timeout);
  }, [expiresAt, now]);

  return (
    <div className="projection-stack">
      <section className={`status-panel tone-${viewModel.status.tone}`} data-testid="task-status" aria-live="polite">
        <span className="status-icon" aria-hidden="true">{statusIcon(viewModel.status)}</span>
        <div>
          <div className="status-title-row">
            <h2>{viewModel.status.label}</h2>
            <span>{viewModel.symbol.replace("-USDT-SWAP", "")} · {viewModel.horizon}</span>
          </div>
          <p>{viewModel.status.description}</p>
        </div>
      </section>

      {viewModel.failure ? (
        <section className="failure-panel" role="alert">
          <div className="failure-heading">
            <OctagonAlert size={21} aria-hidden="true" />
            <div>
              <h2>{viewModel.failure.title}</h2>
              <span>{viewModel.failure.code}</span>
            </div>
          </div>
          <p>{viewModel.failure.message}</p>
          {viewModel.failure.explanation ? (
            <p className="failure-explanation">{viewModel.failure.explanation}</p>
          ) : null}
          {viewModel.failure.provider || viewModel.failure.errorType || viewModel.failure.attempt ? (
            <dl className="failure-diagnostics" aria-label="失败诊断">
              {viewModel.failure.provider ? (
                <div><dt>Provider</dt><dd>{viewModel.failure.provider}</dd></div>
              ) : null}
              {viewModel.failure.errorType ? (
                <div><dt>错误类型</dt><dd>{viewModel.failure.errorType}</dd></div>
              ) : null}
              {viewModel.failure.attempt ? (
                <div><dt>尝试次数</dt><dd>第 {viewModel.failure.attempt} 次尝试</dd></div>
              ) : null}
            </dl>
          ) : null}
          {viewModel.failure.retryable && onRetry ? (
            <button className="retry-button" type="button" onClick={onRetry} disabled={retrying}>
              <RotateCcw size={17} aria-hidden="true" />
              {retrying ? "正在重新提交" : "重新分析"}
            </button>
          ) : null}
        </section>
      ) : null}

      {viewModel.incompleteMessage ? (
        <section className="incomplete-panel" role="status">
          <ShieldAlert size={20} aria-hidden="true" />
          <p>{viewModel.incompleteMessage}</p>
        </section>
      ) : null}

      {shouldShowResearch(task, viewModel.research) ? (
        <ResearchEvidence research={viewModel.research} />
      ) : null}

      {viewModel.result ? <AnalysisResult result={viewModel.result} /> : null}
    </div>
  );
}

function shouldShowResearch(
  task: ProductTask,
  research: ReturnType<typeof toAnalysisViewModel>["research"],
) {
  return research.marketSnapshot !== null
    || research.webEvidence.length > 0
    || research.state === "unavailable"
    || task.status === "running";
}

function statusIcon(status: AnalysisStatusViewModel) {
  const common = { size: 22, strokeWidth: 1.8 };
  if (status.expired) return <OctagonAlert {...common} />;

  switch (status.value) {
    case "queued":
      return <Clock3 {...common} />;
    case "running":
      return <LoaderCircle {...common} className="spinning-icon" />;
    case "waiting_human":
      return <ShieldAlert {...common} />;
    case "succeeded":
      return <CircleCheck {...common} />;
    case "cancelled":
      return <CircleOff {...common} />;
    default:
      return <OctagonAlert {...common} />;
  }
}
