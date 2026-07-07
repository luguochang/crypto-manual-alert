import type { Metadata } from "next";
import { Suspense } from "react";
import "./styles.css";
import { Sidebar } from "./shared/sidebar";

export const metadata: Metadata = {
  title: "Crypto Manual Alert",
  description: "人工确认的加密货币操作提醒与可观测工作台"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <span className="brand-mark">C</span>
              <div>
                <strong>Crypto</strong>
                <span>Ops Workbench</span>
              </div>
            </div>
            <Suspense fallback={null}>
            <Sidebar />
            </Suspense>
            <div className="sidebar-footer">
              人工确认 · 非自动交易
              <br />
              manual_execution_required
            </div>
          </aside>
          <main className="main-panel">{children}</main>
        </div>
      </body>
    </html>
  );
}
