import { Icon, type IconName } from "../shared/icons";
import type { Readiness } from "@/lib/schemas/system";
import { getSystemConfig } from "@/lib/api/system";

export const dynamic = "force-dynamic";

function readinessTone(status: string): string {
  if (status === "ready") return "badge-success";
  if (status === "unsafe" || status === "missing_env" || status === "main_path_blocked") return "badge-failed";
  if (status === "fixture_only" || status === "disabled") return "badge-pending";
  return "badge-neutral";
}

function readinessLabel(status: string): string {
  const labels: Record<string, string> = {
    ready: "已满足",
    fixture_only: "仅演练",
    missing_env: "缺少环境变量",
    disabled: "未启用",
    unsafe: "存在风险",
    main_path_blocked: "需恢复默认主链"
  };
  return labels[status] ?? status;
}

function readinessShortLabel(status: string): string {
  const labels: Record<string, string> = {
    ready: "已满足",
    fixture_only: "仅演练",
    missing_env: "未配置",
    disabled: "未启用",
    unsafe: "需处理",
    main_path_blocked: "需恢复默认主链"
  };
  return labels[status] ?? readinessLabel(status);
}

function boolText(value: unknown) {
  return value ? "是" : "否";
}

function secretText(value: unknown) {
  return value === "<redacted>" ? "已配置" : "未配置";
}

function modelMode(engine: unknown) {
  if (engine === "openai_compatible") return "外部模型";
  if (engine === "fixture") return "本地演练模型";
  return String(engine ?? "未说明");
}

function marketMode(provider: unknown) {
  if (provider === "okx_public") return "OKX 公开行情";
  if (provider === "fixture") return "本地演练行情";
  return String(provider ?? "未说明");
}

function sidecarMode(mode: unknown) {
  if (mode === "disabled") return "已关闭";
  if (mode === "same_engine") return "跟随主模型";
  return String(mode ?? "未说明");
}

function eventMode(provider: unknown) {
  if (provider === "no_active_event") return "已确认无活跃事件";
  if (provider === "disabled") return "未确认";
  return String(provider ?? "未说明");
}

function finalInputLabel(mode: unknown) {
  if (mode === "legacy_prompt") return "默认稳定路径";
  return String(mode ?? "未说明");
}

function workflowLabel(mode: unknown) {
  if (mode === "legacy_baseline") return "稳定主流程";
  return String(mode ?? "未说明");
}

function shadowLabel(mode: unknown) {
  if (mode === "local_audit") return "本地审计旁路";
  return String(mode ?? "未说明");
}

function mainPathBlockerText(blockers: readonly string[] | undefined) {
  if (!blockers?.length) return undefined;
  const readable = blockers.map((blocker) => {
    if (blocker.includes("decision.final_input_mode")) return "最终生成路径需要保持默认稳定路径。";
    if (blocker.includes("workflow.execution_mode")) return "运行定位需要保持稳定主流程。";
    return "主链配置需要回到生产默认路径。";
  });
  return `主链未就绪：${Array.from(new Set(readable)).join(" ")}`;
}

function mainPathNote(readiness: Readiness | undefined) {
  if (!readiness) return "生产可行动证明必须保持稳定主流程、默认生成路径，并关闭候选旁路。";
  if (readiness.prod_actionable.production_main_path_ready) return "发布门槛已满足。";
  return (
    mainPathBlockerText(readiness.prod_actionable.main_path_blockers) ??
    "主链未就绪：真实发布前需要关闭候选旁路。"
  );
}

function modelNote(status: string | undefined) {
  if (status === "unsafe") return "模型地址或模型名不符合生产自测要求。";
  if (status === "ready") return "外部模型配置存在，发布前仍要跑严格生产自测。";
  if (status === "fixture_only") return "当前只会走本地演练，不会调用外部模型。";
  return "需要补齐模型地址、模型名和密钥。";
}

