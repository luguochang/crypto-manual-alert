import { Plus, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { AuthenticatedAppShell } from "@/components/authenticated-app-shell";
import { BrandLockup } from "@/components/brand-lockup";
import { PrimaryNavigation } from "@/components/primary-navigation";
import { ShellTopbar } from "@/components/shell-topbar";
import { requiresAuthenticatedRuntime } from "@/lib/runtime/app-environment";

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  if (requiresAuthenticatedRuntime()) {
    return <AuthenticatedAppShell>{children}</AuthenticatedAppShell>;
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <BrandLockup />

        <Link className="sidebar-primary-action" href="/work" prefetch={false}>
          <Plus size={17} aria-hidden="true" />
          新建分析
        </Link>

        <PrimaryNavigation />

        <div className="environment-note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>
            <strong>Local workspace</strong>
            人工执行边界
          </span>
        </div>
      </aside>
      <div className="app-frame">
        <ShellTopbar />
        <main className="main-content" id="main-content" tabIndex={-1}>{children}</main>
      </div>
    </div>
  );
}
