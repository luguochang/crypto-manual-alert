import { Plus, ShieldCheck } from "lucide-react";
import Link from "next/link";

export function ShellTopbar() {
  return (
    <header className="app-topbar">
      <div className="app-topbar-context">
        <span className="app-topbar-live" aria-hidden="true" />
        <span>Evidence-first intelligence</span>
      </div>
      <div className="app-topbar-actions">
        <span className="app-topbar-boundary">
          <ShieldCheck size={16} aria-hidden="true" />
          Manual only
        </span>
        <Link className="app-topbar-primary" href="/work" prefetch={false}>
          <Plus size={16} aria-hidden="true" />
          创建任务
        </Link>
      </div>
    </header>
  );
}
