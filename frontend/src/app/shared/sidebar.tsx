"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, type IconName } from "./icons";

type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  group: string;
  matchPath: string;
  diagnosticOnly?: boolean;
};

const NAV: NavItem[] = [
  { href: "/", label: "提醒控制台", icon: "dashboard", group: "业务", matchPath: "/" },
  { href: "/runs", label: "提醒记录", icon: "bell", group: "业务", matchPath: "/runs" },
  { href: "/manual-run", label: "新建提醒", icon: "plus", group: "业务", matchPath: "/manual-run" },
  { href: "/runs?columns=observability", label: "诊断视图", icon: "activity", group: "评估", matchPath: "/runs", diagnosticOnly: true },
  { href: "/eval?tab=quality", label: "质量复盘", icon: "flask", group: "评估", matchPath: "/eval" },
  { href: "/config", label: "配置", icon: "settings", group: "配置", matchPath: "/config" }
];

function isActive(item: NavItem, pathname: string, columns: string | null): boolean {
  if (pathname.startsWith("/eval/runs/") && item.matchPath === "/eval") {
    return true;
  }
  if (pathname.startsWith("/runs/") && item.matchPath === "/runs") {
    return item.href.includes("columns=observability") ? columns === "observability" : columns !== "observability";
  }
  if (item.matchPath !== pathname) {
    return false;
  }
  if (pathname === "/runs" && item.matchPath === "/runs") {
    const wantsObservability = item.href.includes("columns=observability");
    return wantsObservability ? columns === "observability" : columns !== "observability";
  }
  return true;
}

function isDiagnosticContext(_pathname: string, columns: string | null, _tab: string | null): boolean {
  return columns === "observability";
}

export function Sidebar() {
  const [hydrated, setHydrated] = useState(false);
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const columns = hydrated ? searchParams.get("columns") : null;
  const tab = hydrated ? searchParams.get("tab") : null;
  const activePathname = hydrated ? pathname : "";
  const diagnosticContext = hydrated && isDiagnosticContext(activePathname, columns, tab);

  useEffect(() => {
    setHydrated(true);
  }, []);

  const visibleNav = NAV.filter((item) => !item.diagnosticOnly || diagnosticContext);
  const groups = Array.from(new Set(visibleNav.map((item) => item.group)));

  return (
    <>
      {groups.map((group) => (
        <div key={group}>
          <div className="nav-group-label">{group}</div>
          <nav className="nav-list" aria-label={group}>
            {visibleNav.filter((item) => item.group === group).map((item) => {
              const active = hydrated && isActive(item, activePathname, columns);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  prefetch={false}
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
