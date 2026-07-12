import { redirect } from "next/navigation";

/**
 * 根路径 - 重定向到 /home
 *
 * Phase 2 更新：原 Phase 0 介绍页已移除，
 * 根路径直接重定向到仪表盘首页。
 */
export default function RootPage() {
  redirect("/home");
}
