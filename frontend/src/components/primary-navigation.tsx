"use client";

import { BriefcaseBusiness, History, Home, Inbox, Library, Radar, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { label: "首页", icon: Home, href: "/home" },
  { label: "工作台", icon: BriefcaseBusiness, href: "/work" },
  { label: "运行记录", icon: History, href: "/runs" },
  { label: "审核收件箱", icon: Inbox, href: "/inbox" },
  { label: "报告资料库", icon: Library, href: "/library" },
  { label: "持续监控", icon: Radar, href: "/monitors" },
  { label: "通知设置", icon: Settings, href: "/settings" },
] as const;

export function PrimaryNavigation() {
  const pathname = usePathname();
  return (
    <nav className="primary-navigation" aria-label="主导航">
      {items.map(({ label, icon: Icon, href }) => {
        const active = href !== null && (pathname === href || pathname.startsWith(`${href}/`));
        return href !== null ? (
          <Link
            className={`navigation-item${active ? " is-active" : ""}`}
            href={href}
            prefetch={false}
            aria-current={active ? "page" : undefined}
            key={label}
          >
            <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
            <span>{label}</span>
          </Link>
        ) : null;
      })}
    </nav>
  );
}
