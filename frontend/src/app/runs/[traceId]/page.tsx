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

export default async function TraceDetailPage({ params }: TraceDetailPageProps) {
  const { traceId } = await params;
  const result = await getRunDetail(traceId);

  if (!result.ok) {
    return (
      <>
        <header className="page-header">
          <div>
            <h1>Trace Detail</h1>
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
  const parsedPlan = detail.plan_run?.parsed_plan;
  const spans = detail.spans ?? [];
  const llmInteractions = detail.llm_interactions ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Trace Detail</h1>
          <p>Trace ID: {trace.trace_id}</p>
        </div>
        <Link className="button button-secondary" href="/runs">
          返回列表
        </Link>
      </header>

      <div className="grid-2">
        <section className="panel">
          <h2>运行信息</h2>
          <dl className="detail-list">
            <div>
              <dt>状态</dt>
              <dd>
                <StatusBadge status={trace.status} />
              </dd>
            </div>
            <div>
              <dt>交易对</dt>
              <dd>{trace.symbol}</dd>
            </div>
            <div>
              <dt>最终动作</dt>
              <dd>{trace.final_action ?? "-"}</dd>
            </div>
            <div>
              <dt>风控允许</dt>
              <dd>{trace.allowed == null ? "-" : trace.allowed ? "是" : "否"}</dd>
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
          <h2>计划摘要</h2>
          <pre className="code-box">{formatJson(parsedPlan)}</pre>
        </section>
      </div>

      <section className="panel section-gap">
        <h2>执行时间线</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Step</th>
                <th>状态</th>
                <th>耗时</th>
                <th>输入摘要</th>
                <th>输出摘要</th>
              </tr>
            </thead>
            <tbody>
              {spans.map((span) => (
                <tr key={span.span_id}>
                  <td>{span.span_name}</td>
                  <td>{span.status}</td>
                  <td>{span.duration_ms} ms</td>
                  <td>
                    <pre className="inline-code">{formatJson(span.input_summary)}</pre>
                  </td>
                  <td>
                    <pre className="inline-code">{formatJson(span.output_summary)}</pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel section-gap">
        <h2>LLM 交互摘要</h2>
        {llmInteractions.length === 0 ? (
          <p className="muted">暂无 LLM 交互记录。</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>组件</th>
                  <th>模型</th>
                  <th>状态</th>
                  <th>输入 Hash</th>
                  <th>输出 Hash</th>
                </tr>
              </thead>
              <tbody>
                {llmInteractions.map((item) => (
                  <tr key={item.id}>
                    <td>{item.component}</td>
                    <td>{item.model}</td>
                    <td>{item.status}</td>
                    <td>{item.input_hash}</td>
                    <td>{item.output_hash}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
