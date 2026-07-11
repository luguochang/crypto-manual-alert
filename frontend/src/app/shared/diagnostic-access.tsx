import Link from "next/link";
import { Icon } from "@/app/shared/icons";
import type { ApiResult } from "@/lib/schemas/api";
import type { SystemConfig } from "@/lib/schemas/system";

export function diagnosticRoutesEnabled(config: ApiResult<SystemConfig>): boolean {
  if (!config.ok) {
    return false;
  }
  return config.data.diagnostic?.routes_enabled === true;
}

export function DiagnosticDisabledNotice({
  backHref,
  backLabel,
}: {
  backHref: string;
  backLabel: string;
}) {
  return (
    <>
      <header className="page-header">
        <div>
          <h1>诊断入口已关闭</h1>
          <p>当前环境没有开放工程诊断入口。普通复核请使用业务页面；需要排障时，请在专用工程环境开启诊断路由。</p>
        </div>
        <Link className="button button-secondary" href={backHref} prefetch={false}>
          <Icon name="chevron-right" size={14} /> {backLabel}
        </Link>
      </header>
      <section className="panel section-gap" aria-label="诊断入口说明">
        <div className="panel-heading">
          <div>
            <h2>普通用户路径保持可读</h2>
            <p className="muted">
              工程排障明细已在当前环境隐藏；生产工作台默认只展示提醒建议、模型审阅、证据摘要、通知状态和质量复盘。
            </p>
          </div>
        </div>
        <div className="toolbar">
          <Link className="button" href={backHref} prefetch={false}>
            <Icon name="bell" size={16} /> {backLabel}
          </Link>
          <Link className="button button-secondary" href="/config" prefetch={false}>
            <Icon name="shield" size={16} /> 查看配置检查
          </Link>
        </div>
      </section>
    </>
  );
}
