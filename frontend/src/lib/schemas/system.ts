import { z } from "zod";

// /api/system/health
export const systemHealthSchema = z
  .object({
    service: z.string(),
    storage: z.string(),
    mode: z.string()
  })
  .passthrough();

// /api/system/config — safe_dict() 返回的脱敏配置快照。
// 结构是 { section: { field: value } }，value 类型多样（bool/str/num/list），
// 用 permissive schema 让 Config 页通用渲染各段，不硬编码每个字段。
export const systemConfigSchema = z.record(
  z.string(),
  z.record(z.string(), z.unknown())
);

export type SystemHealth = z.output<typeof systemHealthSchema>;
export type SystemConfig = z.output<typeof systemConfigSchema>;
