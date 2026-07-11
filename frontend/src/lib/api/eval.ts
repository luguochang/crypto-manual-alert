import { apiRequest } from "@/lib/api/client";
import {
  evalCaseFrozenInputSchema,
  evalCandidateListSchema,
  evalOutcomeListSchema,
  evalPromotionArtifactsSchema,
  evalRunDetailSchema,
  evalRunListSchema,
  evalRunSummarySchema
} from "@/lib/schemas/eval";

export function listEvalCandidates(options?: { dataset?: string; status?: string; severity?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (options?.dataset) {
    params.set("dataset", options.dataset);
  }
  if (options?.status) {
    params.set("status", options.status);
  }
  if (options?.severity) {
    params.set("severity", options.severity);
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

export function getEvalPromotionArtifacts(evalRunId: string) {
  return apiRequest(
    `/api/eval/runs/${encodeURIComponent(evalRunId)}/promotion-artifacts`,
    evalPromotionArtifactsSchema
  );
}

export function getEvalCaseFrozenInput(caseId: string) {
  return apiRequest(`/api/eval/cases/${encodeURIComponent(caseId)}/frozen-input`, evalCaseFrozenInputSchema);
}

export function getEvalFrozenInput(frozenInputHash: string) {
  return apiRequest(`/api/eval/frozen-inputs/${encodeURIComponent(frozenInputHash)}`, evalCaseFrozenInputSchema);
}

export function createEvalRun(payload: {
  dataset_name?: string;
  badcase_ids?: number[];
  mode: string;
  limit?: number;
}) {
  return apiRequest("/api/eval/runs", evalRunSummarySchema, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listEvalOutcomes(options?: { evaluationTarget?: string }) {
  const query = options?.evaluationTarget
    ? `?evaluation_target=${encodeURIComponent(options.evaluationTarget)}`
    : "";
  return apiRequest(`/api/eval/outcomes${query}`, evalOutcomeListSchema);
}
