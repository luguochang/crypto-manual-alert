import { apiRequest } from "@/lib/api/client";
import {
  runDetailSchema,
  runListSchema
} from "@/lib/schemas/runs";

export function listRuns() {
  return apiRequest("/api/runs", runListSchema);
}

export function getRunDetail(traceId: string) {
  return apiRequest(`/api/runs/${encodeURIComponent(traceId)}`, runDetailSchema);
}
