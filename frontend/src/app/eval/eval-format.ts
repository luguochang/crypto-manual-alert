import type { EvalCase, EvalScore } from "@/lib/schemas/eval";
import { productDisplayText } from "@/app/shared/product-copy";
import { safeDisplayContent } from "@/app/shared/safe-error";

const EVAL_LABELS: Record<string, string> = {
  candidate_gate: "候选门槛",
  candidate_gate_failed: "候选门槛未通过",
  counter_thesis_readback: "反向观点复核",
  data_gap_honesty: "数据缺口诚实度",
  eval_side_effect_guard_failed: "复盘副作用检查失败",
  eval_side_effect_violation: "复盘副作用异常",
  execution_plan_unclear: "执行计划不清晰",
  expected_no_trade_violation: "应空仓但未阻断",
  failure_cases: "问题样本集",
  grounding_error: "证据支撑不足",
  critical: "严重",
  high: "高风险",
  llm: "模型评审",
  llm_fixture: "本地模型评审",
  llm_judge_invalid_response: "模型评审返回异常",
  low: "低风险",
  manual_only_violation: "人工执行边界异常",
  medium: "中风险",
  none: "无",
  open: "待处理",
  plan_semantic_candidate_failed: "计划语义候选未通过",
  rule: "规则评审",
  schema_action_invalid: "动作枚举异常",
  selected_badcases: "已选问题样本",
  trace_incomplete: "提醒记录不完整",
  unsafe_entry_stop_plan: "入场止损计划不安全",
  unsafe_switch_readiness: "切换准备状态不安全"
};

const JUDGE_LABELS: Record<string, string> = {
  "eval.side_effect_guard": "副作用检查",
  "llm.data_gap_honesty": "数据缺口评审",
  "llm.evidence_grounding": "证据支撑评审",
  "llm.execution_clarity": "执行清晰度评审",
  "llm.fixture_grounding": "本地证据支撑评审",
  "llm.opposing_thesis": "反向观点评审",
  "llm.overconfidence": "过度自信评审",
  "rule.action_enum": "动作枚举检查",
  "rule.candidate_gate": "候选门槛检查",
  "rule.expected_no_trade": "空仓边界检查",
  "rule.final_switch_readiness": "切换准备检查",
  "rule.manual_only": "人工执行边界检查",
  "rule.opening_requirements": "开仓要素检查",
  "rule.plan_semantic_candidate": "计划语义检查",
  "rule.trace_required_spans": "提醒记录完整性检查"
};

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

export function safeEvalText(value: string | null | undefined, max = 96) {
  const text = value?.trim();
  if (!text) {
    return "-";
  }
  return truncate(safeDisplayContent(text), max);
}

export function safeEvalLabel(value: string | null | undefined, max = 96) {
  const text = value?.trim();
  if (!text) {
    return "-";
  }
  return EVAL_LABELS[text] ?? JUDGE_LABELS[text] ?? productDisplayText(safeEvalText(text, max));
}

export function metadataNumber(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "number" ? String(value) : "-";
}

export function evidenceText(score: Pick<EvalScore, "evidence_refs">) {
  if (score.evidence_refs.length === 0) {
    return "-";
  }
  return score.evidence_refs.map((item) => safeEvalText(item)).join(", ");
}

export function observedText(item: EvalCase) {
  const trace = item.input_summary.trace;
  if (!trace || typeof trace !== "object") {
    return "-";
  }
  const data = trace as Record<string, unknown>;
  const action = typeof data.final_action === "string" ? productDisplayText(safeEvalText(data.final_action)) : "-";
  const allowed = typeof data.allowed === "boolean" ? (data.allowed ? "可人工复核" : "已阻断") : "-";
  return `${action} / ${allowed}`;
}