function marketNote(status: string | undefined) {
  if (status === "unsafe") return "行情地址不符合生产自测要求。";
  if (status === "ready") return "已配置真实行情来源，仍需实际运行验证。";
  return "当前行情只适合验证页面和流程。";
}

function orderBookNote(status: string | undefined) {
  if (status === "ready") return "开仓类提醒可以使用交易所原生订单簿事实。";
  return "开仓类提醒还不能进入真实人工复核。";
}

function eventNote(status: string | undefined) {
  if (status === "ready") return "已确认本窗口没有影响提醒的活跃宏观事件。";
  return "缺少事件状态确认时，开仓、触发或翻转类提醒会被阻断。";
}

function notificationNote(status: string | undefined) {
  if (status === "ready") return "手机提醒配置存在，真实发送结果仍以运行记录为准。";
  if (status === "missing_env") return "已开启提醒但缺少手机推送密钥。";
  return "当前不会向手机发送真实提醒。";
}

function forbiddenEnvNote(status: string | undefined) {
  if (status === "ready") return "当前没有发现交易或提现密钥。";
  return "发现交易或提现密钥时不能进入生产提醒发布。";
}

function overallReadinessSummary(readiness: Readiness | undefined) {
  if (!readiness) return "当前配置状态不可用。";
  if (readiness.prod_actionable.status === "unsafe") return "配置中存在不符合生产自测要求的地址或模型。";
  if (readiness.prod_actionable.prod_actionable_ready) return "生产提醒所需配置已齐全，但仍必须跑严格生产自测。";
  return "当前只能证明演练或部分链路，不能称为真实生产提醒。";
}

