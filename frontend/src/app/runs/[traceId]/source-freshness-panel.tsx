import type { AgentAuditView } from "@/lib/schemas/runs";

type SourceFreshnessPanelProps = {
  evidenceSources: AgentAuditView["evidence_sources"];
  sourceFreshness: AgentAuditView["source_freshness"];
};

function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

export function SourceFreshnessPanel({ evidenceSources, sourceFreshness }: SourceFreshnessPanelProps) {
  return (
    <div className="audit-grid section-gap">
      <section className="audit-block" aria-labelledby="source-freshness-title">
        <h3 id="source-freshness-title">Source Freshness</h3>
        <div className="table-wrap audit-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Tier</th>
                <th>Freshness</th>
                <th>Count</th>
                <th>Execution Facts</th>
                <th>Missing</th>
              </tr>
            </thead>
            <tbody>
              {sourceFreshness.length === 0 ? (
                <tr>
                  <td colSpan={6}>No source freshness rows recorded.</td>
                </tr>
              ) : (
                sourceFreshness.map((row, index) => (
                  <tr key={`${row.source_type}-${row.source_tier}-${row.freshness_status}-${index}`}>
                    <td>{row.source_type}</td>
                    <td>{valueText(row.source_tier)}</td>
                    <td>{row.freshness_status}</td>
                    <td>{row.count}</td>
                    <td>{row.can_satisfy_execution_fact_count}</td>
                    <td>{row.missing_execution_facts.join(", ") || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="audit-block" aria-labelledby="evidence-sources-title">
        <h3 id="evidence-sources-title">Evidence Sources</h3>
        <div className="table-wrap audit-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Evidence</th>
                <th>Claim Ref</th>
                <th>Source</th>
                <th>Freshness</th>
                <th>Retrieved</th>
                <th>Execution Fact</th>
              </tr>
            </thead>
            <tbody>
              {evidenceSources.length === 0 ? (
                <tr>
                  <td colSpan={6}>No evidence sources recorded.</td>
                </tr>
              ) : (
                evidenceSources.slice(0, 20).map((source) => (
                  <tr key={source.evidence_ref}>
                    <td className="mono-cell">{source.evidence_ref}</td>
                    <td>{source.claim_ref ?? "-"}</td>
                    <td>
                      {source.source_type ?? "-"} / {valueText(source.source_tier)}
                    </td>
                    <td>{source.freshness_status ?? "-"}</td>
                    <td>{source.retrieved_at ?? "-"}</td>
                    <td>{source.can_satisfy_execution_fact ? "yes" : "no"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
