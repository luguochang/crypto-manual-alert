import type { Metadata } from "next";
import Link from "next/link";
import "./styles.css";

export const metadata: Metadata = {
  title: "Crypto Manual Alert",
  description: "FastAPI + Next.js operations workbench"
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/manual-run", label: "Manual Run" },
  { href: "/runs", label: "Runs" },
  { href: "/eval", label: "Eval" }
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
              <span className="brand-mark">C</span>
              <div>
                <strong>Crypto</strong>
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