function ReadinessChecklist({ readiness }: { readiness: Readiness | undefined }) {
  if (!readiness) return null;
  const prodReady = readiness.prod_actionable.prod_actionable_ready;
  const mainPathReady = readiness.prod_actionable.production_main_path_ready;
  const items = [
    {
      label: "真实模型",
      item: readiness.decision_engine,
      detail: "需要外部模型地址、模型名和密钥；本地演练不会生成真实模型内容。"
    },
    {
      label: "模型密钥",
      item: readiness.openai_credentials,
      detail: "密钥只显示是否已配置，不会在页面暴露原文。"
    },
    {
      label: "真实行情",
      item: readiness.market_data,
      detail: "可行动提醒需要交易所公开行情，演练行情只能证明流程。"
    },
    {
      label: "订单簿事实",
      item: readiness.liquidity_order_book,
      detail: "开仓/触发类建议需要交易所原生订单簿事实。"
    },
    {
      label: "宏观事件状态",
      item: readiness.event_status,
      detail: "当前实现要求明确确认没有影响本窗口的活跃宏观事件。"
    },
    {
      label: "Bark 通知",
      item: readiness.notification,
      detail: "生产提醒必须能真实发送到手机，失败不能算交付成功。"
    },
    {
      label: "运行主链",
      item: { status: mainPathReady ? "ready" : "main_path_blocked" },
      detail: mainPathNote(readiness)
    },
    {
      label: "人工执行边界",
      item: readiness.trading_safety,
      detail: "系统只生成提醒与审计记录，不允许自动下单。"
    },
    {
      label: "交易密钥隔离",
      item: readiness.forbidden_env,
      detail: "生产环境不能出现交易或提现密钥。"
    },
    {
      label: "候选旁路",
      item: readiness.prod_actionable,
      detail: "发布可行动提醒前必须关闭会复用生产模型的候选旁路。"
    }
  ] as const;

  return (
    <section className="panel section-gap" aria-label="生产提醒缺口">
      <div className="section-heading-row">
        <div>
          <h2>生产提醒缺口</h2>
          <p className="muted">这些条件必须同时满足，才可以把一次提醒称为真实生产可行动链路。</p>
        </div>
        <span className={`badge ${prodReady ? "badge-success" : "badge-failed"}`}>
          {prodReady ? "可以进入发布自测" : "还不能作为生产提醒交付"}
        </span>
      </div>
      <div className="risk-summary-grid">
        {items.map(({ label, item, detail }) => (
          <article className="risk-summary-item" key={label}>
            <span>{label}</span>
            <strong className={`badge ${readinessTone(item.status)}`}>{readinessShortLabel(item.status)}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

type DetailItem = {
  label: string;
  value: string;
  note?: string;
};

type DetailSection = {
  title: string;
  icon: IconName;
  items: DetailItem[];
};

function ConfigDetails({ config, readiness }: { config: Record<string, Record<string, unknown>>; readiness: Readiness | undefined }) {
  const sections: DetailSection[] = [
    {
      title: "主流程",
      icon: "activity",
      items: [
        { label: "运行定位", value: workflowLabel(config.workflow?.execution_mode), note: "当前默认走稳定主流程。" },
        { label: "最终生成路径", value: finalInputLabel(config.decision?.final_input_mode), note: "候选输入切换仍需单独发布审查。" },
        { label: "主链门禁", value: readiness?.prod_actionable.production_main_path_ready ? "已满足" : "主链未就绪", note: mainPathNote(readiness) },
        { label: "候选旁路", value: sidecarMode(config.decision?.candidate_sidecar_mode), note: readiness?.prod_actionable.candidate_sidecar_disabled ? "发布门槛已满足。" : "真实发布前需要关闭。" }
      ]
    },
    {
      title: "模型与行情",
      icon: "cpu",
      items: [
        { label: "模型模式", value: modelMode(config.decision?.engine), note: modelNote(readiness?.decision_engine.status) },
        { label: "模型名称", value: String(config.decision?.openai_model || "未配置") },
        { label: "模型密钥", value: secretText(config.decision?.openai_api_key_value) },
        { label: "行情来源", value: marketMode(config.market_data?.provider), note: marketNote(readiness?.market_data.status) },
        { label: "订单簿事实", value: config.skill_providers?.liquidity_order_book === "exchange_native" ? "交易所原生" : "本地演练", note: orderBookNote(readiness?.liquidity_order_book.status) }
      ]
    },
    {
      title: "通知与事件",
      icon: "bell",
      items: [
        { label: "手机提醒", value: config.notification?.enabled ? "会发送" : "不发送", note: notificationNote(readiness?.notification.status) },
        { label: "提醒密钥", value: secretText(config.notification?.bark_device_key_value) },
        { label: "事件确认", value: eventMode(config.macro_event?.provider), note: eventNote(readiness?.event_status.status) },
        { label: "后台轮询", value: config.scheduler?.enabled ? "已开启" : "未开启" }
      ]
    },
    {
      title: "安全边界",
      icon: "shield",
      items: [
        { label: "自动下单", value: config.trading?.auto_order_enabled ? "存在风险" : "已关闭" },
        { label: "人工执行", value: boolText(config.trading?.manual_execution_required), note: "所有提醒都需要人工核对后手动操作。" },
        { label: "交易密钥", value: readiness?.forbidden_env.status === "ready" ? "未发现" : "存在风险", note: forbiddenEnvNote(readiness?.forbidden_env.status) },
        { label: "允许交易对", value: Array.isArray(config.trading?.allowed_symbols) ? config.trading.allowed_symbols.join(" / ") : "未说明" }
      ]
    },
    {
      title: "复盘能力",
      icon: "flask",
      items: [
        { label: "质量样本目标", value: String((config.eval?.financial_quality as { minimum_scored_count?: unknown } | undefined)?.minimum_scored_count ?? "未说明") },
        { label: "默认审计旁路", value: shadowLabel(config.shadow?.worker_mode), note: "旁路只用于审计，不代表生产自动切换。" },
        { label: "研究检索", value: config.research?.enabled ? "已开启" : "未开启" }
      ]
    }
  ];

  return (
    <section className="panel section-gap" aria-label="配置明细">
      <div className="section-heading-row">
        <div>
          <h2>配置明细</h2>
          <p className="muted">这里展示的是脱敏后的当前生效配置，并按产品语义翻译；更改仍需改配置文件并重启。</p>
        </div>
      </div>
      <div className="config-grid">
        {sections.map((section) => (
          <article className="config-card" key={section.title}>
            <h3>
              <Icon name={section.icon} size={15} />
              {section.title}
            </h3>
            <dl className="config-dl">
              {section.items.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>
                    <span>{item.value}</span>
                    {item.note ? <small>{item.note}</small> : null}
                  </dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}

export default async function ConfigPage() {
  const result = await getSystemConfig();
  const config: Record<string, Record<string, unknown>> = result.ok ? result.data : {};
  const readiness = result.ok ? result.data.readiness : undefined;

  const autoOrder = config.trading?.auto_order_enabled as boolean | undefined;
  const prodReady = readiness?.prod_actionable.prod_actionable_ready ?? false;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>生产提醒就绪检查</h1>
          <p>先看真实模型、真实行情、Bark、事件状态和人工安全边界是否同时满足；不满足时只能算演练或阻塞。</p>
        </div>
      </header>

      {!result.ok ? (
        <div className="error-state" role="alert">配置读取失败，请稍后刷新。</div>
      ) : (
        <>
          <div className="status-bar">
            <span className="status-item">
              <span className={`status-dot ${prodReady ? "ok" : "warn pulse"}`} />
              生产提醒状态 <strong>{prodReady ? "就绪待严格自测" : "未就绪"}</strong>
            </span>
            <span className="status-item">
              <Icon name={autoOrder ? "x" : "check"} size={14} />
              自动下单 <strong className={autoOrder ? "config-value-false" : "config-value-true"}>{autoOrder ? "存在风险" : "已关闭"}</strong>
            </span>
            <span className="status-item">发布口径 <strong>必须通过严格生产自测</strong></span>
          </div>

          <section className="panel section-gap" aria-label="当前证明范围">
            <div className="section-heading-row">
              <div>
                <h2>当前能证明什么</h2>
                <p className="muted">{overallReadinessSummary(readiness)}</p>
              </div>
              <span className={`badge ${prodReady ? "badge-success" : "badge-pending"}`}>
                {prodReady ? "待严格自测" : "演练或阻塞"}
              </span>
            </div>
            <div className="risk-summary-grid">
              <article className="risk-summary-item">
                <span>模型内容</span>
                <strong>{readinessShortLabel(readiness?.decision_engine.status ?? "missing_env")}</strong>
                <p>没有真实模型配置时，页面不会出现可当作生产依据的模型输出。</p>
              </article>
              <article className="risk-summary-item">
                <span>行情事实</span>
                <strong>{readinessShortLabel(readiness?.market_data.status ?? "fixture_only")}</strong>
                <p>本地演练行情不能满足生产执行事实，只能验证流程。</p>
              </article>
              <article className="risk-summary-item">
                <span>手机通知</span>
                <strong>{readinessShortLabel(readiness?.notification.status ?? "disabled")}</strong>
                <p>Bark 未成功发送时，不能称为完整生产提醒闭环。</p>
              </article>
            </div>
          </section>

          <ReadinessChecklist readiness={readiness} />

          <section className={`panel safety-banner ${autoOrder ? "danger-banner" : ""}`} aria-label="配置安全边界">
            <strong>{autoOrder ? "危险：自动下单被打开" : "自动下单关闭：系统只生成提醒与审计记录"}</strong>
            <span>{autoOrder ? "前端仍不提供下单按钮；请立即核对环境并回滚配置。" : "配置页只读展示脱敏状态；修改入口是配置文件和重启，不是前端表单。"}</span>
          </section>

          <ConfigDetails config={config} readiness={readiness} />
        </>
      )}
    </>
  );
}
