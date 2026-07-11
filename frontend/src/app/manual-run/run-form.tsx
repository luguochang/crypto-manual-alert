"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { createManualRun } from "@/lib/api/system";
import { manualRunRequestSchema, type ManualRunResponse } from "@/lib/schemas/manual-run";
import {
  DIRECTION_LABEL,
  DIRECTION_TONE,
  classifyDirection,
  formatPrice
} from "@/app/shared/direction";
import {
  productDecisionLabel,
  productDisplayItems,
  productDisplayText
} from "@/app/shared/product-copy";
import {
  EvidenceSummaryPanel,
  GenerationSummaryPanel,
  ModelConclusionPanel,
  ModelReviewPanel,
  ProofLevelPanel,
  TradingDataStatusPanel
} from "@/app/shared/summary-projections";

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "success"; traceId: string; result: ManualRunResponse; focusText: string }
  | { status: "error"; message: string };

const SYMBOL_SUGGESTIONS = ["ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"];

function notificationTone(status: string): string {
  if (status === "sent") return "badge-success";
  if (status === "failed") return "badge-failed";
  return "badge-pending";
}

function notificationLabel(status: string): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  if (status === "disabled") return "通知未启用";
  return "未记录";
}

function resultReviewTone(status: string): string {
  if (status === "scorable") return "badge-success";
  if (status === "unscorable") return "badge-failed";
  return "badge-pending";
}

