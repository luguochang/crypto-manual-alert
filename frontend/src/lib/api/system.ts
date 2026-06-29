import { apiRequest } from "@/lib/api/client";
import {
  type ManualRunRequest,
  manualRunResponseSchema
} from "@/lib/schemas/manual-run";

// 手动触发只传用户显式输入的参数，不在前端拼接 secret 或服务端配置。
export function createManualRun(payload: ManualRunRequest) {
  return apiRequest("/api/runs/manual", manualRunResponseSchema, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
