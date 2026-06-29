import type { AgentAuditView } from "@/lib/schemas/runs";

type WorkerMatrixProps = {
  workers: AgentAuditView["workers"];
};

function listText(items: string[] | undefined, max = 4) {
  if (!items || items.length === 0) {
    return "-";
  }
  const visible = items.slice(0, max).join(", ");
  return items.length > max ? `${visible} +${items.length - max}` : visible;
}

function statusClass(status: string | undefined) {
  if (status === "ok" || status === "passed") {
    return "badge badge-success";
  }
  if (status === "failed" || status === "blocked" || status === "false") {
    return "badge badge-failed";
  }
  return "badge badge-pending";
}

export function WorkerMatrix({ workers }: WorkerMatrixProps) {
  return (
    <section className="audit-block section-gap" aria-labelledby="worker-matrix-title">
      <h3 id="worker-matrix-title">Worker Matrix</h3>
      <div className="table-wrap audit-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Status</th>
              <th>Hard Block</th>
              <th>Claims</th>
              <th>Tool Refs</th>
              <th>Missing Facts</th>
              <th>Conflicts</th>
              <th>Confirmations</th>
            </tr>
          </thead>
          <tbody>
            {workers.map((worker) => (
              <tr key={worker.task_id ?? worker.agent_name}>
                <td>
                  <strong>{worker.agent_name ?? "-"}</strong>
                  <span className="table-subtext">{worker.summary ?? ""}</span>
                </td>
                <td>
                  <span className={statusClass(worker.status)}>{worker.status ?? "-"}</span>
                </td>
                <td>{worker.hard_block ? "yes" : "no"}</td>
                <td>{worker.claim_count}</td>
                <td>{worker.tool_call_artifact_count}</td>
                <td>{listText(worker.missing_facts, 5)}</td>
                <td>{listText(worker.conflicts, 5)}</td>
                <td>{listText(worker.required_confirmations, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
