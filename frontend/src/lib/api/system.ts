import { apiRequest } from "@/lib/api/client";
import {
  type ManualRunRequest,
  manualRunResponseSchema
} from "@/lib/schemas/manual-run";
import { systemConfigSchema, systemHealthSchema } from "@/lib/schemas/system";

// 手动触发只传用户显式输入的参数，不在前端拼接 secret 或服务端配置。
export function createManualRun(payload: ManualRunRequest) {
  return apiRequest("/api/runs/manual", manualRunResponseSchema, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getSystemHealth() {
  return apiRequest("/api/system/health", systemHealthSchema);
}

// 只读配置快照（safe_dict 已脱敏 bark key 等），用于配置界面展示。
export function getSystemConfig() {
  return apiRequest("/api/system/config", systemConfigSchema);
}
