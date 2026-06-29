import Link from "next/link";
import { getRunDetail } from "@/lib/api/runs";
import { StatusBadge } from "@/app/shared/status-badge";

export const dynamic = "force-dynamic";

type TraceDetailPageProps = {
  params: Promise<{
    traceId: string;
  }>;
};

function formatJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

function shortHash(value: string | undefined) {
  if (!value) {
    return "-";
  }
  return value.length > 16 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return formatJson(value);
}

export default async function TraceDetailPage({ params }: TraceDetailPageProps) {
  const { traceId } = await params;
  const result = await getRunDetail(traceId, { includePayloads: true });

  if (!result.ok) {
    return (
      <>
        <header className="page-header">
          <div>
            <h1>Trace 详情</h1>
            <p>Trace ID: {traceId}</p>
          </div>
          <Link className="button button-secondary" href="/runs">
            返回列表
          </Link>
        </header>
        <div className="error-state">{result.error.message}</div>
      </>
    );
  }

  const detail = result.data;
  const trace = detail.trace;
  const planRun = detail.plan_run;
  const parsedPlan = planRun?.parsed_plan ?? {};
  const verdict = planRun?.verdict ?? {};
  const analysis = detail.analysis ?? {};
  const spans = detail.spans ?? [];
  const llmInteractions = detail.llm_interactions ?? [];
  const badcases = detail.badcases ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Trace 详情</h1>
          <p>Trace ID: {trace.trace_id}</p>
        </div>
        <Link className="button button-secondary" href="/runs">
          返回列表
        </Link>
      </header>

      <section className="trace-summary-grid" aria-label="Trace 摘要">
        <div className="stat-card">
          <span>运行状态</span>
          <strong>
            <StatusBadge status={trace.status} />
          </strong>
        </div>
        <div className="stat-card">
          <span>最终动作</span>
          <strong>{trace.final_action ?? "-"}</strong>
        </div>
        <div className="stat-card">
          <span>Span 数</span>
          <strong>{spans.length}</strong>
        </div>
        <div className="stat-card">
          <span>LLM 调用</span>
          <strong>{llmInteractions.length}</strong>
        </div>
      </section>

      <div className="grid-2 section-gap">
        <section className="panel">
          <h2>运行信息</h2>
          <dl className="detail-list">
            <div>
              <dt>交易对</dt>
              <dd>{trace.symbol}</dd>
            </div>
            <div>
              <dt>运行类型</dt>
              <dd>{trace.run_type}</dd>
            </div>
            <div>
              <dt>风控允许</dt>
              <dd>{trace.allowed == null ? "-" : trace.allowed ? "是" : "否"}</dd>
            </div>
            <div>
              <dt>Plan ID</dt>
              <dd>{trace.final_plan_id ?? planRun?.plan_id ?? "-"}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{trace.created_at}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{trace.ended_at ?? "-"}</dd>
            </div>
          </dl>
        </section>

        <section className="panel">
          <h2>结论摘要</h2>
          <dl className="detail-list">
            <div>
              <dt>主结论</dt>
              <dd>{valueText(parsedPlan.main_action)}</dd>
            </div>
            <div>
              <dt>概率</dt>
              <dd>{valueText(parsedPlan.probability)}</dd>
            </div>
            <div>
              <dt>入场/触发</dt>
              <dd>{valueText(parsedPlan.entry_trigger)}</dd>
            </div>
            <div>
              <dt>止损</dt>
              <dd>{valueText(parsedPlan.stop_price)}</dd>
            </div>
            <div>
              <dt>目标</dt>
              <dd>
                {valueText(parsedPlan.target_1)} / {valueText(parsedPlan.target_2)}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="panel section-gap">
        <h2>分析过程</h2>
        <div className="analysis-grid">
          <div>
            <h3>推理摘要</h3>
            <p className="analysis-text">{valueText(analysis.reasoning_summary)}</p>
          </div>
          <div>
            <h3>反向观点</h3>
            <p className="analysis-text">{valueText(analysis.opposing_thesis)}</p>
          </div>
          <div>
            <h3>数据缺口</h3>
            <pre className="code-box light-code">{formatJson(analysis.data_gaps ?? [])}</pre>
          </div>
          <div>
            <h3>风控命中</h3>
            <pre className="code-box light-code">{formatJson(analysis.risk_rule_hits ?? verdict)}</pre>
          </div>
        </div>
      </section>

      <section className="panel section-gap">
        <h2>执行时间线</h2>
        <div className="timeline-list">
          {spans.map((span, index) => (
            <details className="trace-step" key={span.span_id} open={index < 3}>
              <summary>
                <span>{index + 1}. {span.span_name}</span>
                <span>{span.status}</span>
                <span>{span.duration_ms} ms</span>
              </summary>
              <div className="step-grid">
                <div>
                  <h3>输入摘要</h3>
                  <pre className="code-box">{formatJson(span.input_summary)}</pre>
                </div>
                <div>
                  <h3>输出摘要</h3>
                  <pre className="code-box">{formatJson(span.output_summary)}</pre>
                </div>
              </div>
              {span.error_message ? <p className="error-state">{span.error_message}</p> : null}
            </details>
          ))}
        </div>
      </section>

      <section className="panel section-gap">
        <h2>LLM 请求与返回</h2>
        {llmInteractions.length === 0 ? (
          <p className="muted">
            当前 trace 没有 LLM 交互记录。默认 fixture 决策不会调用真实模型；使用 openai_compatible / LLM research 后会记录。
          </p>
        ) : (
          <div className="timeline-list">
            {llmInteractions.map((item) => (
              <details className="trace-step" key={item.id} open>
                <summary>
                  <span>{item.component}</span>
                  <span>{item.provider} / {item.model}</span>
                  <span>{item.status}</span>
                </summary>
                <dl className="detail-list compact-list">
                  <div>
                    <dt>输入 Hash</dt>
                    <dd>{shortHash(item.input_hash)}</dd>
                  </div>
                  <div>
                    <dt>输出 Hash</dt>
                    <dd>{shortHash(item.output_hash)}</dd>
                  </div>
                </dl>
                <div className="step-grid">
                  <div>
                    <h3>请求摘要</h3>
                    <pre className="code-box">{formatJson(item.input_summary)}</pre>
                  </div>
                  <div>
                    <h3>返回摘要</h3>
                    <pre className="code-box">{formatJson(item.output_summary)}</pre>
                  </div>
                  <div>
                    <h3>脱敏请求 Payload</h3>
                    <pre className="code-box large-code">{item.request_json ?? "未请求 include_payloads"}</pre>
                  </div>
                  <div>
                    <h3>脱敏返回 Payload</h3>
                    <pre className="code-box large-code">{item.response_json ?? "未请求 include_payloads"}</pre>
                  </div>
                </div>
                {item.error_message ? <p className="error-state">{item.error_message}</p> : null}
              </details>
            ))}
          </div>
        )}
      </section>

      <section className="panel section-gap">
        <h2>Badcase 与回流</h2>
        {badcases.length === 0 ? (
          <p className="muted">暂无人工复核 badcase。后续 eval 页面会把这里的记录沉淀为回归集。</p>
        ) : (
          <pre className="code-box">{formatJson(badcases)}</pre>
        )}
      </section>

      <section className="panel section-gap">
        <h2>原始结构化结果</h2>
        <div className="step-grid">
          <div>
            <h3>Parsed Plan</h3>
            <pre className="code-box large-code">{formatJson(parsedPlan)}</pre>
          </div>
          <div>
            <h3>Verdict / Redaction</h3>
            <pre className="code-box large-code">{formatJson({ verdict, redaction: planRun?.redaction })}</pre>
          </div>
        </div>
      </section>
    </>
  );
}
