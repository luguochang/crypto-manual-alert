import { ManualRunForm } from "./run-form";

export default function ManualRunPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <h1>Manual Run</h1>
          <p>手动提交一次运行任务，返回 trace_id 后可进入详情页追踪。</p>
        </div>
      </header>
      <ManualRunForm />
    </>
  );
}
