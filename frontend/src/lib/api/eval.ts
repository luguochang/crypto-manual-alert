import { apiRequest } from "@/lib/api/client";
import {
  evalCandidateListSchema,
  evalOutcomeListSchema,
  evalRunDetailSchema,
  evalRunListSchema
} from "@/lib/schemas/eval";

export function listEvalCandidates(options?: { dataset?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (options?.dataset) {
    params.set("dataset", options.dataset);
  }
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest(`/api/eval/candidates${query}`, evalCandidateListSchema);
}

export function listEvalRuns(options?: { limit?: number }) {
  const query = options?.limit ? `?limit=${encodeURIComponent(String(options.limit))}` : "";
  return apiRequest(`/api/eval/runs${query}`, evalRunListSchema);
}

export function getEvalRunDetail(evalRunId: string) {
  return apiRequest(`/api/eval/runs/${encodeURIComponent(evalRunId)}`, evalRunDetailSchema);
}

export function listEvalOutcomes(options?: { evaluationTarget?: string }) {
  const query = options?.evaluationTarget
    ? `?evaluation_target=${encodeURIComponent(options.evaluationTarget)}`
    : "";
  return apiRequest(`/api/eval/outcomes${query}`, evalOutcomeListSchema);
}
