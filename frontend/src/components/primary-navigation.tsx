"use client";

import { BriefcaseBusiness, History, Inbox, Library, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { label: "Work", icon: BriefcaseBusiness, href: "/work" },
  { label: "Runs", icon: History, href: "/runs" },
  { label: "Inbox", icon: Inbox, href: "/inbox" },
  { label: "Library", icon: Library, href: null },
  { label: "Settings", icon: Settings, href: null },
] as const;

export function PrimaryNavigation() {
  const pathname = usePathname();
  return (
    <nav className="primary-navigation" aria-label="Primary navigation">
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
        ) : (
          <button
            className="navigation-item"
            type="button"
            disabled
            aria-label={`${label}，尚未开放`}
            title="尚未开放"
            key={label}
          >
            <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
            <span>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
