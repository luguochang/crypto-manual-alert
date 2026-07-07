"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Icon, type IconName } from "./icons";

type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  group: string;
  // 用于判断 active 的路径 + 可选 query 参数
  matchPath: string;
  matchView?: string;
};

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: "dashboard", group: "总览", matchPath: "/" },
  { href: "/runs?view=alerts", label: "提醒业务", icon: "bell", group: "业务", matchPath: "/runs", matchView: "alerts" },
  { href: "/manual-run", label: "新建提醒", icon: "plus", group: "业务", matchPath: "/manual-run" },
  { href: "/runs?view=observe", label: "Agent 可观测", icon: "activity", group: "分析与优化", matchPath: "/runs", matchView: "observe" },
  { href: "/eval", label: "评估", icon: "flask", group: "分析与优化", matchPath: "/eval" },
  { href: "/config", label: "配置", icon: "settings", group: "分析与优化", matchPath: "/config" }
];

function isActive(item: NavItem, pathname: string, view: string | null): boolean {
  if (item.matchPath !== pathname) {
    // /runs/[traceId] 详情页：按默认 tab 高亮对应导航项
    if (pathname.startsWith("/runs/") && item.matchPath === "/runs") {
      return false;
    }
    return false;
  }
  if (item.matchView) {
    return view === item.matchView;
  }
  return true;
}

export function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const view = searchParams.get("view");

  const groups = Array.from(new Set(NAV.map((item) => item.group)));

  return (
    <>
      {groups.map((group) => (
        <div key={group}>
          <div className="nav-group-label">{group}</div>
          <nav className="nav-list" aria-label={group}>
            {NAV.filter((item) => item.group === group).map((item) => {
              const active = isActive(item, pathname, view);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={active ? "active" : ""}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon name={item.icon} size={18} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      ))}
    </>
  );
}
