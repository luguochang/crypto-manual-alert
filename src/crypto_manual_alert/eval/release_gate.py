from __future__ import annotations

from typing import Any

from crypto_manual_alert.eval.schema import EvalReplayOutput, EvalScore

from .complete_replay_refs import COMPLETE_REPLAY_REF_KEYS
from .release_promotion_review import promotion_review
from .side_effect_proof import validate_no_production_side_effect_proof


REQUIRED_WORKER_ARTIFACT_COUNT = 7
COMPLETE_REPLAY_REF_NAMES = set(COMPLETE_REPLAY_REF_KEYS)


def build_release_gate_summary(
    *,
    scores: list[EvalScore],
    replay_outputs: dict[str, EvalReplayOutput],
    cases: list[Any] | None = None,
    eval_run_id: str | None = None,
    promotion_artifacts: dict[str, dict[str, Any]] | None = None,
    minimum_case_count: int = 1,
    schema_valid_rate_threshold: float = 0.0,
    required_badcase_severities: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize whether an eval run is eligible for candidate promotion.

    This is advisory metadata for release review. It does not switch production
    FinalDecision input and does not write to the production journal.
    """

    failed_scores = [score for score in scores if not score.passed]
    case_ids = {score.case_id for score in scores}
    case_ids.update(replay_outputs.keys())
    observed_case_count = len(case_ids)
    minimum_coverage_reasons: list[str] = []
    schema_valid_rate_reasons: list[str] = []
    badcase_severity_coverage_reasons: list[str] = []
    eval_score_reasons: list[str] = []
    critical_rule_reasons: list[str] = []
    manual_execution_reasons: list[str] = []
    side_effect_reasons: list[str] = []
    side_effect_proof_reasons: list[str] = []
    candidate_business_reasons: list[str] = []
    candidate_replay_reasons: list[str] = []
    worker_coverage_reasons: list[str] = []
    complete_replay_reasons: list[str] = []
    switch_readiness_reasons: list[str] = []

    blocking_reasons: list[str] = []
    clean_minimum_case_count = max(1, int(minimum_case_count))
    if observed_case_count < clean_minimum_case_count:
        minimum_coverage_reasons.append("minimum_eval_coverage_not_met")
        blocking_reasons.append("minimum_eval_coverage_not_met")
    schema_score_count = sum(1 for score in scores if _is_schema_score(score))
    schema_score_passed = sum(1 for score in scores if _is_schema_score(score) and score.passed)
    schema_valid_rate = (
        float(schema_score_passed / schema_score_count) if schema_score_count else 1.0
    )
    clean_schema_threshold = max(0.0, min(float(schema_valid_rate_threshold), 1.0))
    if schema_valid_rate < clean_schema_threshold:
        schema_valid_rate_reasons.append("schema_valid_rate_below_threshold")
        blocking_reasons.append("schema_valid_rate_below_threshold")
    badcase_severity_coverage = _badcase_severity_coverage(
        cases=cases or [],
        required_badcase_severities=required_badcase_severities or [],
    )
    if badcase_severity_coverage["missing_severities"]:
        badcase_severity_coverage_reasons.append("badcase_severity_coverage_not_met")
        blocking_reasons.append("badcase_severity_coverage_not_met")
    if failed_scores:
        eval_score_reasons.append("eval_scores_failed")
        blocking_reasons.extend(eval_score_reasons)
    for score in failed_scores:
        if score.judge_name == "rule.manual_only":
            manual_execution_reasons.append("manual_execution_required_failed")
            blocking_reasons.append("manual_execution_required_failed")
        if score.judge_name == "eval.side_effect_guard":
            side_effect_reasons.append("eval_side_effect_guard_failed")
        category = str(score.failure_category or "")
        is_critical_rule_detail = score.severity == "critical" and score.judge_name.startswith("rule.")
        if category and category != "none" and not is_critical_rule_detail:
            blocking_reasons.append(category)
            if category in {"candidate_gate_failed", "plan_semantic_candidate_failed"}:
                candidate_business_reasons.append(category)
            if score.judge_name == "eval.side_effect_guard":
                side_effect_reasons.append(category)
        if score.judge_name == "rule.manual_only" and category and category != "none":
            blocking_reasons.append(category)
            manual_execution_reasons.append(category)

    if any(score.severity == "critical" and score.judge_name.startswith("rule.") for score in failed_scores):
        critical_rule_reasons.append("critical_rule_failed")
        blocking_reasons.append("critical_rule_failed")
    for score in failed_scores:
        category = str(score.failure_category or "")
        if (
            category
            and category != "none"
            and score.severity == "critical"
            and score.judge_name.startswith("rule.")
            and score.judge_name != "rule.manual_only"
        ):
            blocking_reasons.append(category)
            critical_rule_reasons.append(category)

    candidate_available = 0
    candidate_missing = 0
    worker_counts: list[int] = []
    worker_manifest_missing_fields: list[dict[str, Any]] = []
    worker_manifest_consistency_violations: list[dict[str, Any]] = []
    context_artifact_consistency_violations: list[dict[str, Any]] = []
    artifact_snapshot_consistency_violations: list[dict[str, Any]] = []
    counter_conflict_coverage_violations: list[dict[str, Any]] = []
    complete_replay_missing_refs: list[dict[str, Any]] = []
    span_tree_incomplete_cases: list[dict[str, Any]] = []
    worker_hard_blocks: list[dict[str, Any]] = []
    blocked_action_cases: list[dict[str, Any]] = []
    incomplete_block_evidence_cases: list[str] = []
    execution_fact_source_violations: list[dict[str, Any]] = []
    switch_ready_values: list[bool] = []
    for case_id, output in replay_outputs.items():
        replay_readback_violation = _candidate_replay_readback_violation(output)
        if replay_readback_violation:
            candidate_missing += 1
            candidate_replay_reasons.append(replay_readback_violation)
            blocking_reasons.append(replay_readback_violation)
            continue
        candidate_replay = output.output_payload.get("candidate_replay")
        if not isinstance(candidate_replay, dict) or candidate_replay.get("status") != "available":
            candidate_missing += 1
            continue
        candidate_available += 1
        worker_count = candidate_replay.get("worker_artifact_count")
        if isinstance(worker_count, int):
            worker_counts.append(worker_count)
        if candidate_replay.get("worker_manifest_complete") is False:
            worker_coverage_reasons.append("worker_manifest_incomplete")
            for item in candidate_replay.get("worker_manifest_missing_fields") or []:
                if not isinstance(item, dict):
                    continue
                worker_manifest_missing_fields.append(
                    {
                        "case_id": case_id,
                        "task_id": item.get("task_id"),
                        "agent_name": item.get("agent_name"),
                        "missing_fields": list(item.get("missing_fields") or []),
                    }
                )
        consistency = candidate_replay.get("worker_manifest_consistency")
        if not isinstance(consistency, dict):
            worker_coverage_reasons.append("worker_manifest_consistency_missing")
            blocking_reasons.append("worker_manifest_consistency_missing")
        elif consistency.get("passed") is False:
            worker_coverage_reasons.append("worker_manifest_consistency_failed")
            blocking_reasons.append("worker_manifest_consistency_failed")
            for violation in consistency.get("violations") or []:
                if not isinstance(violation, dict):
                    continue
                worker_manifest_consistency_violations.append(_safe_violation(case_id, violation))
        context_consistency = candidate_replay.get("context_artifact_consistency")
        if not isinstance(context_consistency, dict):
            worker_coverage_reasons.append("context_artifact_consistency_missing")
            blocking_reasons.append("context_artifact_consistency_missing")
        elif context_consistency.get("passed") is False:
            worker_coverage_reasons.append("context_artifact_consistency_failed")
            blocking_reasons.append("context_artifact_consistency_failed")
            for violation in context_consistency.get("violations") or []:
                if not isinstance(violation, dict):
                    continue
                context_artifact_consistency_violations.append(_safe_violation(case_id, violation))
        artifact_snapshot_consistency = candidate_replay.get("artifact_snapshot_consistency")
        if not isinstance(artifact_snapshot_consistency, dict) or artifact_snapshot_consistency.get("passed") is not True:
            worker_coverage_reasons.append("artifact_snapshot_readback_failed")
            blocking_reasons.append("artifact_snapshot_readback_failed")
            violations = (
                artifact_snapshot_consistency.get("violations")
                if isinstance(artifact_snapshot_consistency, dict)
                else None
            )
            if not violations:
                artifact_snapshot_consistency_violations.append(
                    {
                        "case_id": case_id,
                        "rule_id": "candidate_artifact_snapshot_consistency_missing",
                    }
                )
            for violation in violations or []:
                if not isinstance(violation, dict):
                    continue
                artifact_snapshot_consistency_violations.append(_safe_violation(case_id, violation))
        counter_conflict_coverage = candidate_replay.get("counter_conflict_coverage")
        if not isinstance(counter_conflict_coverage, dict):
            worker_coverage_reasons.append("counter_conflict_coverage_missing")
            blocking_reasons.append("counter_conflict_coverage_missing")
        elif counter_conflict_coverage.get("passed") is False:
            worker_coverage_reasons.append("counter_conflict_coverage_failed")
            blocking_reasons.append("counter_conflict_coverage_failed")
            for violation in counter_conflict_coverage.get("violations") or []:
                if not isinstance(violation, dict):
                    continue
                counter_conflict_coverage_violations.append(_safe_violation(case_id, violation))
        complete_replay_ref_map = (
            candidate_replay.get("complete_replay_refs")
            if isinstance(candidate_replay.get("complete_replay_refs"), dict)
            else {}
        )
        missing_complete_refs = [
            str(item)
            for item in candidate_replay.get("complete_replay_missing_refs") or []
            if str(item) in COMPLETE_REPLAY_REF_NAMES
        ]
        for ref_name, coverage_key in sorted(COMPLETE_REPLAY_REF_KEYS.items()):
            if complete_replay_ref_map.get(coverage_key) is not True and ref_name not in missing_complete_refs:
                missing_complete_refs.append(ref_name)
        if missing_complete_refs:
            complete_replay_reasons.append("complete_replay_input_incomplete")
            blocking_reasons.append("complete_replay_input_incomplete")
            complete_replay_missing_refs.append(
                {
                    "case_id": case_id,
                    "missing_refs": missing_complete_refs,
                }
            )
        if candidate_replay.get("span_tree_parent_complete") is not True or _safe_int(
            candidate_replay.get("span_tree_missing_parent_count")
        ) > 0:
            complete_replay_reasons.append("span_tree_parent_incomplete")
            blocking_reasons.append("span_tree_parent_incomplete")
            span_tree_incomplete_cases.append(
                {
                    "case_id": case_id,
                    "missing_parent_count": _safe_int(candidate_replay.get("span_tree_missing_parent_count")),
                }
            )
        for hard_block in candidate_replay.get("worker_hard_blocks") or []:
            if not isinstance(hard_block, dict):
                continue
            worker_hard_blocks.append(_safe_worker_hard_block(case_id, hard_block))
        switch_ready_values.append(candidate_replay.get("switch_ready") is True)
        for reason in candidate_replay.get("blocking_reasons") or []:
            reason_text = str(reason)
            if reason_text and reason_text not in blocking_reasons:
                blocking_reasons.append(reason_text)
            if reason_text in {"candidate_gate_failed", "plan_semantic_candidate_failed"}:
                candidate_business_reasons.append(reason_text)
            if reason_text == "candidate_gate_failed":
                blocked_actions = [str(item) for item in candidate_replay.get("blocked_actions") or []]
                missing_facts = [str(item) for item in candidate_replay.get("missing_facts") or []]
                if blocked_actions:
                    blocked_action_cases.append(
                        {
                            "case_id": case_id,
                            "blocked_actions": blocked_actions,
                            "missing_facts": missing_facts,
                        }
                    )
                if not blocked_actions and not missing_facts:
                    candidate_business_reasons.append("candidate_block_evidence_incomplete")
                    blocking_reasons.append("candidate_block_evidence_incomplete")
                    incomplete_block_evidence_cases.append(case_id)
        for violation in candidate_replay.get("execution_fact_source_violations") or []:
            if not isinstance(violation, dict):
                continue
            execution_fact_source_violations.append(
                {
                    "case_id": case_id,
                    "evidence_id": violation.get("evidence_id"),
                    "data_type": violation.get("data_type"),
                    "source_type": violation.get("source_type"),
                }
            )

    if candidate_missing and candidate_available:
        candidate_replay_reasons.append("candidate_replay_missing")
        blocking_reasons.append("candidate_replay_missing")
    if candidate_available and (not switch_ready_values or not all(switch_ready_values)):
        switch_readiness_reasons.append("final_switch_readiness_not_ready")
        blocking_reasons.append("final_switch_readiness_not_ready")

    worker_count_min = min(worker_counts) if worker_counts else 0
    if candidate_available and worker_count_min < REQUIRED_WORKER_ARTIFACT_COUNT:
        worker_coverage_reasons.append("worker_artifact_coverage_incomplete")
        blocking_reasons.append("worker_artifact_coverage_incomplete")
    if worker_manifest_missing_fields:
        blocking_reasons.append("worker_manifest_incomplete")
    execution_fact_source_reasons: list[str] = []
    if execution_fact_source_violations:
        execution_fact_source_reasons.append("execution_fact_source_violation")
        blocking_reasons.append("execution_fact_source_violation")

    blocking_reasons = _dedupe(blocking_reasons)
    worker_artifact_coverage = {
        **_gate_result(worker_coverage_reasons),
        "required_min": REQUIRED_WORKER_ARTIFACT_COUNT,
        "observed_min": worker_count_min,
        "manifest_missing_fields": worker_manifest_missing_fields,
        "manifest_consistency_violations": worker_manifest_consistency_violations,
        "context_artifact_consistency_violations": context_artifact_consistency_violations,
    }
    if artifact_snapshot_consistency_violations:
        worker_artifact_coverage[
            "artifact_snapshot_consistency_violations"
        ] = artifact_snapshot_consistency_violations
    counter_conflict_coverage_reasons = []
    if counter_conflict_coverage_violations:
        counter_conflict_coverage_reasons.append("counter_conflict_coverage_failed")
    worker_hard_block_reasons = []
    if worker_hard_blocks:
        worker_hard_block_reasons.append("worker_hard_block")
        blocking_reasons.append("worker_hard_block")
        blocking_reasons = _dedupe(blocking_reasons)
    current_candidate_inputs = _current_candidate_inputs(replay_outputs)
    side_effect_proof_artifact = (promotion_artifacts or {}).get("no_production_side_effect_proof")
    side_effect_proof_ref = None
    if eval_run_id is not None:
        side_effect_proof_valid, side_effect_proof_reasons = validate_no_production_side_effect_proof(
            side_effect_proof_artifact,
            eval_run_id=eval_run_id,
        )
        if side_effect_proof_valid and isinstance(side_effect_proof_artifact, dict):
            side_effect_proof_ref = side_effect_proof_artifact.get("artifact_ref")
        if side_effect_proof_reasons:
            blocking_reasons.extend(side_effect_proof_reasons)
            blocking_reasons = _dedupe(blocking_reasons)
    hard_gate_results = {
        "minimum_eval_coverage": {
            **_gate_result(minimum_coverage_reasons),
            "required_min": clean_minimum_case_count,
            "observed": observed_case_count,
        },
        "schema_valid_rate": {
            **_gate_result(schema_valid_rate_reasons),
            "required_min": clean_schema_threshold,
            "observed_rate": round(schema_valid_rate, 6),
            "observed_count": schema_score_count,
            "passed_count": schema_score_passed,
        },
        "badcase_severity_coverage": {
            **_gate_result(badcase_severity_coverage_reasons),
            **badcase_severity_coverage,
        },
        "eval_scores": _gate_result(eval_score_reasons),
        "critical_rule_failures": _gate_result(critical_rule_reasons),
        "manual_execution_required": _gate_result(manual_execution_reasons),
        "eval_side_effect_guard": _gate_result(side_effect_reasons),
        "no_production_side_effect_proof": {
            **_gate_result(side_effect_proof_reasons),
            "artifact_ref": side_effect_proof_ref,
        },
        "candidate_business_gates": {
            **_gate_result(candidate_business_reasons),
            "blocked_action_cases": blocked_action_cases,
            "incomplete_block_evidence_cases": incomplete_block_evidence_cases,
        },
        "execution_fact_sources": {
            **_gate_result(execution_fact_source_reasons),
            "violations": execution_fact_source_violations,
        },
        "candidate_replay": _gate_result(candidate_replay_reasons),
        "worker_artifact_coverage": worker_artifact_coverage,
        "complete_replay_input": {
            **_gate_result(complete_replay_reasons),
            "missing_refs": complete_replay_missing_refs,
            "span_tree_incomplete_cases": span_tree_incomplete_cases,
        },
        "worker_hard_blocks": {
            **_gate_result(worker_hard_block_reasons),
            "worker_hard_blocks": worker_hard_blocks,
        },
        "counter_conflict_coverage": {
            **_gate_result(counter_conflict_coverage_reasons),
            "violations": counter_conflict_coverage_violations,
        },
        "final_switch_readiness": _gate_result(switch_readiness_reasons),
    }
    ready = not blocking_reasons

    return {
        "schema_version": 1,
        "ready": ready,
        "hard_gates_passed": ready,
        "promotion_approved": False,
        "decision_effect": "none",
        "blocking_reasons": blocking_reasons,
        "candidate_replay_available": candidate_available,
        "candidate_replay_missing": candidate_missing,
        "worker_artifact_count_min": worker_count_min,
        "hard_gate_results": hard_gate_results,
        "promotion_review": promotion_review(
            ready=ready,
            eval_run_id=eval_run_id,
            promotion_artifacts=promotion_artifacts or {},
            current_candidate_inputs=current_candidate_inputs,
        ),
    }


def _candidate_replay_readback_violation(output: EvalReplayOutput) -> str | None:
    if output.status != "completed":
        return "candidate_replay_output_not_completed"
    metadata = output.metadata if isinstance(output.metadata, dict) else {}
    if (
        output.mode != "candidate_decision"
        or metadata.get("source") != "eval.candidate_decision_replay"
        or metadata.get("decision_effect") != "none"
    ):
        return "candidate_replay_readback_not_verified"
    if _candidate_replay_has_decision_effect_violation(output.output_payload):
        return "candidate_replay_decision_effect_violation"
    return None


def _candidate_replay_has_decision_effect_violation(output_payload: dict[str, Any]) -> bool:
    candidate_replay = output_payload.get("candidate_replay")
    if _has_side_effect_intent(candidate_replay):
        return True

    candidate_decision = output_payload.get("candidate_decision")
    if _has_side_effect_intent(candidate_decision):
        return True

    shadow_final = output_payload.get("decision_input_shadow_final")
    if _has_side_effect_intent(shadow_final):
        return True

    candidate_final_comparison = output_payload.get("candidate_final_legacy_comparison")
    if _has_side_effect_intent(candidate_final_comparison):
        return True

    candidate_final_decision = output_payload.get("candidate_final_decision")
    if _has_side_effect_intent(candidate_final_decision):
        return True

    return False


def _has_side_effect_intent(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if "decision_effect" in value and value.get("decision_effect") != "none":
        return True
    return any(
        value.get(flag) is True
        for flag in ("production_final_input", "notification_input", "live_order_input")
    )


def _safe_worker_hard_block(case_id: str, hard_block: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "contribution_id": hard_block.get("contribution_id"),
        "agent_name": hard_block.get("agent_name"),
        "reasons": [str(reason) for reason in hard_block.get("reasons") or []],
    }


def _current_candidate_inputs(replay_outputs: dict[str, EvalReplayOutput]) -> set[tuple[str, str]]:
    current: set[tuple[str, str]] = set()
    for output in replay_outputs.values():
        candidate_replay = output.output_payload.get("candidate_replay")
        if not isinstance(candidate_replay, dict) or candidate_replay.get("status") != "available":
            continue
        input_ref = candidate_replay.get("decision_input_ref")
        input_hash = candidate_replay.get("decision_input_hash")
        if isinstance(input_ref, str) and input_ref.strip() and isinstance(input_hash, str) and input_hash.strip():
            current.add((str(input_ref), str(input_hash)))
    return current


def _safe_violation(case_id: str, violation: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "rule_id",
        "task_id",
        "agent_name",
        "expected",
        "observed",
        "missing_fields",
        "artifact_type",
        "failure_policy_applied",
        "counter_thesis_count",
        "conflict_count",
    }
    safe = {"case_id": case_id}
    for key in allowed_keys:
        if key in violation:
            safe[key] = violation.get(key)
    return safe


def _badcase_severity_coverage(
    *,
    cases: list[Any],
    required_badcase_severities: list[str],
) -> dict[str, Any]:
    required = _dedupe([str(severity) for severity in required_badcase_severities])
    observed_counts = {severity: 0 for severity in required}
    for case in cases:
        severity = _case_severity(case)
        if severity in observed_counts:
            observed_counts[severity] += 1
    missing = [severity for severity in required if observed_counts.get(severity, 0) == 0]
    return {
        "required_severities": required,
        "observed_counts": observed_counts,
        "missing_severities": missing,
    }


def _case_severity(case: Any) -> str:
    if isinstance(case, dict):
        return str(case.get("severity") or "")
    return str(getattr(case, "severity", "") or "")


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _gate_result(blocking_reasons: list[str]) -> dict[str, Any]:
    return {"passed": not blocking_reasons, "blocking_reasons": _dedupe(blocking_reasons)}


def _is_schema_score(score: EvalScore) -> bool:
    return score.judge_name in {"rule.action_enum"} or str(score.failure_category or "").startswith("schema_")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
