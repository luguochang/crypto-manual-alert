import type { EvalCase, EvalScore } from "@/lib/schemas/eval";

export function shortId(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

export function severityClass(severity: string) {
  if (severity === "critical" || severity === "high") {
    return "badge-failed";
  }
  if (severity === "medium") {
    return "badge-pending";
  }
  return "badge-running";
}

export function resultClass(passed: boolean) {
  return passed ? "badge-success" : "badge-failed";
}

export function replayClass(status: string | undefined) {
  if (status === "completed") {
    return "badge-success";
  }
  if (status === "failed" || status === "error") {
    return "badge-failed";
  }
  return "badge-pending";
}

export function truncate(value: string | null | undefined, max = 96) {
  const text = value?.trim();
  if (!text) {
    return "-";
  }
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

export function metadataNumber(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "number" ? String(value) : "-";
}

export function evidenceText(score: EvalScore) {
  return score.evidence_refs.length > 0 ? score.evidence_refs.join(", ") : "-";
}

export function observedText(item: EvalCase) {
  const trace = item.input_summary.trace;
  if (!trace || typeof trace !== "object") {
    return "-";
  }
  const data = trace as Record<string, unknown>;
  const action = typeof data.final_action === "string" ? data.final_action : "-";
  const allowed = typeof data.allowed === "boolean" ? String(data.allowed) : "-";
  return `${action} / ${allowed}`;
}
