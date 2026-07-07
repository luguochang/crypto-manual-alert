import { Icon, type IconName } from "./icons";
import type { RunStatus } from "@/lib/schemas/runs";

const statusText: Record<RunStatus, string> = {
  running: "运行中",
  allowed: "允许提醒",
  blocked: "风控阻断",
  failed: "失败",
  ok: "完成"
};

const statusClass: Record<RunStatus, string> = {
  running: "badge-running",
  allowed: "badge-success",
  blocked: "badge-failed",
  failed: "badge-failed",
  ok: "badge-success"
};

const statusIcon: Record<RunStatus, IconName> = {
  running: "activity",
  allowed: "check",
  blocked: "x",
  failed: "alert",
  ok: "check"
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`badge ${statusClass[status]}`}>
      <Icon name={statusIcon[status]} size={13} />
      {statusText[status]}
    </span>
  );
}
