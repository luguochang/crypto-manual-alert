import type { DataDeletion } from "@/lib/schemas/product-api";


type LifecycleReceiptListProps = {
  receipts: DataDeletion["receipts"];
};

const phaseLabels: Record<DataDeletion["receipts"][number]["phase"], string> = {
  delete: "删除",
  survivor_scan: "残留扫描",
  retention_queue: "到期队列",
};

export function LifecycleReceiptList({ receipts }: LifecycleReceiptListProps) {
  if (receipts.length === 0) return null;

  return (
    <div className="lifecycle-system-list" aria-label="不可变删除回执">
      <strong>不可变回执 · {receipts.length} 条</strong>
      {receipts.map((receipt) => (
        <div key={receipt.id}>
          <span>{receipt.system} · {phaseLabels[receipt.phase]}</span>
          <span data-state={receipt.outcome} title={receipt.receipt_hash}>
            {receipt.outcome} · {receipt.survivor_count} 残留 · {receipt.receipt_hash.slice(0, 10)}
          </span>
        </div>
      ))}
    </div>
  );
}
