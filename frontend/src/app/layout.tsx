import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

/**
 * 根布局
 * - 设置 html lang="zh-CN"
 * - 引入全局样式
 * - 暗色主题背景
 * - 包含 V2 侧边导航栏 + 主内容区域
 *
 * 设计文档 15-frontend-and-config-management.md 第三节。
 */
export const metadata: Metadata = {
  title: "Crypto Alert V2",
  description: "加密货币提醒 Agent - 市场分析与风险管理",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        style={{
          backgroundColor: "var(--color-bg-primary)",
          color: "var(--color-text-primary)",
          minHeight: "100vh",
        }}
      >
        <div
          style={{
            display: "flex",
            minHeight: "100vh",
          }}
        >
          <Sidebar />
          <main
            style={{
              flex: 1,
              minWidth: 0, // 防止 flex 子项溢出
              overflowX: "hidden",
            }}
          >
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
