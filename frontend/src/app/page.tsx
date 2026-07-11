import Link from "next/link";
import { listRuns } from "@/lib/api/runs";
import { getSystemHealth } from "@/lib/api/system";
import { StatusBadge } from "@/app/shared/status-badge";
import { Icon, type IconName } from "@/app/shared/icons";
import { productDisplayText } from "@/app/shared/product-copy";

export const dynamic = "force-dynamic";

type QuickLink = { href: string; label: string; desc: string; icon: IconName; tone: string };

const QUICK_LINKS: QuickLink[] = [
  { href: "/manual-run", label: "新建提醒", desc: "手动提交一次评估", icon: "plus", tone: "primary" },
  { href: "/runs", label: "提醒记录", desc: "查看建议、风控与 Bark 送达", icon: "bell", tone: "accent" },
  { href: "/eval?tab=quality", label: "质量复盘", desc: "查看历史提醒后的质量表现", icon: "flask", tone: "accent" },
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
  const modeStatus = productModeStatus(mode);

  const allowed = recentRuns.filter((r) => r.status === "allowed").length;
  const blocked = recentRuns.filter((r) => r.status === "blocked").length;

  const statCards = [
    { label: "提醒窗口", value: recentRuns.length, trend: "最近 20 条提醒，非全量统计" },
    { label: "可人工复核", value: allowed, trend: "可复核不代表自动下单许可" },
    { label: "风控阻断", value: blocked, trend: "风控命中后已阻断" },
    { label: "自动下单", value: "关闭", trend: "系统只生成提醒与记录" }
  ];

  return (
    <>
      <header className="page-header">
        <div>
          <h1>提醒控制台</h1>
          <p>控制面总览：只展示人工提醒、门禁与审计入口，不是交易终端。</p>
        </div>
        <Link className="button" href="/manual-run" prefetch={false}>
          <Icon name="plus" size={16} /> 生成人工提醒
        </Link>
      </header>

      <div className="status-bar">
        <span className="status-item">
          <span className={`status-dot ${modeStatus.tone}`} />
          运行模式 <strong>{modeStatus.label}</strong>
        </span>
        <span className="status-item">
          <Icon name="database" size={14} />
          数据存储 <strong>{productStorageStatus(health?.storage)}</strong>
        </span>
        <span className="status-item">
          <Icon name="shield" size={14} />
          服务状态 <strong>{productServiceStatus(health?.service)}</strong>
        </span>
        <span className="status-item">
          <Icon name="check" size={14} />
          自动下单 <strong style={{ color: "var(--success)" }}>关闭</strong>
        </span>
      </div>

      <section className="panel safety-banner" aria-label="安全边界">
        <strong>安全边界：自动下单关闭，所有可复核结果都需要人工再次确认。</strong>
        <span>统计基于当前列表窗口；提醒后的实际表现会在质量复盘中汇总。</span>
      </section>

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
            <Link className="button-ghost button" href="/runs" prefetch={false}>
              全部 <Icon name="chevron-right" size={14} />
            </Link>
          </div>
          {recentRuns.length === 0 ? (
            <p className="muted">暂无人工提醒记录。生成提醒前不会产生任何交易副作用。</p>
          ) : (
            <div className="table-wrap">
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>交易对</th>
                    <th>状态</th>
                    <th>提醒建议</th>
                    <th>创建时间</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.slice(0, 8).map((run) => (
                    <tr key={run.trace_id}>
                      <td className="mono-cell">{run.symbol}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td>{productDisplayText(run.final_action) || "-"}</td>
                      <td>{formatRunTime(run.created_at)}</td>
                      <td>
                        <Link className="button-ghost button" href={`/runs/${encodeURIComponent(run.trace_id)}`} prefetch={false}>
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
              <Link key={link.href} href={link.href} prefetch={false} className="quick-link-cell" style={{ display: "flex", alignItems: "center", gap: 12, textDecoration: "none" }}>
                <Icon name={link.icon} size={18} style={{ color: "var(--primary)" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="quick-link-name">{link.label}</div>
                  <div className="quick-link-meta">{link.desc}</div>
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

function productModeStatus(value: string): { label: string; tone: "ok" | "warn pulse" } {
  if (value === "SHADOW") {
    return { label: "安全演练", tone: "warn pulse" };
  }
  if (value === "PROD") {
    return { label: "生产配置", tone: "ok" };
  }
  return { label: "待确认", tone: "warn pulse" };
}

function productStorageStatus(value: string | undefined): string {
  return value ? "记录存储正常" : "存储待确认";
}

function productServiceStatus(value: string | undefined): string {
  return value ? "服务正常" : "服务待确认";
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}