export function ManualRunForm() {
  const [symbol, setSymbol] = useState("ETH-USDT-SWAP");
  const [query, setQuery] = useState("重点关注 ETH 当前持仓风险、触发价、止损和复核时间。");
  const [horizon, setHorizon] = useState("6h/12h/1d/3d");
  const [side, setSide] = useState<"long" | "short" | "flat" | "unknown">("unknown");
  const [entryPrice, setEntryPrice] = useState("");
  const [leverage, setLeverage] = useState("");
  const [riskMode, setRiskMode] = useState<"conservative" | "normal" | "aggressive">("normal");
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });
  const resultPanelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (submitState.status !== "success") return;
    const frameId = window.requestAnimationFrame(() => {
      resultPanelRef.current?.scrollIntoView({ block: "start", behavior: "auto" });
      resultPanelRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [submitState.status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitState({ status: "submitting" });

    const parsed = manualRunRequestSchema.safeParse({
      symbol,
      query,
      horizon,
      alert_channel: "bark",
      position: {
        side,
        entry_price: entryPrice || undefined,
        leverage: leverage || undefined
      },
      risk_mode: riskMode
    });

    if (!parsed.success) {
      setSubmitState({
        status: "error",
        message: parsed.error.issues[0]?.message ?? "表单参数不合法"
      });
      return;
    }

    const result = await createManualRun(parsed.data);

    if (!result.ok) {
      setSubmitState({
        status: "error",
        message: "提醒暂时生成失败，无法确认是否写入记录；请在提醒记录中核对，或稍后重试。"
      });
      return;
    }

    setSubmitState({ status: "success", traceId: result.data.trace_id, result: result.data, focusText: parsed.data.query });
  }

  return (
    <section className="form-panel">
      <h2>提醒参数</h2>
      <p className="muted">
        关注点会记录为本次复核备注；当前主计划仍由交易对、周期、持仓和配置驱动，系统不会自动下单。
      </p>
      <form className="form-grid" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="symbol">交易对</label>
          <input
            id="symbol"
            list="symbol-suggestions"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="如 ETH-USDT-SWAP"
          />
          <datalist id="symbol-suggestions">
            {SYMBOL_SUGGESTIONS.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </div>

        <div className="field">
          <label htmlFor="query">关注点</label>
          <textarea id="query" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="horizon">周期</label>
            <input id="horizon" value={horizon} onChange={(event) => setHorizon(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="riskMode">风险模式</label>
            <select
              id="riskMode"
              value={riskMode}
              onChange={(event) => setRiskMode(event.target.value as typeof riskMode)}
            >
              <option value="conservative">保守</option>
              <option value="normal">普通</option>
              <option value="aggressive">激进</option>
            </select>
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="side">当前持仓</label>
            <select id="side" value={side} onChange={(event) => setSide(event.target.value as typeof side)}>
              <option value="unknown">未说明</option>
              <option value="long">已有多单</option>
              <option value="short">已有空单</option>
              <option value="flat">空仓</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="entryPrice">持仓均价</label>
            <input
              id="entryPrice"
              inputMode="decimal"
              placeholder="可选"
              value={entryPrice}
              onChange={(event) => setEntryPrice(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="leverage">杠杆</label>
            <input
              id="leverage"
              inputMode="decimal"
              placeholder="最高 2"
              value={leverage}
              onChange={(event) => setLeverage(event.target.value)}
            />
          </div>
        </div>

        <button className="button" disabled={submitState.status === "submitting"} type="submit">
          {submitState.status === "submitting" ? "提交中" : "生成提醒建议"}
        </button>
        {submitState.status === "submitting" ? (
          <p className="async-progress" role="status" aria-label="提醒生成进度">
            正在生成提醒建议，请不要重复提交。系统只生成提醒，不会自动下单。
          </p>
        ) : null}
      </form>

      {submitState.status === "error" ? <p className="error-state" role="alert">{submitState.message}</p> : null}

      {submitState.status === "success" ? (
        <div className="panel result-panel" ref={resultPanelRef} tabIndex={-1} aria-live="polite">
          <h2>本次提醒建议</h2>
          {(() => {
            const plan = submitState.result.plan;
            const verdict = submitState.result.verdict;
            const summary = submitState.result.business_summary;
            const resultReview = submitState.result.result_review;
            const direction = classifyDirection(plan.main_action);
            return (
              <>
                <div className={`alert-summary ${verdict.allowed ? "alert-allowed" : "alert-blocked"}`}>
                  <span className={`direction-badge ${DIRECTION_TONE[direction]}`}>
                    {DIRECTION_LABEL[direction]}
                  </span>
                  <div className="alert-summary-main">
                    <div className="alert-action">{productDisplayText(plan.main_action)}</div>
                    <div className="alert-meta">
                      <span>{plan.instrument}</span>
                      {plan.horizon ? <span> · 周期 {plan.horizon}</span> : null}
                      {plan.probability !== null && plan.probability !== undefined ? (
                        <span> · 概率 {(plan.probability * 100).toFixed(0)}%</span>
                      ) : null}
                      <span> · {verdict.allowed ? "允许手动核对" : "已阻断"}</span>
                    </div>
                  </div>
                </div>
                <ModelConclusionPanel summary={summary.generation_summary} />
                <dl className="detail-list price-grid">
                  <div>
                    <dt>参考价</dt>
                    <dd>{formatPrice(plan.reference_price)}</dd>
                  </div>
                  <div>
                    <dt>触发价</dt>
                    <dd>{formatPrice(plan.entry_trigger)}</dd>
                  </div>
                  <div>
                    <dt>止损</dt>
                    <dd>{formatPrice(plan.stop_price)}</dd>
                  </div>
                  <div>
                    <dt>目标 1</dt>
                    <dd>{formatPrice(plan.target_1)}</dd>
                  </div>
                  <div>
                    <dt>目标 2</dt>
                    <dd>{formatPrice(plan.target_2)}</dd>
                  </div>
                  <div>
                    <dt>过期时间</dt>
                    <dd>{plan.expires_at ? new Date(plan.expires_at).toLocaleString() : "—"}</dd>
                  </div>
                </dl>
                <div className="mode-notice">
                  <strong>{productDecisionLabel(summary.decision_label)}</strong>
                  <span>{productDisplayText(summary.mode_notice)}</span>
                </div>
                <TradingDataStatusPanel status={summary.market_data_status} />
                <ProofLevelPanel summary={summary} />

                {plan.manual_execution_required ? (
                  <p className="hint">系统仅给建议，需人工核对后手动执行；不自动下单。</p>
                ) : null}

                {verdict.reasons.length > 0 ? (
                  <div className="verdict-reasons">
                    <h3>{verdict.allowed ? "提示" : "阻断理由"}</h3>
                    <ul>
                      {productDisplayItems(verdict.reasons).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="analysis-grid section-gap">
                  <div>
                    <h3>为什么</h3>
                    <ul>
                      {productDisplayItems(summary.reason_bullets, 4).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <div>
                    <h3>风险 / 缺口</h3>
                    <ul>
                      {productDisplayItems([...summary.risk_bullets, ...summary.data_gap_bullets], 5).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <EvidenceSummaryPanel bullets={summary.evidence_bullets} />
                  <ModelReviewPanel
                    summary={summary.generation_summary}
                    evidenceBullets={summary.evidence_bullets}
                    focusText={submitState.focusText}
                  />
                  <div>
                    <h3>生成链路</h3>
                    <span className="badge badge-info">{productDisplayText(summary.generation_summary.mode_label)}</span>
                    <strong className="analysis-text">{productDisplayText(summary.generation_summary.status_label)}</strong>
                    <p className="analysis-text">{productDisplayText(summary.generation_summary.response_summary)}</p>
                    <ul>
                      {productDisplayItems(summary.generation_summary.detail_bullets, 5).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                  <GenerationSummaryPanel summary={summary.generation_summary} />
                  <div>
                    <h3>下一步</h3>
                    <ul>
                      {productDisplayItems(summary.next_steps).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <div>
                    <h3>通知</h3>
                    <span className={`badge ${notificationTone(summary.notification.status)}`}>
                      {notificationLabel(summary.notification.status)}
                    </span>
                    <p className="analysis-text">{productDisplayText(summary.notification.message)}</p>
                  </div>
                  <div aria-label="后续复盘">
                    <h3>后续复盘</h3>
                    <span className={`badge ${resultReviewTone(resultReview.status)}`}>
                      {productDisplayText(resultReview.label)}
                    </span>
                    <strong className="analysis-text">
                      {resultReview.status === "not_collected" ? "结果尚未生成" : productDisplayText(resultReview.label)}
                    </strong>
                    <p className="analysis-text">{productDisplayText(resultReview.message)}</p>
                    <p className="muted">结果样本 {resultReview.sample_count} 条</p>
                  </div>
                </div>
              </>
            );
          })()}
          <div className="route-state-actions">
            <Link className="button button-secondary" href={`/runs/${encodeURIComponent(submitState.traceId)}`} prefetch={false}>
              查看详情
            </Link>
            <Link className="button button-secondary" href={`/runs?latest=${encodeURIComponent(submitState.traceId)}`} prefetch={false}>
              查看记录
            </Link>
          </div>
        </div>
      ) : null}
    </section>
  );
}
