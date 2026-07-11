export default function NotFound() {
  return (
    <section className="route-state" aria-label="提醒不存在">
      <div className="route-state-panel">
        <span className="badge badge-pending">需要确认</span>
        <h1>没有找到这条提醒</h1>
        <p>提醒工作台没有找到对应记录。</p>
        <p>这条提醒可能还没有生成，或本地数据已经被清理。系统不会因为这个页面自动下单。</p>
        <div className="route-state-actions">
          <a className="button" href="/runs">
            返回提醒记录
          </a>
          <a className="button button-secondary" href="/manual-run">
            新建提醒
          </a>
          <a className="button button-ghost" href="/config">
            查看就绪检查
          </a>
        </div>
      </div>
    </section>
  );
}
