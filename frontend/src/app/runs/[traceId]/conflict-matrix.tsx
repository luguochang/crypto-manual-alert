import type { AgentAuditView } from "@/lib/schemas/runs";

type ConflictMatrixProps = {
  conflictEdges: AgentAuditView["conflict_edges"];
  strongestCounterThesisRef?: string | null;
};

export function ConflictMatrix({ conflictEdges, strongestCounterThesisRef }: ConflictMatrixProps) {
  return (
    <section className="audit-block" aria-labelledby="conflict-matrix-title">
      <h3 id="conflict-matrix-title">Conflict Matrix</h3>
      <div className="table-wrap audit-table-wrap">
        <table className="compact-table">
          <thead>
            <tr>
              <th>Worker A</th>
              <th>Worker B</th>
              <th>Claim Ref</th>
              <th>Type</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {conflictEdges.length === 0 ? (
              <tr>
                <td colSpan={5}>No explicit conflict edges recorded.</td>
              </tr>
            ) : (
              conflictEdges.map((edge, index) => (
                <tr key={`${edge.worker_a}-${edge.worker_b}-${edge.claim_ref}-${index}`}>
                  <td>{edge.worker_a ?? "-"}</td>
                  <td>{edge.worker_b ?? "-"}</td>
                  <td className="mono-cell">{edge.claim_ref ?? "-"}</td>
                  <td>{edge.conflict_type ?? "-"}</td>
                  <td>{edge.severity ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <dl className="detail-list compact-list section-gap">
        <div>
          <dt>Strongest Counter Thesis</dt>
          <dd className="mono-cell">{strongestCounterThesisRef ?? "-"}</dd>
        </div>
      </dl>
    </section>
  );
}
