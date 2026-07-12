import type { NextConfig } from "next";

/**
 * Next.js 15 配置
 * Phase 0: 基础骨架，暂无特殊配置需求
 */
const nextConfig: NextConfig = {
  // 允许开发时代理到 Agent Server（localhost:2024）
  // 生产环境应通过反向代理处理
  experimental: {},
};

export default nextConfig;
