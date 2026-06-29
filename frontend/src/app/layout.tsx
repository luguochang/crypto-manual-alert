import type { Metadata } from "next";
import Link from "next/link";
import "./styles.css";

export const metadata: Metadata = {
  title: "Jiami Workbench",
  description: "FastAPI + Next.js operations workbench"
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/manual-run", label: "Manual Run" },
  { href: "/runs", label: "Runs" }
];

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
              <span className="brand-mark">J</span>
              <div>
                <strong>Jiami</strong>
                <span>Ops Workbench</span>
              </div>
            </div>
            <nav className="nav-list" aria-label="主导航">
              {navItems.map((item) => (
                <Link key={item.href} href={item.href}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="main-panel">{children}</main>
        </div>
      </body>
    </html>
  );
}
