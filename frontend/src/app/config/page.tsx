import { Icon, type IconName } from "../shared/icons";
import { getSystemConfig } from "@/lib/api/system";

export const dynamic = "force-dynamic";

const SECTION_ICON: Record<string, IconName> = {
  app: "settings",
  trading: "zap",
  market_data: "activity",
  decision: "cpu",
  notification: "bell",
  scheduler: "clock",
  research: "search",
  eval: "flask",
  shadow: "shield",
  workflow: "activity",
  skill_providers: "database",
  macro_event: "alert",
  security: "shield"
};

const SECTION_ORDER = [
  "app",
  "trading",
  "market_data",
  "decision",
  "notification",
  "scheduler",
  "research",
  "shadow",
  "workflow",
  "skill_providers",
  "macro_event",
  "eval",
  "security"
];

const SECTION_LABEL: Record<string, string> = {
  app: "应用",
  trading: "交易护栏",
  market_data: "行情数据",
  decision: "决策引擎",
  notification: "通知",
  scheduler: "调度",
  research: "研究检索",
  shadow: "Shadow Worker",
  workflow: "工作流模式",
  skill_providers: "Skill Provider",
  macro_event: "宏观事件",
  eval: "评估门禁",
  security: "安全边界"
};

function isSecretish(value: unknown): boolean {
  return typeof value === "string" && (value === "<redacted>" || value === "<unset>");
}

function renderValue(value: unknown) {
  if (value === null || value === undefined) {
    return <span className="config-value-false">—</span>;
  }
  if (typeof value === "boolean") {
    return value ? (
      <span className="config-value-true">true</span>
    ) : (
      <span className="config-value-false">false</span>
    );
  }
  if (isSecretish(value)) {
    return <span className="config-value-secret">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">[]</span>;
    return (
      <span>
        {value.map((item, idx) => (
          <span key={idx} className="config-pill" style={{ marginRight: 6, marginBottom: 4, display: "inline-block" }}>
            {String(item)}
          </span>
        ))}
      </span>
    );
  }
  if (typeof value === "object") {
    // 嵌套段（如 eval.release_gate / financial_quality）
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <dl className="config-dl" style={{ marginTop: 4 }}>
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{renderValue(v)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="mono">{String(value)}</span>;
}

export default async function ConfigPage() {
  const result = await getSystemConfig();
  const config = result.ok ? result.data : {};

  const sections = SECTION_ORDER.filter((key) => config[key] !== undefined);
  const mode = config.app?.mode as string | undefined;
  const autoOrder = config.trading?.auto_order_enabled as boolean | undefined;
  const manualRequired = config.trading?.manual_execution_required as boolean | undefined;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>配置</h1>
          <p>当前生效配置的只读快照（脱敏）。变更需改 YAML 并重启，避免运行时绕过安全校验。</p>
        </div>
      </header>

      {!result.ok ? (
        <div className="error-state">{result.error.message}</div>
      ) : (
        <>
          <div className="status-bar">
            <span className="status-item">
              <span className={`status-dot ${mode === "SHADOW" ? "warn pulse" : "ok"}`} />
              app.mode = <strong>{mode ?? "-"}</strong>
            </span>
            <span className="status-item">
              <Icon name={autoOrder ? "x" : "check"} size={14} />
              auto_order_enabled = <strong className={autoOrder ? "config-value-false" : "config-value-true"}>{String(autoOrder)}</strong>
            </span>
            <span className="status-item">
              <Icon name={manualRequired ? "check" : "alert"} size={14} />
              manual_execution_required = <strong className={manualRequired ? "config-value-true" : "config-value-false"}>{String(manualRequired)}</strong>
            </span>
          </div>

          <div className="config-grid">
            {sections.map((key) => {
              const fields = Object.entries(config[key] as Record<string, unknown>);
              return (
                <section className="config-card" key={key}>
                  <h3>
                    <Icon name={SECTION_ICON[key] ?? "settings"} size={15} />
                    {SECTION_LABEL[key] ?? key}
                    <span className="config-pill" style={{ marginLeft: "auto" }}>{key}</span>
                  </h3>
                  <dl className="config-dl">
                    {fields.map(([field, value]) => (
                      <div key={field}>
                        <dt>{field}</dt>
                        <dd>{renderValue(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
