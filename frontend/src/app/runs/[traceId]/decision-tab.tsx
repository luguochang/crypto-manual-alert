import { DecisionSummaryCard } from "./decision-summary-card";
import { CockpitStatusBar } from "./cockpit-status-bar";
import { asNumber, asString } from "@/app/shared/coerce";
import { valueText } from "./format-helpers";
import type { AgentAuditView, PlanRun, RunSummary } from "@/lib/schemas/runs";

type DecisionTabProps = {
  parsedPlan: Record<string, unknown>;
  verdict: Record<string, unknown>;
  agentAudit: AgentAuditView | undefined;
  analysis: Record<string, unknown>;
  trace: RunSummary;
  planRun: PlanRun | null;
};

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null);
}

export function DecisionTab({ parsedPlan, verdict, agentAudit, analysis, trace, planRun }: DecisionTabProps) {
  const dataGaps = asStringArray(analysis.data_gaps);
  const riskRuleHits = asRecordArray(analysis.risk_rule_hits).length > 0
    ? asRecordArray(analysis.risk_rule_hits)
    : asRecordArray(verdict.rule_hits);

  return (
    <>
      <CockpitStatusBar agentAudit={agentAudit} verdict={verdict} />

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

      <section className="panel section-gap">
        <h2>分析</h2>
        <div className="analysis-grid">
          <div>
            <h3>推理摘要</h3>
            <p className="analysis-text">{valueText(analysis.reasoning_summary)}</p>
          </div>
          <div>
            <h3>反向论点</h3>
            <p className="analysis-text">{valueText(analysis.opposing_thesis)}</p>
          </div>
          <div>
            <h3>数据缺口（{dataGaps.length}）</h3>
            {dataGaps.length === 0 ? (
              <p className="muted">无数据缺口。</p>
            ) : (
              <div className="pill-row">
                {dataGaps.map((gap) => (
                  <span key={gap} className="config-pill">{gap}</span>
                ))}
              </div>
            )}
          </div>
          <div>
            <h3>风控规则命中（{riskRuleHits.length}）</h3>
            {riskRuleHits.length === 0 ? (
              <p className="muted">无规则命中。</p>
            ) : (
              <div className="table-wrap">
                <table className="compact-table">
                  <thead>
                    <tr><th>规则</th><th>阻断</th><th>说明</th></tr>
                  </thead>
                  <tbody>
                    {riskRuleHits.map((hit, idx) => (
                      <tr key={asString(hit.rule_id) ?? `rule-${idx}`} className={hit.blocking === true ? "worker-failed" : ""}>
                        <td className="mono-cell">{asString(hit.rule_id) ?? "-"}</td>
                        <td>{hit.blocking === true ? <span className="badge badge-failed">blocking</span> : <span className="badge badge-neutral">warn</span>}</td>
                        <td>{asString(hit.reason) ?? asString(hit.message) ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="panel section-gap">
        <h2>运行信息</h2>
        <dl className="detail-list">
          <div><dt>交易对</dt><dd>{trace.symbol}</dd></div>
          <div><dt>Run Type</dt><dd>{trace.run_type}</dd></div>
          <div><dt>Plan ID</dt><dd className="mono">{trace.final_plan_id ?? planRun?.plan_id ?? "-"}</dd></div>
          <div><dt>创建时间</dt><dd className="mono">{trace.created_at}</dd></div>
          <div><dt>结束时间</dt><dd className="mono">{trace.ended_at ?? "-"}</dd></div>
        </dl>
      </section>
    </>
  );
}
