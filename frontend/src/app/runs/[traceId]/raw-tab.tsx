import { JsonDetails } from "@/app/shared/json-details";
import type { LlmInteraction, PlanRun, TraceSpan } from "@/lib/schemas/runs";

type RawTabProps = {
  parsedPlan: Record<string, unknown>;
  verdict: Record<string, unknown>;
  planRun: PlanRun | null;
  analysis: Record<string, unknown>;
  spans: TraceSpan[];
  llmInteractions: LlmInteraction[];
};

function parseDiagnosticJson(value: string | undefined): unknown {
  if (!value) return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function compactLlmInteraction(item: LlmInteraction) {
  return {
    id: item.id,
    trace_id: item.trace_id,
    span_id: item.span_id,
    component: item.component,
    provider: item.provider,
    model: item.model,
    endpoint: item.endpoint,
    status: item.status,
    duration_ms: item.duration_ms,
    prompt_tokens: item.prompt_tokens,
    completion_tokens: item.completion_tokens,
    total_tokens: item.total_tokens,
    cost_usd: item.cost_usd,
    finish_reason: item.finish_reason,
    retry_count: item.retry_count,
    input_hash: item.input_hash,
    output_hash: item.output_hash,
    input_summary: item.input_summary,
    output_summary: item.output_summary,
    request_json: parseDiagnosticJson(item.request_json),
    response_json: parseDiagnosticJson(item.response_json),
    error_type: item.error_type,
    error_message: item.error_message,
    metadata: item.metadata
  };
}

function compactSpan(span: TraceSpan) {
  return {
    span_id: span.span_id,
    parent_span_id: span.parent_span_id,
    span_name: span.span_name,
    span_type: span.span_type,
    status: span.status,
    started_at: span.started_at,
    ended_at: span.ended_at,
    duration_ms: span.duration_ms,
    input_summary: span.input_summary,
    output_summary: span.output_summary,
    error_type: span.error_type,
    error_message: span.error_message,
    metadata: span.metadata
  };
}

function objectKeyCount(value: Record<string, unknown> | null | undefined) {
  return value ? Object.keys(value).length : 0;
}

export function RawTab({ parsedPlan, verdict, planRun, analysis, spans, llmInteractions }: RawTabProps) {
  const loadedPayloads = llmInteractions.filter((item) => item.request_json != null || item.response_json != null).length;
  const redactionStatus = planRun?.redaction?.payloads_included
    ? "后端已按显式诊断请求返回 payload，前端已应用展示层脱敏。"
    : "默认未加载完整 payload；前端仍会对展示内容应用展示层脱敏。";

  return (
    <section className="panel">
      <h2>原始数据</h2>
      <div className="mode-notice" aria-label="原始数据诊断说明">
        <strong>工程诊断</strong>
        <span>这是工程诊断视图，不是普通提醒详情；JSON 仅用于排障核对，默认业务页面不会要求阅读原始数据。</span>
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>开发者下钻用：展示后端已脱敏或摘要化的 payload、span 与 LLM 交互，便于核对完整链路。</p>
      <section className="audit-block section-gap" aria-labelledby="raw-summary-title" aria-label="原始数据摘要">
        <div className="section-heading-row">
          <div>
            <h3 id="raw-summary-title">原始数据摘要</h3>
            <p className="muted">{redactionStatus}</p>
          </div>
          <span className="badge badge-info">已应用展示层脱敏</span>
        </div>
        <dl className="audit-summary-strip">
          <div>
            <dt>计划字段</dt>
            <dd>{objectKeyCount(parsedPlan)} 项</dd>
          </div>
          <div>
            <dt>风控字段</dt>
            <dd>{objectKeyCount(verdict)} 项</dd>
          </div>
          <div>
            <dt>分析字段</dt>
            <dd>{objectKeyCount(analysis)} 项</dd>
          </div>
          <div>
            <dt>模型交互</dt>
            <dd>{llmInteractions.length} 次 / payload {loadedPayloads} 条</dd>
          </div>
          <div>
            <dt>Span</dt>
            <dd>{spans.length} 条</dd>
          </div>
          <div>
            <dt>展示策略</dt>
            <dd>摘要优先，JSON 折叠查看</dd>
          </div>
        </dl>
      </section>
      <div className="step-grid">
        <JsonDetails title="Parsed Plan" value={parsedPlan} large />
        <JsonDetails title="Verdict / Redaction" value={{ verdict, redaction: planRun?.redaction }} large />
        <JsonDetails title="Analysis" value={analysis} large />
        <JsonDetails title="LLM 交互" value={llmInteractions.map(compactLlmInteraction)} large />
        <JsonDetails title="Span 摘要" value={spans.map(compactSpan)} large />
      </div>
    </section>
  );
}
