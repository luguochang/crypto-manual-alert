import { apiRequest } from "@/lib/api/client";
import {
  runDetailSchema,
  runListSchema
} from "@/lib/schemas/runs";

export type ListRunsOptions = {
  limit?: number;
  offset?: number;
  status?: string;
  symbol?: string;
  allowed?: boolean;
};

export function listRuns(options: ListRunsOptions = {}) {
  const params = new URLSearchParams();
  if (options.limit != null) {
    params.set("limit", String(options.limit));
  }
  if (options.offset != null) {
    params.set("offset", String(options.offset));
  }
  if (options.status) {
    params.set("status", options.status);
  }
  if (options.symbol) {
    params.set("symbol", options.symbol);
  }
  if (options.allowed != null) {
    params.set("allowed", String(options.allowed));
  }
  const query = params.toString();
  return apiRequest(`/api/runs${query ? `?${query}` : ""}`, runListSchema);
}

export function getRunDetail(traceId: string, options?: { includePayloads?: boolean }) {
  const query = options?.includePayloads ? "?include_payloads=true" : "";
  return apiRequest(`/api/runs/${encodeURIComponent(traceId)}${query}`, runDetailSchema);
}
