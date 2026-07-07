import Link from "next/link";
import { listRuns } from "@/lib/api/runs";
import { getSystemHealth } from "@/lib/api/system";
import { StatusBadge } from "@/app/shared/status-badge";
import { Icon, type IconName } from "@/app/shared/icons";

export const dynamic = "force-dynamic";

type QuickLink = { href: string; label: string; desc: string; icon: IconName; tone: string };

const QUICK_LINKS: QuickLink[] = [
  { href: "/manual-run", label: "新建提醒", desc: "手动提交一次评估", icon: "plus", tone: "primary" },
  { href: "/runs?view=alerts", label: "提醒业务", desc: "查看决策与 Bark 送达", icon: "bell", tone: "accent" },
  { href: "/runs?view=observe", label: "Agent 可观测", desc: "trace 时间线 / worker / 工具 / gate", icon: "activity", tone: "accent" },
  { href: "/eval", label: "评估", desc: "金融质量 / baseline / outcome", icon: "flask", tone: "accent" },
  { href: "/config", label: "配置", desc: "生效配置只读快照", icon: "settings", tone: "muted" }
];

export default async function DashboardPage() {
  const [runsResult, healthResult] = await Promise.all([
    listRuns(),
    getSystemHealth()
  ]);

  const recentRuns = runsResult.ok ? (runsResult.data.items ?? []) : [];
  const health = healthResult.ok ? healthResult.data : null;
  const mode = health?.mode ?? "unknown";

  const allowed = recentRuns.filter((r) => r.status === "allowed").length;
  const blocked = recentRuns.filter((r) => r.status === "blocked").length;
  const llmTotal = recentRuns.reduce((sum, r) => sum + (r.llm_interaction_count ?? 0), 0);

  const statCards = [
    { label: "最近运行", value: recentRuns.length, trend: "最近 20 条" },
    { label: "允许提醒", value: allowed, trend: "verdict.allowed = true" },
    { label: "风控阻断", value: blocked, trend: "gate blocked" },
    { label: "LLM 交互", value: llmTotal, trend: "累计调用数" }
  ];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>系统总览：运行状态、最近提醒与可观测入口。</p>
        </div>
        <Link className="button" href="/manual-run">
          <Icon name="plus" size={16} /> 新建运行
        </Link>
      </header>

      <div className="status-bar">
        <span className="status-item">
          <span className={`status-dot ${mode === "SHADOW" ? "warn pulse" : "ok"}`} />
          mode = <strong>{mode}</strong>
        </span>
        <span className="status-item">
          <Icon name="database" size={14} />
          storage = <strong>{health?.storage ?? "-"}</strong>
        </span>
        <span className="status-item">
          <Icon name="shield" size={14} />
          service = <strong>{health?.service ?? "-"}</strong>
        </span>
        <span className="status-item">
          <Icon name="check" size={14} />
          auto_order = <strong style={{ color: "var(--success)" }}>disabled</strong>
        </span>
      </div>

      <section className="stats-grid" aria-label="运行统计">
        {statCards.map((card) => (
          <div className="stat-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <span className="stat-trend">{card.trend}</span>
          </div>
        ))}
      </section>

      <div className="grid-2">
        <section className="panel">
          <div className="section-heading-row">
            <div>
              <h2>最近提醒</h2>
              <p className="muted">业务视角：决策动作与风控结论。</p>
            </div>
            <Link className="button-ghost button" href="/runs?view=alerts">
              全部 <Icon name="chevron-right" size={14} />
            </Link>
          </div>
          {recentRuns.length === 0 ? (
            <p className="muted">暂无运行记录。</p>
          ) : (
            <div className="table-wrap">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>交易对</th>
                    <th>状态</th>
                    <th>最终动作</th>
                    <th>创建时间</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.slice(0, 8).map((run) => (
                    <tr key={run.trace_id}>
                      <td className="mono-cell">{run.symbol}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td>{run.final_action ?? "-"}</td>
                      <td className="mono-cell">{run.created_at}</td>
                      <td>
                        <Link className="button-ghost button" href={`/runs/${encodeURIComponent(run.trace_id)}`}>
                          <Icon name="chevron-right" size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>快捷入口</h2>
          <div className="config-grid" style={{ gridTemplateColumns: "1fr" }}>
            {QUICK_LINKS.map((link) => (
              <Link key={link.href} href={link.href} className="worker-cell" style={{ display: "flex", alignItems: "center", gap: 12, textDecoration: "none" }}>
                <Icon name={link.icon} size={18} style={{ color: "var(--primary)" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="worker-name">{link.label}</div>
                  <div className="worker-meta">{link.desc}</div>
                </div>
                <Icon name="chevron-right" size={14} style={{ color: "var(--muted)" }} />
              </Link>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
