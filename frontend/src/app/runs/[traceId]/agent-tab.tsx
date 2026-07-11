import { AgentAuditPanel } from "./agent-audit-panel";
import { safeDisplayError } from "@/app/shared/safe-error";
import { metricText, moneyText } from "./format-helpers";
import type { AgentAuditView, LlmInteraction, TraceSpan } from "@/lib/schemas/runs";

type AgentTabProps = {
  agentAudit: AgentAuditView | undefined;
  spans: TraceSpan[];
  llmInteractions: LlmInteraction[];
};

export function AgentTab({ agentAudit, spans, llmInteractions }: AgentTabProps) {
  const totalTokens = llmInteractions.reduce((s, i) => s + (i.total_tokens ?? 0), 0);
  const totalCost = llmInteractions.reduce((s, i) => s + (i.cost_usd ?? 0), 0);
  const minStart = spans.length > 0 ? Math.min(...spans.map((s) => Date.parse(s.started_at) || 0)) : 0;
  const maxEnd = spans.length > 0 ? Math.max(...spans.map((s) => Date.parse(s.ended_at) || 0)) : 0;
  const spanWindow = Math.max(1, maxEnd - minStart);
  const failedSpans = spans.filter((span) => span.status === "error").length;
  const warningSpans = spans.filter((span) => span.status !== "ok" && span.status !== "error").length;
  const hardBlocks = agentAudit?.workers.filter((worker) => worker.hard_block).length ?? 0;
  const productionMode = agentAudit?.input_lineage.production_final_input_mode ?? "未记录";
  const decisionEffect = agentAudit?.decision_effect ?? "未记录";

  return (
    <>
      <section className="panel section-gap" aria-labelledby="diagnostic-summary-title" aria-label="工程诊断摘要">
        <div className="section-heading-row">
          <div>
            <h2 id="diagnostic-summary-title">工程诊断摘要</h2>
            <p className="muted">先确认主链、模型调用、审查 worker 和异常数量；下方矩阵与时间线只用于工程追踪。</p>
          </div>
          <span className={agentAudit?.available ? "badge badge-success" : "badge badge-pending"}>
            {agentAudit?.available ? "审计可见" : "未记录审计"}
          </span>
        </div>
        <dl className="audit-summary-strip">
          <div>
            <dt>生产主链</dt>
            <dd>{productionMode}</dd>
          </div>
          <div>
            <dt>候选影响</dt>
            <dd>{decisionEffect}</dd>
          </div>
          <div>
            <dt>模型调用</dt>
            <dd>{llmInteractions.length} 次 / {totalTokens} tokens</dd>
          </div>
          <div>
            <dt>执行耗时</dt>
            <dd>{spans.length} spans / {metricText(maxEnd && minStart ? maxEnd - minStart : 0, "ms")}</dd>
          </div>
          <div>
            <dt>Worker 审查</dt>
            <dd>{agentAudit?.workers.length ?? 0} 个 / {hardBlocks} 个硬阻断</dd>
          </div>
          <div>
            <dt>异常摘要</dt>
            <dd>{failedSpans} 错误 / {warningSpans} 提醒</dd>
          </div>
        </dl>
      </section>

      <AgentAuditPanel agentAudit={agentAudit} />

      <section className="panel section-gap">
        <div className="section-heading-row">
          <div>
            <h2>Span 时间线</h2>
            <p className="muted">Agent 执行火焰图：按耗时占比可视化每个 span，展开查看输入/输出摘要与错误。</p>
          </div>
          <span className="badge badge-neutral">{spans.length} spans</span>
        </div>
        {spans.length === 0 ? (
          <p className="muted">无 span 记录。</p>
        ) : (
          <div className="flame-timeline">
            {spans.map((span) => {
              const start = Date.parse(span.started_at) || minStart;
              const offsetPct = minStart ? Math.max(0, ((start - minStart) / spanWindow) * 100) : 0;
              const widthPct = Math.max(2, (span.duration_ms / Math.max(1, maxEnd - minStart || span.duration_ms)) * 100);
              const tone = span.status === "ok" ? "ok" : span.status === "error" ? "err" : "warn";
              const hasError = Boolean(span.error_type || span.error_message);
              const hasPayload = span.input_summary != null || span.output_summary != null || hasError;
              return (
                <details className="flame-row" key={span.span_id} open={span.status !== "ok"}>
                  <summary className="flame-summary">
                    <span className="flame-label">{span.span_name}</span>
                    <span className="flame-bar">
                      <span
                        className={`flame-fill ${tone}`}
                        style={{ left: `${offsetPct}%`, width: `${Math.min(widthPct, 100 - offsetPct)}%` }}
                      />
                    </span>
                    <span className="flame-duration">{span.duration_ms} ms · {span.status}</span>
                  </summary>
                  {hasPayload ? (
                    <div className="flame-detail">
                      {span.input_summary != null ? (
                        <ReadableSummary title="输入摘要" value={span.input_summary} />
                      ) : null}
                      {span.output_summary != null ? (
                        <ReadableSummary title="输出摘要" value={span.output_summary} />
                      ) : null}
                      {hasError ? (
                        <div className="error-note">
                          <strong>{safeDisplayError(span.error_type ?? "error", "执行异常")}</strong>
                          {span.error_message ? (
                            <span> — {safeDisplayError(span.error_message, "错误详情已记录，可在服务日志中排查。")}</span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </details>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel section-gap">
        <div className="section-heading-row">
          <div>
            <h2>LLM 调用</h2>
            <p className="muted">每次 LLM 交互的模型、token、成本、耗时与重试；默认只展示安全摘录，完整 payload 仅 Raw 视图显式加载。</p>
          </div>
          <div className="status-bar" style={{ margin: 0, padding: "6px 12px", border: "none", background: "transparent" }}>
            <span className="status-item">tokens <strong>{totalTokens}</strong></span>
            <span className="status-item">cost <strong>{moneyText(totalCost)}</strong></span>
            <span className="status-item">calls <strong>{llmInteractions.length}</strong></span>
          </div>
        </div>
        {llmInteractions.length === 0 ? (
          <p className="muted">无 LLM 交互记录（默认 fixture 引擎不产生 LLM 调用）。</p>
        ) : (
          <div className="llm-call-list">
            {llmInteractions.map((item) => {
              return (
                <details
                  key={item.id}
                  className={`llm-call-row ${item.status !== "ok" ? "worker-failed" : ""}`}
                  open={item.status !== "ok"}
                >
                  <summary className="llm-call-summary">
                    <span className="mono-cell">#{item.id}</span>
                    <span>{item.component}</span>
                    <span className="mono-cell">{item.provider} / {item.model}</span>
                    <span className={`badge ${item.status === "ok" ? "badge-success" : "badge-failed"}`}>{item.status}</span>
                    <span className="mono-cell">{metricText(item.duration_ms, "ms")}</span>
                    <span className="mono-cell">{metricText(item.total_tokens)} tok</span>
                    <span className="mono-cell">{moneyText(item.cost_usd)}</span>
                    <span className="mono-cell">retry {item.retry_count}</span>
                    {item.error_type ? <span className="error-note-inline">{item.error_type}</span> : null}
                  </summary>
                  <div className="llm-call-payloads">
                    <ReadableSummary
                      title="请求摘要"
                      value={item.input_summary}
                      meta={[
                        ["输入指纹", item.input_hash],
                        ["完整请求", "仅 Raw 视图显式加载"]
                      ]}
                    />
                    <ReadableSummary
                      title="响应摘要"
                      value={item.completion_excerpt ?? item.output_summary}
                      meta={[
                        ["输出指纹", item.output_hash],
                        ["完整响应", "仅 Raw 视图显式加载"]
                      ]}
                    />
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}

function ReadableSummary({
  title,
  value,
  meta = []
}: {
  title: string;
  value: unknown;
  meta?: Array<[string, unknown]>;
}) {
  return (
    <section className="trace-step light-code" aria-label={title}>
      <div className="trace-step-title">
        <span>{title}</span>
        <span>摘要</span>
      </div>
      <p className="muted">{summaryText(value)}</p>
      {meta.length > 0 ? (
        <dl className="detail-list compact-list">
          {meta.map(([label, item]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{summaryText(item)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

function summaryText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "未记录";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return safeDisplayError(String(value), "摘要已记录，原始内容已隐藏。");
  }
  if (Array.isArray(value)) {
    const scalars = value
      .filter((item) => ["string", "number", "boolean"].includes(typeof item))
      .slice(0, 4)
      .map(String);
    return scalars.length > 0
      ? safeDisplayError(scalars.join(", "), "摘要已记录，原始内容已隐藏。")
      : "结构化摘要已记录，请在 Raw 视图按需展开。";
  }
  return "结构化摘要已记录，请在 Raw 视图按需展开。";
}
