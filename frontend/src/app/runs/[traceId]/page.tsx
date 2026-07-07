import Link from "next/link";
import { getRunDetail } from "@/lib/api/runs";
import { AgentAuditPanel } from "./agent-audit-panel";
import { DecisionSummaryCard } from "./decision-summary-card";
import { asNumber, asString } from "@/app/shared/coerce";
import { JsonDetails, formatJson } from "@/app/shared/json-details";
import { StatusBadge } from "@/app/shared/status-badge";

export const dynamic = "force-dynamic";

type TraceDetailPageProps = {
  params: Promise<{
    traceId: string;
  }>;
};

function shortHash(value: string | null | undefined) {
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

function metricText(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${value}${suffix}`;
}

function moneyText(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "unknown";
  }
  return `$${value.toFixed(6)}`;
}

export default async function TraceDetailPage({ params }: TraceDetailPageProps) {
  const { traceId } = await params;
  const result = await getRunDetail(traceId, { includePayloads: true });

  if (!result.ok) {
    return (
      <>
        <header className="page-header">
          <div>
            <h1>Trace Detail</h1>
            <p>Trace ID: {traceId}</p>
          </div>
          <Link className="button button-secondary" href="/runs">
            Back to Runs
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
  const agentAudit = planRun?.agent_audit_view;
  const analysis = detail.analysis ?? {};
  const spans = detail.spans ?? [];
  const llmInteractions = detail.llm_interactions ?? [];
  const badcases = detail.badcases ?? [];
  const totalKnownTokens = llmInteractions.reduce((sum, item) => sum + (item.total_tokens ?? 0), 0);
  const missingTokenCount = llmInteractions.filter((item) => item.total_tokens == null).length;
  const totalKnownCost = llmInteractions.reduce((sum, item) => sum + (item.cost_usd ?? 0), 0);
  const missingCostCount = llmInteractions.filter((item) => item.cost_usd == null).length;
  const knownCostCount = llmInteractions.length - missingCostCount;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Trace Detail</h1>
          <p>Trace ID: {trace.trace_id}</p>
        </div>
        <Link className="button button-secondary" href="/runs">
          Back to Runs
        </Link>
      </header>

      <section className="trace-summary-grid" aria-label="Trace summary">
        <div className="stat-card">
          <span>Run Status</span>
          <strong>
            <StatusBadge status={trace.status} />
          </strong>
        </div>
        <div className="stat-card">
          <span>Final Action</span>
          <strong>{trace.final_action ?? "-"}</strong>
        </div>
        <div className="stat-card">
          <span>Spans</span>
          <strong>{spans.length}</strong>
        </div>
        <div className="stat-card">
          <span>LLM Calls</span>
          <strong>{llmInteractions.length}</strong>
        </div>
      </section>

      <DecisionSummaryCard
        mainAction={asString(parsedPlan.main_action)}
        probability={asNumber(parsedPlan.probability)}
        referencePrice={asNumber(parsedPlan.reference_price)}
        entryTrigger={asNumber(parsedPlan.entry_trigger)}
        stopPrice={asNumber(parsedPlan.stop_price)}
        target1={asNumber(parsedPlan.target_1)}
        target2={asNumber(parsedPlan.target_2)}
        allowed={trace.allowed}
        symbol={trace.symbol}
        horizon={asString(parsedPlan.horizon)}
        executionMode={agentAudit?.mode}
        productionFinalInputMode={agentAudit?.input_lineage?.production_final_input_mode}
        analysis={analysis}
        verdictReasons={verdict.reasons}
      />

      <AgentAuditPanel agentAudit={agentAudit} />

      <div className="grid-2 section-gap">
        <section className="panel">
          <h2>Run Info</h2>
          <dl className="detail-list">
            <div>
              <dt>Symbol</dt>
              <dd>{trace.symbol}</dd>
            </div>
            <div>
              <dt>Run Type</dt>
              <dd>{trace.run_type}</dd>
            </div>
            <div>
              <dt>Risk Allowed</dt>
              <dd>{trace.allowed == null ? "-" : trace.allowed ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt>Plan ID</dt>
              <dd>{trace.final_plan_id ?? planRun?.plan_id ?? "-"}</dd>
            </div>
            <div>
              <dt>Created At</dt>
              <dd>{trace.created_at}</dd>
            </div>
            <div>
              <dt>Ended At</dt>
              <dd>{trace.ended_at ?? "-"}</dd>
            </div>
          </dl>
        </section>

        <section className="panel">
          <h2>Decision Summary</h2>
          <dl className="detail-list">
            <div>
              <dt>Main Action</dt>
              <dd>{valueText(parsedPlan.main_action)}</dd>
            </div>
            <div>
              <dt>Probability</dt>
              <dd>{valueText(parsedPlan.probability)}</dd>
            </div>
            <div>
              <dt>Entry Trigger</dt>
              <dd>{valueText(parsedPlan.entry_trigger)}</dd>
            </div>
            <div>
              <dt>Stop</dt>
              <dd>{valueText(parsedPlan.stop_price)}</dd>
            </div>
            <div>
              <dt>Targets</dt>
              <dd>
                {valueText(parsedPlan.target_1)} / {valueText(parsedPlan.target_2)}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="panel section-gap">
        <h2>Analysis</h2>
        <div className="analysis-grid">
          <div>
            <h3>Reasoning Summary</h3>
            <p className="analysis-text">{valueText(analysis.reasoning_summary)}</p>
          </div>
          <div>
            <h3>Opposing Thesis</h3>
            <p className="analysis-text">{valueText(analysis.opposing_thesis)}</p>
          </div>
          <div>
            <h3>Data Gaps</h3>
            <JsonDetails title="Data Gaps JSON" value={analysis.data_gaps ?? []} light />
          </div>
          <div>
            <h3>Risk Rule Hits</h3>
            <JsonDetails title="Risk Rule Hits JSON" value={analysis.risk_rule_hits ?? verdict} light />
          </div>
        </div>
      </section>

      <section className="panel section-gap">
        <h2>Span Timeline</h2>
        <div className="timeline-list">
          {spans.map((span, index) => (
            <details className="trace-step" key={span.span_id} open={span.status !== "ok"}>
              <summary>
                <span>
                  {index + 1}. {span.span_name}
                </span>
                <span>{span.status}</span>
                <span>{span.duration_ms} ms</span>
              </summary>
              <div className="step-grid">
                <div>
                  <h3>Input Summary</h3>
                  <pre className="code-box">{formatJson(span.input_summary)}</pre>
                </div>
                <div>
                  <h3>Output Summary</h3>
                  <pre className="code-box">{formatJson(span.output_summary)}</pre>
                </div>
              </div>
              {span.error_message ? <p className="error-state">{span.error_message}</p> : null}
            </details>
          ))}
        </div>
      </section>

      <section className="panel section-gap">
        <h2>LLM Requests And Responses</h2>
        {llmInteractions.length === 0 ? (
          <p className="muted">No LLM interactions were recorded for this trace.</p>
        ) : (
          <div className="timeline-list">
            <dl className="detail-list compact-list">
              <div>
                <dt>Known Tokens</dt>
                <dd>
                  {totalKnownTokens}
                  {missingTokenCount > 0 ? ` (${missingTokenCount} calls missing usage)` : ""}
                </dd>
              </div>
              <div>
                <dt>Known Cost</dt>
                <dd>
                  {knownCostCount > 0 ? moneyText(totalKnownCost) : "unknown"}
                  {missingCostCount > 0 ? ` (${missingCostCount} calls missing price config)` : ""}
                </dd>
              </div>
            </dl>
            {llmInteractions.map((item, index) => (
              <details className="trace-step" key={item.id} open={item.status !== "ok"}>
                <summary>
                  <span>
                    #{item.id} {item.component}
                  </span>
                  <span>
                    {item.provider} / {item.model}
                  </span>
                  <span>{item.status}</span>
                  <span>{metricText(item.duration_ms, " ms")}</span>
                  <span>{metricText(item.total_tokens, " tok")}</span>
                </summary>
                <dl className="detail-list compact-list">
                  <div>
                    <dt>Span</dt>
                    <dd>{shortHash(item.span_id)}</dd>
                  </div>
                  <div>
                    <dt>Endpoint</dt>
                    <dd>{item.endpoint ?? "-"}</dd>
                  </div>
                  <div>
                    <dt>Created At</dt>
                    <dd>{item.created_at ?? "-"}</dd>
                  </div>
                  <div>
                    <dt>Finish</dt>
                    <dd>{item.finish_reason ?? "-"}</dd>
                  </div>
                  <div>
                    <dt>Retry</dt>
                    <dd>{item.retry_count ?? 0}</dd>
                  </div>
                  <div>
                    <dt>Prompt / Completion</dt>
                    <dd>
                      {metricText(item.prompt_tokens)} / {metricText(item.completion_tokens)}
                    </dd>
                  </div>
                  <div>
                    <dt>Cost</dt>
                    <dd>{moneyText(item.cost_usd)}</dd>
                  </div>
                  <div>
                    <dt>Input Hash</dt>
                    <dd>{shortHash(item.input_hash)}</dd>
                  </div>
                  <div>
                    <dt>Output Hash</dt>
                    <dd>{shortHash(item.output_hash)}</dd>
                  </div>
                </dl>
                <div className="step-grid">
                  <div>
                    <h3>Request Summary</h3>
                    <pre className="code-box">{formatJson(item.input_summary)}</pre>
                  </div>
                  <div>
                    <h3>Response Summary</h3>
                    <pre className="code-box">{formatJson(item.output_summary)}</pre>
                  </div>
                  <div>
                    <h3>Metadata</h3>
                    <pre className="code-box">{formatJson(item.metadata ?? {})}</pre>
                  </div>
                  <div>
                    <h3>Sanitized Request Payload</h3>
                    <pre className="code-box large-code">{item.request_json ?? "not requested"}</pre>
                  </div>
                  <div>
                    <h3>Sanitized Response Payload</h3>
                    <pre className="code-box large-code">{item.response_json ?? "not requested"}</pre>
                  </div>
                </div>
                {item.error_message ? <p className="error-state">{item.error_message}</p> : null}
              </details>
            ))}
          </div>
        )}
      </section>

      <section className="panel section-gap">
        <h2>Badcases And Replay</h2>
        {badcases.length === 0 ? (
          <p className="muted">No manual badcase review records yet.</p>
        ) : (
          <JsonDetails title="Badcase Records JSON" value={badcases} />
        )}
      </section>

      <section className="panel section-gap">
        <h2>Structured Result</h2>
        <div className="step-grid">
          <JsonDetails title="Parsed Plan JSON" value={parsedPlan} large />
          <JsonDetails title="Verdict / Redaction JSON" value={{ verdict, redaction: planRun?.redaction }} large />
        </div>
      </section>
    </>
  );
}
