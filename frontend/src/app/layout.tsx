import type { Metadata, Viewport } from "next";
import { connection } from "next/server";

import { AppShell } from "@/components/app-shell";

import "./globals.css";

export const metadata: Metadata = {
  title: "Signal Desk",
  description: "人工决策辅助工作台",
  icons: {
    icon: "/signal-desk-mark.svg",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Authentication mode is a deployment-time setting and must not be frozen into the image.
  await connection();
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
