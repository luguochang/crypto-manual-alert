import type { AgentAuditView } from "@/lib/schemas/runs";

type ToolCallGraphProps = {
  toolCalls: AgentAuditView["tool_calls"];
  rootCauseGraph: AgentAuditView["root_cause_graph"];
};

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
  return String(value);
}

function factRefsText(value: unknown) {
  if (!value || typeof value !== "object") {
    return "-";
  }
  const refs = value as Record<string, unknown>;
  return ["mark", "index", "order_book"]
    .filter((key) => refs[key])
    .map((key) => `${key}:${shortHash(String(refs[key]))}`)
    .join(" / ") || "-";
}

function errorText(call: AgentAuditView["tool_calls"][number]) {
  if (!call.error_type && !call.error_hash) {
    return "-";
  }
  return `${call.error_type ?? "error"}:${shortHash(call.error_hash)}`;
}

export function ToolCallGraph({ toolCalls, rootCauseGraph }: ToolCallGraphProps) {
  return (
    <div className="audit-grid section-gap">
      <section className="audit-block" aria-labelledby="tool-calls-title">
        <h3 id="tool-calls-title">Skill Tool Calls</h3>
        <div className="table-wrap audit-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Worker</th>
                <th>Skill</th>
                <th>Status</th>
                <th>Source</th>
                <th>Freshness</th>
                <th>Execution Fact</th>
                <th>Fact Refs</th>
                <th>Error</th>
                <th>Result Ref</th>
              </tr>
            </thead>
            <tbody>
              {toolCalls.length === 0 ? (
                <tr>
                  <td colSpan={9}>No skill tool calls recorded for this trace.</td>
                </tr>
              ) : (
                toolCalls.map((call, index) => (
                  <tr key={call.tool_call_id ?? `${call.worker}-${index}`}>
                    <td>{call.worker ?? "-"}</td>
                    <td>{call.skill_name ?? "-"}</td>
                    <td>{call.status ?? "-"}</td>
                    <td>
                      {call.source_type ?? "-"} / {valueText(call.source_tier)}
                    </td>
                    <td>{call.freshness_status ?? "-"}</td>
                    <td>{call.can_satisfy_execution_fact ? "yes" : "no"}</td>
                    <td className="mono-cell">{factRefsText(call.fact_refs)}</td>
                    <td className="mono-cell">{errorText(call)}</td>
                    <td className="mono-cell">{shortHash(call.result_ref)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="audit-block" aria-labelledby="root-cause-title">
        <h3 id="root-cause-title">Root Cause Graph</h3>
        <div className="table-wrap audit-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Node</th>
                <th>Layer</th>
                <th>Factor</th>
                <th>Worker</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rootCauseGraph.nodes.length === 0 ? (
                <tr>
                  <td colSpan={5}>No root-cause graph nodes recorded.</td>
                </tr>
              ) : (
                rootCauseGraph.nodes.map((node) => (
                  <tr key={node.node_id}>
                    <td className="mono-cell">{node.node_id}</td>
                    <td>{node.layer}</td>
                    <td>{node.factor_type ?? "-"}</td>
                    <td>{node.worker ?? "-"}</td>
                    <td>{node.evidence_refs.join(", ") || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {rootCauseGraph.edges.length > 0 ? (
          <ol className="runtime-flow-list section-gap">
            {rootCauseGraph.edges.map((edge, index) => (
              <li key={`${edge.from}-${edge.to}-${index}`}>
                <strong>
                  {edge.from} to {edge.to}
                </strong>
                <span>{edge.worker ?? "-"}</span>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
    </div>
  );
}
