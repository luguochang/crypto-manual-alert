"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { createManualRun } from "@/lib/api/system";
import { manualRunRequestSchema, type ManualRunResponse } from "@/lib/schemas/manual-run";
import {
  DIRECTION_LABEL,
  DIRECTION_TONE,
  classifyDirection,
  formatPrice
} from "@/app/shared/direction";

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "success"; traceId: string; result: ManualRunResponse }
  | { status: "error"; message: string };

const SYMBOL_SUGGESTIONS = ["ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"];

export function ManualRunForm() {
  const [symbol, setSymbol] = useState("ETH-USDT-SWAP");
  const [query, setQuery] = useState("评估 ETH 当前手动操作计划，给出多空/等待、触发价、止损和复核时间。");
  const [horizon, setHorizon] = useState("6h/12h/1d/3d");
  const [side, setSide] = useState<"long" | "short" | "flat" | "unknown">("unknown");
  const [entryPrice, setEntryPrice] = useState("");
  const [leverage, setLeverage] = useState("");
  const [riskMode, setRiskMode] = useState<"conservative" | "normal" | "aggressive">("normal");
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });

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
      setSubmitState({ status: "error", message: result.error.message });
      return;
    }

    setSubmitState({ status: "success", traceId: result.data.trace_id, result: result.data });
  }

  return (
    <section className="form-panel">
      <h2>手动提醒参数</h2>
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
          <label htmlFor="query">分析问题</label>
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
          {submitState.status === "submitting" ? "提交中" : "生成手动操作计划"}
        </button>
      </form>

      {submitState.status === "error" ? <p className="error-state">{submitState.message}</p> : null}

      {submitState.status === "success" ? (
        <div className="panel result-panel">
          <h2>返回结果</h2>
          {(() => {
            const plan = submitState.result.plan;
            const verdict = submitState.result.verdict;
            const direction = classifyDirection(plan.main_action);
            return (
              <>
                <div className={`alert-summary ${verdict.allowed ? "alert-allowed" : "alert-blocked"}`}>
                  <span className={`direction-badge ${DIRECTION_TONE[direction]}`}>
                    {DIRECTION_LABEL[direction]}
                  </span>
                  <div className="alert-summary-main">
                    <div className="alert-action">{plan.main_action}</div>
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

                {plan.manual_execution_required ? (
                  <p className="hint">系统仅给建议，需人工核对后手动执行；不自动下单。</p>
                ) : null}

                {verdict.reasons.length > 0 ? (
                  <div className="verdict-reasons">
                    <h3>{verdict.allowed ? "提示" : "阻断理由"}</h3>
                    <ul>
                      {verdict.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            );
          })()}
          <p className="hint">
            Trace ID: <code>{submitState.traceId}</code>
          </p>
          <Link className="button button-secondary" href={`/runs/${encodeURIComponent(submitState.traceId)}`}>
            查看 Trace
          </Link>
        </div>
      ) : null}
    </section>
  );
}
