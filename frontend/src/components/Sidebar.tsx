"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, type IconName } from "@/app/shared/icons";

/**
 * V2 侧边导航栏
 *
 * 导航到 Home / Work / Inbox / Library / Settings。
 * 当前页面高亮，Inbox 显示未读数 badge。
 *
 * 设计文档 15-frontend-and-config-management.md 第三节。
 * 使用 CSS 变量保持与全局暗色主题一致。
 */

type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  badge?: number; // Inbox 未读数（运行时注入）
};

const NAV_ITEMS: NavItem[] = [
  { href: "/home", label: "首页", icon: "dashboard" },
  { href: "/work", label: "工作台", icon: "activity" },
  { href: "/inbox", label: "收件箱", icon: "bell" },
  { href: "/library", label: "分析库", icon: "database" },
  { href: "/settings", label: "设置", icon: "settings" },
];

export function Sidebar() {
  const [hydrated, setHydrated] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setHydrated(true);
  }, []);

  // Inbox 未读数 - Phase 2 占位，后续接入 API
  const inboxBadge = 0;

  return (
    <aside
      style={{
        width: "220px",
        minHeight: "100vh",
        backgroundColor: "var(--color-bg-secondary)",
        borderRight: "1px solid var(--color-border)",
        padding: "1rem 0.75rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.25rem",
        position: "sticky",
        top: 0,
        flexShrink: 0,
      }}
    >
      {/* Logo / 品牌区 */}
      <div
        style={{
          padding: "0.5rem 0.75rem 1rem",
          borderBottom: "1px solid var(--color-border)",
          marginBottom: "0.75rem",
        }}
      >
        <Link
          href="/home"
          style={{
            textDecoration: "none",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          <span
            style={{
              width: "28px",
              height: "28px",
              borderRadius: "6px",
              backgroundColor: "var(--color-brand)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#0f172a",
              fontWeight: 800,
              fontSize: "0.875rem",
              flexShrink: 0,
            }}
          >
            C
          </span>
          <span
            style={{
              fontSize: "0.875rem",
              fontWeight: 700,
              color: "var(--color-text-primary)",
            }}
          >
            Crypto Alert
          </span>
        </Link>
      </div>

      {/* 导航项 */}
      <nav style={{ display: "flex", flexDirection: "column", gap: "0.125rem" }}>
        {NAV_ITEMS.map((item) => {
          const isActive =
            hydrated &&
            (pathname === item.href ||
              (item.href !== "/home" && pathname.startsWith(item.href)));

          const showBadge = item.href === "/inbox" && inboxBadge > 0;

          return (
            <Link
              key={item.href}
              href={item.href}
              prefetch={false}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.625rem",
                padding: "0.5rem 0.75rem",
                borderRadius: "6px",
                textDecoration: "none",
                fontSize: "0.8125rem",
                fontWeight: isActive ? 600 : 400,
                color: isActive
                  ? "var(--color-text-primary)"
                  : "var(--color-text-secondary)",
                backgroundColor: isActive
                  ? "var(--color-bg-tertiary)"
                  : "transparent",
                border: isActive
                  ? "1px solid var(--color-border-light)"
                  : "1px solid transparent",
                transition: "background-color 0.15s, color 0.15s",
              }}
            >
              <Icon
                name={item.icon}
                size={18}
                color={
                  isActive
                    ? "var(--color-brand)"
                    : "var(--color-text-muted)"
                }
              />
              <span style={{ flex: 1 }}>{item.label}</span>
              {showBadge && (
                <span
                  style={{
                    backgroundColor: "var(--color-error)",
                    color: "#fff",
                    fontSize: "0.65rem",
                    fontWeight: 700,
                    padding: "0.125rem 0.375rem",
                    borderRadius: "999px",
                    minWidth: "18px",
                    textAlign: "center",
                  }}
                >
                  {inboxBadge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* 底部状态指示 */}
      <div
        style={{
          marginTop: "auto",
          padding: "0.75rem",
          borderTop: "1px solid var(--color-border)",
          fontSize: "0.7rem",
          color: "var(--color-text-muted)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.375rem",
            marginBottom: "0.25rem",
          }}
        >
          <span
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              backgroundColor: "var(--color-success)",
            }}
          />
          Agent Server: localhost:2024
        </div>
        <div style={{ fontFamily: "monospace", fontSize: "0.65rem" }}>
          V2 Phase 2
        </div>
      </div>
    </aside>
  );
}
