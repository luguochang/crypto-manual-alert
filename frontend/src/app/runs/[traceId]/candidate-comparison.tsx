import type { AgentAuditView } from "@/lib/schemas/runs";
import { safeDisplayError } from "@/app/shared/safe-error";

type CandidateComparisonProps = {
  comparison: AgentAuditView["candidate_final_comparison"];
};

function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    const scalars = value.filter((item) => ["string", "number", "boolean"].includes(typeof item)).slice(0, 4).map(String);
    return scalars.length > 0 ? scalars.join(", ") : "结构化列表已记录";
  }
  return "结构化内容已记录";
}

function errorText(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return safeDisplayError(valueText(value), "执行异常");
}

function stringList(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item)).filter(Boolean);
}

export function CandidateComparison({ comparison }: CandidateComparisonProps) {
  const candidateDiagnosis = comparison.candidate?.diagnosis as
    | { summary?: unknown; blocking_reasons?: unknown }
    | undefined;
  const blockingReasons = stringList(candidateDiagnosis?.blocking_reasons);
  const gateReasons = stringList(comparison.production_control_gate?.reasons);
  const gateBlockingRules = stringList(comparison.production_control_gate?.blocking_rule_ids);

  return (
    <section className="audit-block" aria-labelledby="candidate-comparison-title">
      <h3 id="candidate-comparison-title">Candidate Comparison</h3>
      <dl className="detail-list compact-list">
        <div>
          <dt>Candidate Status</dt>
          <dd>{comparison.status ?? "-"}</dd>
        </div>
        <div>
          <dt>Production Input</dt>
          <dd>{comparison.production_final_input ? "yes" : "no"}</dd>
        </div>
        <div>
          <dt>Input Selection</dt>
          <dd>{valueText(comparison.final_input_selection?.mode)}</dd>
        </div>
      </dl>
      <div className="table-wrap audit-table-wrap">
        <table className="compact-table">
          <thead>
            <tr>
              <th>Path</th>
              <th>Action</th>
              <th>Probability</th>
              <th>Allowed</th>
              <th>Error</th>
              <th>Input Ref</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Legacy final</td>
              <td>{valueText(comparison.legacy?.action)}</td>
              <td>{valueText(comparison.legacy?.probability)}</td>
              <td>{valueText(comparison.legacy?.allowed)}</td>
              <td>-</td>
              <td>-</td>
            </tr>
            <tr>
              <td>Swarm candidate</td>
              <td>{valueText(comparison.candidate?.action)}</td>
              <td>{valueText(comparison.candidate?.probability)}</td>
              <td>{valueText(comparison.candidate?.allowed)}</td>
              <td>{errorText(comparison.candidate?.error)}</td>
              <td className="mono-cell">{valueText(comparison.candidate?.input_ref)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <dl className="detail-list compact-list section-gap">
        <div>
          <dt>Decision Effect</dt>
          <dd>{comparison.decision_effect ?? "-"}</dd>
        </div>
        <div>
          <dt>Diff</dt>
          <dd>{valueText(comparison.diff)}</dd>
        </div>
        <div>
          <dt>Production Gate</dt>
          <dd>{valueText(comparison.production_control_gate?.allowed)}</dd>
        </div>
        <div>
          <dt>Gate Reasons</dt>
          <dd>{gateReasons.join(", ") || "-"}</dd>
        </div>
        <div>
          <dt>Blocking Rules</dt>
          <dd>{gateBlockingRules.join(", ") || "-"}</dd>
        </div>
      </dl>
      {candidateDiagnosis?.summary || blockingReasons.length > 0 ? (
        <div className="audit-note section-gap">
          <strong>{safeDisplayError(valueText(candidateDiagnosis?.summary), "诊断摘要已记录")}</strong>
          {blockingReasons.length > 0 ? (
            <ul>
              {blockingReasons.map((reason) => (
                <li key={reason}>{safeDisplayError(reason, "阻断理由已记录")}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
