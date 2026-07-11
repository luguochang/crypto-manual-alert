export default function Loading() {
  return (
    <section className="route-state" aria-label="提醒工作台载入中">
      <div className="route-state-panel">
        <span className="badge badge-running">正在准备</span>
        <h1>提醒工作台正在载入</h1>
        <p>正在读取人工提醒、配置就绪状态和复盘摘要。系统只生成提醒，不会自动下单。</p>
        <div className="route-state-skeleton" aria-hidden="true">
          <span className="skeleton" />
          <span className="skeleton" />
          <span className="skeleton" />
        </div>
      </div>
    </section>
  );
}
