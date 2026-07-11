"use client";

export default function Error({
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="route-state" aria-label="提醒工作台错误恢复">
      <div className="route-state-panel route-state-panel-danger">
        <span className="badge badge-failed">需要重试</span>
        <h1>提醒工作台暂时无法显示</h1>
        <p>页面读取过程中遇到问题。已保留人工确认边界，系统不会自动下单或发送交易指令。</p>
        <div className="route-state-actions">
          <button className="button" type="button" onClick={reset}>
            重新加载
          </button>
          <a className="button button-secondary" href="/manual-run">
            新建提醒
          </a>
          <a className="button button-ghost" href="/runs">
            返回提醒记录
          </a>
        </div>
      </div>
    </section>
  );
}
