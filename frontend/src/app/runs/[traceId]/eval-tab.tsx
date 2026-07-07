import { fieldText } from "./format-helpers";
import type { AgentAuditView } from "@/lib/schemas/runs";

type EvalTabProps = {
  agentAudit: AgentAuditView | undefined;
  badcases: Record<string, unknown>[];
};

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function asString(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function EvalTab({ agentAudit, badcases }: EvalTabProps) {
  const releaseGate = agentAudit?.release_eval_gate;
  const gates = agentAudit?.gates;
  const gateItems: { name: string; data: Record<string, unknown> | undefined }[] = [
    { name: "Facts Gate", data: agentAudit?.facts_gate as Record<string, unknown> | undefined },
    { name: "Production Control Gate", data: gates?.production_control_gate as Record<string, unknown> | undefined },
    { name: "Candidate Gate", data: gates?.gate_candidate as Record<string, unknown> | undefined },
    { name: "Plan Semantic Candidate", data: gates?.plan_semantic_candidate as Record<string, unknown> | undefined },
    { name: "Final Switch Readiness", data: gates?.final_decision_switch_readiness as Record<string, unknown> | undefined }
  ];

  return (
    <>
      <div className="grid-3 section-gap">
        <section className="panel">
          <h3>Structural Gate</h3>
          <dl className="detail-list">
            <div><dt>ready</dt><dd>{fieldText(releaseGate?.structural_gate as Record<string, unknown> | undefined, "ready")}</dd></div>
            <div><dt>passed</dt><dd>{fieldText(releaseGate?.structural_gate as Record<string, unknown> | undefined, "passed")}</dd></div>
            <div><dt>blocking</dt><dd>{fieldText(releaseGate?.structural_gate as Record<string, unknown> | undefined, "blocking")}</dd></div>
          </dl>
        </section>
        <section className="panel">
          <h3>Production Control Gate</h3>
          <dl className="detail-list">
            <div><dt>allowed</dt><dd>{fieldText(releaseGate?.production_control_gate as Record<string, unknown> | undefined, "allowed")}</dd></div>
            <div><dt>severity</dt><dd>{fieldText(releaseGate?.production_control_gate as Record<string, unknown> | undefined, "severity")}</dd></div>
            <div><dt>reasons</dt><dd>{fieldText(releaseGate?.production_control_gate as Record<string, unknown> | undefined, "reasons")}</dd></div>
          </dl>
        </section>
        <section className="panel">
          <h3>Financial Quality</h3>
          <dl className="detail-list">
            <div><dt>status</dt><dd>{fieldText(releaseGate?.financial_quality_gate as Record<string, unknown> | undefined, "status")}</dd></div>
            <div><dt>decision_effect</dt><dd>{fieldText(releaseGate?.financial_quality_gate as Record<string, unknown> | undefined, "decision_effect")}</dd></div>
            <div><dt>scored_count</dt><dd>{fieldText(releaseGate?.financial_quality_gate as Record<string, unknown> | undefined, "observed_scored_count")}</dd></div>
          </dl>
        </section>
      </div>

      <section className="panel section-gap">
        <h2>Gate 追溯链</h2>
        <div className="gate-trace">
          {gateItems.map((g) => {
            const passed = g.data?.passed === true || g.data?.allowed === true;
            const blocking = g.data?.blocking === true || g.data?.passed === false;
            const reasons = asStringArray(g.data?.reasons);
            return (
              <div key={g.name} className={`gate-row ${blocking ? "gate-block" : "gate-pass"}`}>
                <span className="gate-name">{g.name}</span>
                <span className={`badge ${blocking ? "badge-failed" : passed ? "badge-success" : "badge-neutral"}`}>
                  {blocking ? "blocked" : passed ? "passed" : fieldText(g.data, "passed") || "-"}
                </span>
                <span className="gate-reasons">
                  {reasons.length > 0 ? (
                    <ul className="gate-reason-list">
                      {reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : (
                    <span>{fieldText(g.data, "severity") !== "-" ? fieldText(g.data, "severity") : "—"}</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel section-gap">
        <h2>Badcases（{badcases.length}）</h2>
        {badcases.length === 0 ? (
          <p className="muted">无 badcase 记录。</p>
        ) : (
          <div className="table-wrap">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>严重度</th>
                  <th>类别</th>
                  <th>状态</th>
                  <th>期望行为</th>
                  <th>实际行为</th>
                  <th>证据引用</th>
                </tr>
              </thead>
              <tbody>
                {badcases.map((bc, idx) => {
                  const severity = asString(bc.severity);
                  const evidenceRefs = asStringArray(bc.evidence_refs);
                  return (
                    <tr key={asString(bc.id) ?? `bc-${idx}`} className={severity === "critical" || severity === "high" ? "worker-failed" : ""}>
                      <td className="mono-cell">{asString(bc.id)}</td>
                      <td>
                        <span className={`badge ${severity === "critical" ? "badge-failed" : severity === "high" ? "badge-failed" : "badge-neutral"}`}>
                          {severity}
                        </span>
                      </td>
                      <td>{asString(bc.category)}</td>
                      <td>{asString(bc.status)}</td>
                      <td>{asString(bc.expected_behavior)}</td>
                      <td>{asString(bc.actual_behavior)}</td>
                      <td className="mono-cell">{evidenceRefs.length > 0 ? evidenceRefs.join(", ") : "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
