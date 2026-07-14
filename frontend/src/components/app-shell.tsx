import { Radar, ShieldCheck } from "lucide-react";

import { PrimaryNavigation } from "@/components/primary-navigation";

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup" aria-label="Signal Desk">
          <span className="brand-mark" aria-hidden="true">
            <Radar size={22} strokeWidth={1.8} />
          </span>
          <span className="brand-copy">
            <strong>Signal Desk</strong>
            <span>Decision workspace</span>
          </span>
        </div>

        <PrimaryNavigation />

        <div className="environment-note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>
            <strong>Local workspace</strong>
            人工执行边界
          </span>
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
