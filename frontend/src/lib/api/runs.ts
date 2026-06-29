import { apiRequest } from "@/lib/api/client";
import {
  runDetailSchema,
  runListSchema
} from "@/lib/schemas/runs";

export function listRuns() {
  return apiRequest("/api/runs", runListSchema);
}

export function getRunDetail(traceId: string, options?: { includePayloads?: boolean }) {
  const query = options?.includePayloads ? "?include_payloads=true" : "";
  return apiRequest(`/api/runs/${encodeURIComponent(traceId)}${query}`, runDetailSchema);
}
