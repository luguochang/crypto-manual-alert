import { AgentAuditPanel } from "./agent-audit-panel";
import { JsonDetails } from "@/app/shared/json-details";
import { metricText, moneyText } from "./format-helpers";
import type { AgentAuditView, LlmInteraction, TraceSpan } from "@/lib/schemas/runs";

type AgentTabProps = {
  agentAudit: AgentAuditView | undefined;
  spans: TraceSpan[];
  llmInteractions: LlmInteraction[];
};

function tryParseJson(value: string | undefined | null): unknown {
  if (!value) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

export function AgentTab({ agentAudit, spans, llmInteractions }: AgentTabProps) {
  const totalTokens = llmInteractions.reduce((s, i) => s + (i.total_tokens ?? 0), 0);
  const totalCost = llmInteractions.reduce((s, i) => s + (i.cost_usd ?? 0), 0);
  const minStart = spans.length > 0 ? Math.min(...spans.map((s) => Date.parse(s.started_at) || 0)) : 0;
  const maxEnd = spans.length > 0 ? Math.max(...spans.map((s) => Date.parse(s.ended_at) || 0)) : 0;
  const spanWindow = Math.max(1, maxEnd - minStart);

  return (
    <>
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
                  <summary style={{ display: "contents" }}>
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
                        <JsonDetails title="输入摘要" value={span.input_summary} light />
                      ) : null}
                      {span.output_summary != null ? (
                        <JsonDetails title="输出摘要" value={span.output_summary} light />
                      ) : null}
                      {hasError ? (
                        <div className="error-note">
                          <strong>{span.error_type ?? "error"}</strong>
                          {span.error_message ? <span> — {span.error_message}</span> : null}
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
            <p className="muted">每次 LLM 交互的模型、token、成本、耗时与重试；展开查看脱敏请求/响应正文。</p>
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
              const request = tryParseJson(item.request_json);
              const response = tryParseJson(item.response_json);
              const hasPayload = request != null || response != null;
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
                  {hasPayload ? (
                    <div className="llm-call-payloads">
                      {request != null ? <JsonDetails title="请求正文（脱敏）" value={request} large /> : null}
                      {response != null ? <JsonDetails title="响应正文（脱敏）" value={response} large /> : null}
                    </div>
                  ) : null}
                </details>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
