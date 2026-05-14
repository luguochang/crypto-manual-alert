from __future__ import annotations

import json
from typing import Any

from crypto_manual_alert.artifacts.contributions import tool_call_artifact_ref_fields
from crypto_manual_alert.storage.agent_audit_projection import (
    project_conflict_edges,
    project_evidence_sources,
    project_input_lineage,
    project_release_eval_gate,
    project_root_cause_graph,
    project_source_freshness,
    project_strongest_counter_thesis_ref,
    project_tool_calls,
)


SENSITIVE_PAYLOAD_KEYS = {
    "raw_decision",
    "frozen_input",
    "frozen_input_hash",
    "snapshot",
    "evidence_snapshot",
    "plan",
}
QUERY_AUDIT_NOTE_MODE = "audit_note"


def build_agent_audit_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the API/UI-safe agent audit projection from a stored plan payload.

    The stored payload can contain full prompt/frozen-input material for replay.
    This projection is intentionally ref/hash oriented and should remain safe to
    return from the run detail API.
    """

    shadow = _mapping(payload.get("shadow_swarm_audit"))
    controlled_shadow = _mapping(payload.get("controlled_shadow"))
    pre_final_input = _mapping(payload.get("pre_final_decision_input"))
    decision_input_candidate = _mapping(payload.get("decision_input_candidate"))
    if not shadow and not pre_final_input and not decision_input_candidate:
        return {"available": False, "reason": "agent_audit_payload_missing"}
    worker_results = shadow.get("worker_results")
    lead_synthesis = _mapping(shadow.get("lead_synthesis"))
    tool_calls = project_tool_calls(worker_results)
    evidence_sources = project_evidence_sources(payload.get("evidence_packets"))
    candidate_final_comparison = _candidate_final_comparison(payload)

    return _drop_none(
        {
            "available": True,
            "schema_version": 1,
            "mode": controlled_shadow.get("mode") or shadow.get("mode") or "shadow",
            "decision_effect": "audit_only_input_production_blocking_gate",
            "query_semantics": _query_semantics_view(_mapping(payload.get("run_context"))),
            "symbol_consistency": _symbol_consistency_view(payload),
            "controlled_shadow": _controlled_shadow_view(controlled_shadow),
            "lead_plan": _lead_plan_view(_mapping(shadow.get("lead_plan"))),
            "workers": _worker_views(worker_results),
            "lead_synthesis": _lead_synthesis_view(lead_synthesis),
            "harness_validation": _first_mapping(
                shadow.get("harness_validation"), payload.get("harness_validation")
            ),
            "facts_gate": _facts_gate_view(_mapping(payload.get("facts_gate"))),
            "evidence_packets": _evidence_packet_summary(payload.get("evidence_packets")),
            "tool_calls": tool_calls,
            "evidence_sources": evidence_sources,
            "source_freshness": project_source_freshness(
                evidence_sources,
                facts_gate=_mapping(payload.get("facts_gate")),
                tool_calls=tool_calls,
            ),
            "root_cause_graph": project_root_cause_graph(worker_results),
            "conflict_edges": project_conflict_edges(lead_synthesis, worker_results),
            "strongest_counter_thesis_ref": project_strongest_counter_thesis_ref(lead_synthesis),
            "decision_input": _decision_input_view(pre_final_input),
            "decision_input_candidate": _decision_input_view(decision_input_candidate),
            "candidate_final_comparison": candidate_final_comparison,
            "input_lineage": project_input_lineage(
                payload=payload,
                decision_input=pre_final_input,
                candidate_final_comparison=candidate_final_comparison,
            ),
            "release_eval_gate": project_release_eval_gate(payload),
            "gates": _gate_views(payload),
            "final_input_selection": _public_mapping(
                payload.get("final_input_selection"),
                [
                    "mode",
                    "decision_effect",
                    "source_ref",
                    "readiness_ready",
                    "fallback_from_mode",
                    "fallback_reason",
                    "fallback_blocking_reasons",
                ],
            ),
            "legacy_prompt_lifecycle": _public_mapping(
                payload.get("legacy_prompt_lifecycle"),
                [
                    "status",
                    "selected_as_final_input",
                    "allowed_uses",
                    "replacement_target",
                    "fallback_reason",
                    "fallback_blocking_reasons",
                ],
            ),
            "replay_refs": _replay_refs(payload.get("replayable_input_candidate")),
            "runtime_flow": _runtime_flow(payload),
            "source_payload_keys": _public_payload_keys(payload),
        }
    )


def _lead_plan_view(lead_plan: dict[str, Any]) -> dict[str, Any]:
    if not lead_plan:
        return {}
    tasks = []
    for item in _list(lead_plan.get("tasks")):
        task = _mapping(item)
        tasks.append(
            _drop_none(
                {
                    "task_id": task.get("task_id"),
                    "agent_name": task.get("agent_name"),
                    "role": task.get("role"),
                    "required": task.get("required"),
                    "timeout_seconds": task.get("timeout_seconds"),
                    "requested_tools": _string_list(task.get("requested_tools")),
                    "input_ref": task.get("input_ref"),
                    "trace_ref": task.get("trace_ref"),
                    "failure_policy": task.get("failure_policy"),
                }
            )
        )
    return _drop_none(
        {
            "plan_id": lead_plan.get("plan_id"),
            "mode": lead_plan.get("mode"),
            "decision_effect": lead_plan.get("decision_effect"),
            "resource_limits": _mapping(lead_plan.get("resource_limits")),
            "tasks": tasks,
        }
    )


def _query_semantics_view(run_context: dict[str, Any]) -> dict[str, Any]:
    semantics = _mapping(run_context.get("query_semantics"))
    if not semantics:
        return {}
    return _drop_none(
        {
            "mode": semantics.get("mode") or QUERY_AUDIT_NOTE_MODE,
            "query_text": run_context.get("query_text"),
            "drives_lead_plan": semantics.get("drives_lead_plan"),
            "drives_worker_selection": semantics.get("drives_worker_selection"),
            "drives_tool_budget": semantics.get("drives_tool_budget"),
            "drives_facts_requirement": semantics.get("drives_facts_requirement"),
            "drives_final_input": semantics.get("drives_final_input"),
            "explanation": semantics.get("explanation"),
        }
    )


def _symbol_consistency_view(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = _mapping(payload.get("symbol_consistency"))
    if explicit:
        return _drop_none(
            {
                "request_symbol": explicit.get("request_symbol"),
                "snapshot_symbol": explicit.get("snapshot_symbol"),
                "plan_instrument": explicit.get("plan_instrument"),
                "consistent": explicit.get("consistent"),
            }
        )
    request_symbol = _mapping(payload.get("run_context")).get("symbol")
    snapshot_symbol = _mapping(payload.get("snapshot")).get("symbol")
    plan_instrument = _mapping(payload.get("parsed_plan") or payload.get("plan")).get("instrument")
    values = [str(value) for value in (request_symbol, snapshot_symbol, plan_instrument) if value]
    if not values:
        return {}
    return _drop_none(
        {
            "request_symbol": request_symbol,
            "snapshot_symbol": snapshot_symbol,
            "plan_instrument": plan_instrument,
            "consistent": len(set(values)) <= 1,
        }
    )


def _controlled_shadow_view(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return _drop_none(
        {
            "mode": payload.get("mode"),
            "status": payload.get("status"),
            "audit_only": payload.get("audit_only"),
            "production_candidate": payload.get("production_candidate"),
            "blocked": payload.get("blocked"),
            "production_final_input": payload.get("production_final_input"),
            "notification_input": payload.get("notification_input"),
            "reason": payload.get("reason"),
        }
    )


def _worker_views(worker_results: Any) -> list[dict[str, Any]]:
    workers: list[dict[str, Any]] = []
    for item in _list(worker_results):
        result = _mapping(item)
        contribution = _mapping(result.get("contribution"))
        constraints = _mapping(contribution.get("constraints"))
        agent_result = _mapping(result.get("agent_run_result"))
        tool_call_artifact_refs = tool_call_artifact_ref_fields(contribution)
        workers.append(
            _drop_none(
                {
                    "agent_name": result.get("agent_name") or contribution.get("agent_name"),
                    "task_id": result.get("task_id") or contribution.get("task_id"),
                    "status": result.get("status") or contribution.get("status"),
                    "required": result.get("required") if "required" in result else contribution.get("required"),
                    "trace_ref": result.get("trace_ref") or contribution.get("trace_ref"),
                    "input_ref": contribution.get("input_ref") or agent_result.get("contribution_ref"),
                    "output_hash": contribution.get("output_hash") or agent_result.get("output_hash"),
                    "failure_policy_applied": result.get("failure_policy_applied")
                    or contribution.get("failure_policy_applied"),
                    "summary": contribution.get("summary"),
                    "claim_count": len(_list(contribution.get("claims"))),
                    "conflict_count": len(_list(contribution.get("conflicts"))),
                    "conflicts": _string_list(contribution.get("conflicts"), max_items=12),
                    "missing_facts": _string_list(contribution.get("missing_facts"), max_items=16),
                    "evidence_ids": _string_list(contribution.get("evidence_ids"), max_items=16),
                    "confidence_cap": contribution.get("confidence_cap", constraints.get("confidence_cap")),
                    "confidence_cap_reasons": _string_list(
                        contribution.get("confidence_cap_reasons", constraints.get("confidence_cap_reasons")),
                        max_items=12,
                    ),
                    "hard_block": bool(contribution.get("hard_block", constraints.get("hard_block", False))),
                    "hard_block_reasons": _string_list(
                        contribution.get("hard_block_reasons", constraints.get("hard_block_reasons")),
                        max_items=12,
                    ),
                    "blocked_actions": _string_list(
                        contribution.get("blocked_actions", constraints.get("blocked_actions")),
                        max_items=12,
                    ),
                    "blocked_action_classes": _string_list(
                        contribution.get("blocked_action_classes", constraints.get("blocked_action_classes")),
                        max_items=12,
                    ),
                    "allowed_action_class_reduction": constraints.get("allowed_action_class_reduction")
                    or contribution.get("allowed_action_class_reduction"),
                    "manual_review_reminders": _string_list(
                        contribution.get("manual_review_reminders", constraints.get("manual_review_reminders")),
                        max_items=12,
                    ),
                    "required_confirmations": _string_list(
                        contribution.get("required_confirmations", constraints.get("required_confirmations")),
                        max_items=12,
                    ),
                    "requested_tools": _string_list(constraints.get("requested_tools"), max_items=12),
                    "tool_call_artifact_count": len(tool_call_artifact_refs),
                    "tool_call_artifact_refs": tool_call_artifact_refs,
                }
            )
        )
    return workers


def _lead_synthesis_view(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return _drop_none(
        {
            "included_contribution_ids": _string_list(payload.get("included_contribution_ids"), max_items=20),
            "dropped_contributions": _list(payload.get("dropped_contributions"))[:20],
            "supporting_thesis": _string_list(payload.get("supporting_thesis"), max_items=8),
            "counter_thesis": _string_list(payload.get("counter_thesis"), max_items=8),
            "conflicts": _string_list(payload.get("conflicts"), max_items=20),
            "conflict_refs": _list(payload.get("conflict_refs"))[:20],
            "missing_facts": _string_list(payload.get("missing_facts"), max_items=20),
            "confidence_cap": payload.get("confidence_cap"),
            "confidence_cap_reasons": _string_list(payload.get("confidence_cap_reasons"), max_items=20),
        }
    )


def _facts_gate_view(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return _drop_none(
        {
            "passed": payload.get("passed"),
            "severity": payload.get("severity"),
            "reasons": _string_list(payload.get("reasons"), max_items=20),
            "missing_execution_facts": _string_list(payload.get("missing_execution_facts"), max_items=20),
            "missing_auxiliary_facts": _string_list(payload.get("missing_auxiliary_facts"), max_items=20),
            "missing_event_facts": _string_list(payload.get("missing_event_facts"), max_items=20),
            "missing_macro_facts": _string_list(payload.get("missing_macro_facts"), max_items=20),
            "blocked_action_classes": _string_list(payload.get("blocked_action_classes"), max_items=12),
            "confidence_cap": payload.get("confidence_cap"),
            "confidence_cap_reasons": _string_list(payload.get("confidence_cap_reasons"), max_items=20),
        }
    )


def _evidence_packet_summary(value: Any) -> dict[str, Any]:
    packets = _list(value)
    ids = []
    source_types = []
    freshness = []
    for item in packets:
        packet = _mapping(item)
        if packet.get("evidence_id") is not None:
            ids.append(str(packet.get("evidence_id")))
        elif packet.get("id") is not None:
            ids.append(str(packet.get("id")))
        if packet.get("source_type") is not None:
            source_types.append(str(packet.get("source_type")))
        if packet.get("freshness_status") is not None:
            freshness.append(str(packet.get("freshness_status")))
    return {
        "count": len(packets),
        "ids": ids[:20],
        "source_types": sorted(set(source_types))[:20],
        "freshness_statuses": sorted(set(freshness))[:20],
    }


def _decision_input_view(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return _drop_none(
        {
            "mode": payload.get("mode"),
            "schema_version": payload.get("schema_version"),
            "decision_effect": payload.get("decision_effect"),
            "execution_mode": payload.get("execution_mode"),
            "symbol": payload.get("symbol"),
            "trace_id": payload.get("trace_id"),
            "input_ref": payload.get("input_ref"),
            "input_hash": payload.get("input_hash"),
            "validation": _mapping(payload.get("validation")),
            "missing_facts": _string_list(payload.get("missing_facts"), max_items=30),
            "conflicts": _string_list(payload.get("conflicts"), max_items=30),
            "effective_allowed_actions": _string_list(payload.get("effective_allowed_actions"), max_items=20),
            "blocked_actions": _string_list(payload.get("blocked_actions"), max_items=20),
            "confidence_policy": _mapping(payload.get("confidence_policy")),
            "contribution_refs": _list(payload.get("contribution_refs"))[:20],
            "evidence_refs": _string_list(payload.get("evidence_refs"), max_items=20),
        }
    )


def _gate_views(payload: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "gate_candidate": _mapping(payload.get("gate_candidate")),
            "plan_semantic_candidate": _mapping(payload.get("plan_semantic_candidate")),
            "final_decision_switch_readiness": _mapping(payload.get("final_decision_switch_readiness")),
            "production_control_gate": _mapping(payload.get("production_control_gate")),
        }
    )


def _candidate_final_comparison(payload: dict[str, Any]) -> dict[str, Any]:
    sidecar = _mapping(payload.get("candidate_final_decision"))
    if not sidecar:
        return {}
    legacy_plan = _mapping(payload.get("parsed_plan") or payload.get("plan"))
    legacy_probability = _number_or_none(legacy_plan.get("probability"))
    candidate_plan = _json_mapping(sidecar.get("raw_candidate_decision"))
    candidate_probability = _number_or_none(candidate_plan.get("probability"))
    candidate_error = sidecar.get("error") if isinstance(sidecar.get("error"), dict) else None
    production_final_input = sidecar.get("production_final_input") is True
    decision_effect = sidecar.get("decision_effect")
    candidate_payload = {
        "input_ref": sidecar.get("input_ref"),
        "input_hash": sidecar.get("input_hash"),
        "action": candidate_plan.get("main_action") or candidate_plan.get("action"),
        "probability": candidate_probability,
        "allowed": bool(sidecar.get("input_gate_passed") is True and candidate_error is None),
        "error": candidate_error,
    }
    candidate_diagnosis = _candidate_diagnosis(sidecar.get("diagnosis"))
    if candidate_diagnosis:
        candidate_payload["diagnosis"] = candidate_diagnosis
    return _drop_none(
        {
            "status": "audit_only" if decision_effect == "none" and not production_final_input else "invalid",
            "decision_effect": decision_effect,
            "production_final_input": production_final_input,
            "legacy": _drop_none(
                {
                    "action": legacy_plan.get("main_action"),
                    "probability": legacy_probability,
                    "allowed": _mapping(payload.get("verdict")).get("allowed"),
                }
            ),
            "candidate": candidate_payload,
            "diff": _candidate_diff(
                legacy_action=legacy_plan.get("main_action"),
                candidate_action=candidate_plan.get("main_action") or candidate_plan.get("action"),
                legacy_probability=legacy_probability,
                candidate_probability=candidate_probability,
            ),
            "production_control_gate": _production_control_gate_summary(payload.get("production_control_gate")),
            "final_input_selection": _public_mapping(
                payload.get("final_input_selection"),
                ["mode", "decision_effect", "source_ref"],
            ),
        }
    )


def _production_control_gate_summary(value: Any) -> dict[str, Any]:
    gate = _mapping(value)
    if not gate:
        return {}
    return _drop_none(
        {
            "allowed": gate.get("allowed"),
            "reasons": _string_list(gate.get("reasons"), max_items=12),
            "blocking_rule_ids": [
                str(item.get("rule_id"))
                for item in _list(gate.get("rule_hits"))
                if isinstance(item, dict) and item.get("blocking") is True and item.get("rule_id")
            ][:12],
        }
    )


def _candidate_diff(
    *,
    legacy_action: Any,
    candidate_action: Any,
    legacy_probability: float | None,
    candidate_probability: float | None,
) -> dict[str, Any]:
    diff: dict[str, Any] = {"action_changed": legacy_action != candidate_action}
    if legacy_probability is not None and candidate_probability is not None:
        diff["probability_delta"] = round(candidate_probability - legacy_probability, 10)
    return diff


def _candidate_diagnosis(value: Any) -> dict[str, Any]:
    diagnosis = _mapping(value)
    if not diagnosis:
        return {}
    return _drop_empty(
        {
            "summary": diagnosis.get("summary"),
            "blocking_reasons": _string_list(diagnosis.get("blocking_reasons"), max_items=12),
        }
    )


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _replay_refs(value: Any) -> dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    refs = {
        key: ref_value
        for key, ref_value in _mapping(payload.get("artifact_refs")).items()
        if "frozen_input" not in key and "raw" not in key
    }
    return _drop_none(
        {
            "input_ref": payload.get("input_ref"),
            "input_hash": payload.get("input_hash"),
            "artifact_refs": refs,
            "has_lead_synthesis_artifact": payload.get("has_lead_synthesis_artifact"),
            "has_production_control_gate": payload.get("has_production_control_gate"),
        }
    )


def _runtime_flow(payload: dict[str, Any]) -> list[dict[str, Any]]:
    span_tree_refs = _span_tree_refs(payload)
    span_refs = _list(span_tree_refs.get("span_refs"))
    if span_refs:
        span_tree_ref = span_tree_refs.get("span_tree_ref")
        flow: list[dict[str, Any]] = []
        for span in span_refs[:80]:
            item = _mapping(span)
            name = str(item.get("span_name") or item.get("span_type") or "unknown")
            owner = str(item.get("span_type") or name)
            flow_item = {
                "name": name,
                "owner": owner,
                "effect": "runtime span executed",
                "status": item.get("status"),
                "duration_ms": item.get("duration_ms"),
                "span_id": item.get("span_id"),
                "parent_span_id": item.get("parent_span_id"),
                "source": "span_tree_refs",
                "span_tree_ref": span_tree_ref,
            }
            for key in ("span_input_hash", "span_output_hash"):
                if item.get(key):
                    flow_item[key] = item.get(key)
            for key in ("input_refs", "output_refs"):
                if isinstance(item.get(key), dict) and item.get(key):
                    flow_item[key] = item.get(key)
            flow.append(flow_item)
        return flow
    return [
        {
            "name": "manual_api",
            "owner": "api.routes_runs",
            "effect": "creates DecisionRequest and traceable run context",
            "source": "static_fallback",
        },
        {
            "name": "legacy_baseline",
            "owner": "workflow.legacy_decision_workflow",
            "effect": "production final input remains legacy_prompt unless switch review approves DecisionInput",
            "source": "static_fallback",
        },
        {
            "name": "shadow_swarm_audit",
            "owner": "LeadAgent plus required Worker Agents",
            "effect": "audit-only worker outputs; downstream control gate may block production action",
            "source": "static_fallback",
        },
        {
            "name": "decision_input_candidate",
            "owner": "decision.pre_final_input",
            "effect": "structured candidate input with refs, missing facts, conflicts, and confidence policy",
            "source": "static_fallback",
        },
        {
            "name": "final_input_selection",
            "owner": "decision.final_input",
            "effect": "selects legacy_prompt or reviewed DecisionInput input",
            "source": "static_fallback",
        },
        {
            "name": "production_control_gate",
            "owner": "decision.production_control_gate",
            "effect": "production-blocking gate based on candidate audit and worker constraints",
            "source": "static_fallback",
        },
        {
            "name": "persistence",
            "owner": "workflow.run_persistence_step",
            "effect": "stores full replay payload; API exposes sanitized projection",
            "source": "static_fallback",
        },
        {
            "name": "frontend_projection",
            "owner": "runs trace detail page",
            "effect": "renders agent audit view without raw prompt or raw completion payloads",
            "source": "static_fallback",
        },
    ]


def _span_tree_refs(payload: dict[str, Any]) -> dict[str, Any]:
    replayable = _mapping(payload.get("replayable_input_candidate"))
    artifact_refs = _mapping(replayable.get("artifact_refs"))
    span_tree_refs = _mapping(artifact_refs.get("span_tree_refs"))
    if span_tree_refs:
        return span_tree_refs
    telemetry_refs = _mapping(artifact_refs.get("telemetry_refs"))
    if telemetry_refs:
        return telemetry_refs
    return {}


def _public_mapping(value: Any, keys: list[str]) -> dict[str, Any]:
    payload = _mapping(value)
    return _drop_none({key: payload.get(key) for key in keys})


def _public_payload_keys(payload: dict[str, Any]) -> list[str]:
    return sorted(
        key
        for key in payload
        if key not in SENSITIVE_PAYLOAD_KEYS and "frozen_input" not in key and "raw" not in key
    )


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        payload = _mapping(value)
        if payload:
            return payload
    return {}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any, *, max_items: int = 20) -> list[str]:
    return [str(item) for item in _list(value)[:max_items]]


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _drop_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value}
