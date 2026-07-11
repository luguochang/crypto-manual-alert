import { ManualRunForm } from "./run-form";

export default function ManualRunPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <h1>新建提醒</h1>
          <p>填写交易对、周期和持仓信息，生成一条仅供人工复核的提醒建议。</p>
        </div>
      </header>
      <ManualRunForm />
    </>
  );
}
