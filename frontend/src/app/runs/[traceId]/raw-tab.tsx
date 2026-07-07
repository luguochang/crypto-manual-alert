import { JsonDetails } from "@/app/shared/json-details";
import type { PlanRun } from "@/lib/schemas/runs";

type RawTabProps = {
  parsedPlan: Record<string, unknown>;
  verdict: Record<string, unknown>;
  planRun: PlanRun | null;
  analysis: Record<string, unknown>;
};

export function RawTab({ parsedPlan, verdict, planRun, analysis }: RawTabProps) {
  return (
    <section className="panel">
      <h2>原始数据</h2>
      <p className="muted" style={{ marginBottom: 16 }}>开发者下钻用：未脱敏字段请勿外传。LLM 请求/响应与 span 输入输出见"业务矩阵"页签。</p>
      <div className="step-grid">
        <JsonDetails title="Parsed Plan" value={parsedPlan} large />
        <JsonDetails title="Verdict / Redaction" value={{ verdict, redaction: planRun?.redaction }} large />
        <JsonDetails title="Analysis" value={analysis} large />
      </div>
    </section>
  );
}
