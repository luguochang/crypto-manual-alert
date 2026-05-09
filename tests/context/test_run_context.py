from __future__ import annotations

from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext, ReservedContextWriteError, SideEffectPolicy
from crypto_manual_alert.decision.frozen_input import stable_hash


def test_decision_run_context_keeps_full_request_semantics():
    """运行上下文必须保留完整请求，不能在入口层退化成 symbol 字符串。"""
    request = DecisionRequest(
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        query_text="评估 ETH 是否还能追多",
        horizon="6h",
        session_id="session-1",
    )

    context = DecisionRunContext.create(request)

    assert context.run_id
    assert context.request is request
    assert context.symbol == "ETH-USDT-SWAP"
    assert context.query_text == "评估 ETH 是否还能追多"
    assert context.horizon == "6h"
    assert context.session_id == "session-1"
    assert context.side_effect_policy.allow_production_journal_write is True
    assert context.side_effect_policy.allow_notification_intent is True


def test_side_effect_policy_blocks_eval_replay_and_postmortem_side_effects():
    """旁路运行默认零副作用，不能写生产 journal，也不能生成通知意图。"""
    for run_type in ("eval", "replay", "postmortem"):
        policy = SideEffectPolicy.from_run_type(run_type)

        assert policy.allow_production_journal_write is False
        assert policy.allow_notification_intent is False


def test_decision_run_context_summary_is_stable_for_api_and_trace_boundaries():
    """context 摘要用于 API/trace 调试，只暴露稳定业务字段。"""
    context = DecisionRunContext.create(DecisionRequest(symbol=" sol-usdt-swap ", query_text="  看 SOL  "))

    assert context.to_public_summary() == {
        "run_id": context.run_id,
        "run_type": "manual",
        "symbol": "SOL-USDT-SWAP",
        "query_text": "看 SOL",
        "query_semantics": {
            "mode": "audit_note",
            "drives_lead_plan": False,
            "drives_worker_selection": False,
            "drives_tool_budget": False,
            "drives_facts_requirement": False,
            "drives_final_input": False,
            "explanation": "query_text is retained for operator audit context; current production planning is driven by symbol/horizon/config.",
        },
        "horizon": None,
        "session_id": None,
        "manual_only": True,
        "memory_snapshot": {
            "snapshot_id": "memory:none:empty",
            "session_id": None,
            "allowed_fields": {},
            "recent_turn_count": 0,
            "summary": None,
            "long_term_memory_refs": [],
        },
        "side_effect_policy": {
            "allow_production_journal_write": True,
            "allow_notification_intent": True,
        },
    }


def test_decision_run_context_records_safe_memory_snapshot_without_raw_messages():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP", session_id="session-1"))

    context.set_memory_snapshot(
        {
            "snapshot_id": "memory:session-1:turn-12",
            "session_id": "session-1",
            "allowed_fields": {"risk_preference": "low"},
            "recent_turn_count": 5,
            "summary": "User prefers lower leverage.",
            "long_term_memory_refs": [{"memory_id": "mem-1", "memory_hash": "sha256:mem-1", "score": 0.9}],
            "messages": [{"role": "user", "content": "raw conversation must not leak"}],
            "raw_conversation": "raw conversation must not leak",
        },
        writer_role="session_memory",
    )

    summary = context.to_public_summary()

    assert summary["memory_snapshot"] == {
        "snapshot_id": "memory:session-1:turn-12",
        "session_id": "session-1",
        "allowed_fields": {"risk_preference": "low"},
        "recent_turn_count": 5,
        "summary": "User prefers lower leverage.",
        "long_term_memory_refs": [{"memory_id": "mem-1", "memory_hash": "sha256:mem-1", "score": 0.9}],
    }
    assert "raw conversation must not leak" not in str(summary)


def test_decision_run_context_quarantines_market_fact_like_memory_fields():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP", session_id="session-1"))

    context.set_memory_snapshot(
        {
            "snapshot_id": "memory:session-1:turn-13",
            "session_id": "session-1",
            "allowed_fields": {
                "risk_preference": "low",
                "user_position": "long",
                "position_slots": {"symbol": "ETH-USDT-SWAP", "side": "long", "entry_price": 3200},
                "asset_focus": ["ETH"],
                "preferred_horizon": "4h",
                "language": "zh-CN",
                "mark": 3500.5,
                "funding": "0.08%",
                "open_interest": 123456,
                "order_book": {"best_bid": 3499},
                "news_status": "ETF headline still active",
                "macro_event_status": "CPI surprise pending",
                "last_model_conclusion": "trigger long now",
                "previous_final_action": "open long",
            },
            "recent_turn_count": 6,
        },
        writer_role="session_memory",
    )

    memory = context.to_public_summary()["memory_snapshot"]

    assert memory["allowed_fields"] == {
        "asset_focus": ["ETH"],
        "language": "zh-CN",
        "position_slots": {"symbol": "ETH-USDT-SWAP", "side": "long", "entry_price": 3200},
        "preferred_horizon": "4h",
        "risk_preference": "low",
        "user_position": "long",
    }
    assert memory["quarantined_fields"] == [
        "allowed_fields.funding",
        "allowed_fields.last_model_conclusion",
        "allowed_fields.macro_event_status",
        "allowed_fields.mark",
        "allowed_fields.news_status",
        "allowed_fields.open_interest",
        "allowed_fields.order_book",
        "allowed_fields.previous_final_action",
    ]
    assert memory["memory_warnings"] == [
        "memory_snapshot.quarantined_fact_like_fields: memory is context only, not live market evidence"
    ]
    serialized = str(memory)
    assert "3500.5" not in serialized
    assert "ETF headline still active" not in serialized
    assert "trigger long now" not in serialized


def test_decision_run_context_records_append_only_workflow_artifacts():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))

    context.append_evidence({"evidence_id": "ev-1", "data_type": "mark"}, writer_role="workflow")
    context.append_contribution(
        {"contribution_id": "c-1", "agent_name": "DataQualityAgent"},
        writer_role="worker",
    )
    context.set_lead_plan({"plan_id": "lead-1", "task_count": 4}, writer_role="lead")
    context.set_decision_input(
        {"input_ref": "trace:1:decision_input_candidate"},
        writer_role="decision_input_builder",
    )
    context.set_gate_result("facts_gate", {"passed": False}, writer_role="gate")

    artifacts = context.to_artifact_summary()

    assert artifacts == {
        "evidence_count": 1,
        "contribution_count": 1,
        "has_lead_plan": True,
        "has_decision_input": True,
        "gate_result_names": ["facts_gate"],
        "reserved_sections": [],
        "evidence_refs": [
            {
                "evidence_id": "ev-1",
                "data_type": "mark",
                "artifact_hash": stable_hash({"evidence_id": "ev-1", "data_type": "mark"}),
            }
        ],
        "contribution_refs": [
            {
                "contribution_id": "c-1",
                "agent_name": "DataQualityAgent",
                "confidence_cap": None,
                "confidence_cap_reasons": [],
                "blocked_actions": [],
                "hard_block": False,
                "hard_block_reasons": [],
                "manual_review_reminders": [],
                "allowed_action_class_reduction": {},
                "required_confirmations": [],
                "artifact_hash": stable_hash({"contribution_id": "c-1", "agent_name": "DataQualityAgent"}),
            }
        ],
        "lead_plan_ref": {
            "plan_id": "lead-1",
            "artifact_hash": stable_hash({"plan_id": "lead-1", "task_count": 4}),
        },
        "decision_input_ref": {
            "input_ref": "trace:1:decision_input_candidate",
            "artifact_hash": stable_hash({"input_ref": "trace:1:decision_input_candidate"}),
        },
        "gate_result_refs": {"facts_gate": {"passed": False, "artifact_hash": stable_hash({"passed": False})}},
    }
    assert context.evidence_packets == [{"evidence_id": "ev-1", "data_type": "mark"}]
    assert context.agent_contributions == [{"contribution_id": "c-1", "agent_name": "DataQualityAgent"}]
    assert context.lead_plan == {"plan_id": "lead-1", "task_count": 4}
    assert context.decision_input == {"input_ref": "trace:1:decision_input_candidate"}
    assert context.gate_results == {"facts_gate": {"passed": False}}


def test_decision_run_context_artifact_summary_exposes_safe_refs_without_raw_payloads():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    context.append_evidence(
        {
            "evidence_id": "ev-1",
            "data_type": "mark",
            "source_type": "exchange_native",
            "source_url": "https://okx.example/mark",
            "raw_payload": "raw exchange json must not leak",
        },
        writer_role="workflow",
    )
    context.append_contribution(
        {
            "contribution_id": "c-root",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "input_ref": "trace:1:shadow_input",
            "output_hash": "sha256:root",
            "summary": "raw contribution text must not leak",
        },
        writer_role="worker",
    )
    context.set_lead_plan(
        {"plan_id": "shadow:trace-1", "tasks": [{"raw": "must not leak"}]},
        writer_role="lead",
    )
    context.set_decision_input(
        {
            "input_ref": "trace:1:decision_input_candidate",
            "input_hash": "sha256:decision",
            "raw": "must not leak",
        },
        writer_role="decision_input_builder",
    )
    context.set_gate_result(
        "replayable_input_candidate",
        {
            "input_ref": "trace:1:replayable_input_candidate",
            "input_hash": "sha256:replayable",
            "raw": "must not leak",
        },
        writer_role="gate",
    )

    summary = context.to_artifact_summary()

    assert summary["evidence_refs"] == [
        {
            "evidence_id": "ev-1",
            "data_type": "mark",
            "source_type": "exchange_native",
            "source_url": "https://okx.example/mark",
            "artifact_hash": stable_hash(
                {
                    "evidence_id": "ev-1",
                    "data_type": "mark",
                    "source_type": "exchange_native",
                    "source_url": "https://okx.example/mark",
                    "raw_payload": "raw exchange json must not leak",
                }
            ),
        }
    ]
    assert summary["contribution_refs"] == [
        {
            "contribution_id": "c-root",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "input_ref": "trace:1:shadow_input",
            "output_hash": "sha256:root",
            "confidence_cap": None,
            "confidence_cap_reasons": [],
            "blocked_actions": [],
            "hard_block": False,
            "hard_block_reasons": [],
            "manual_review_reminders": [],
            "allowed_action_class_reduction": {},
            "required_confirmations": [],
            "artifact_hash": stable_hash(
                {
                    "contribution_id": "c-root",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "input_ref": "trace:1:shadow_input",
                    "output_hash": "sha256:root",
                    "summary": "raw contribution text must not leak",
                }
            ),
        }
    ]
    assert summary["lead_plan_ref"] == {
        "plan_id": "shadow:trace-1",
        "artifact_hash": stable_hash({"plan_id": "shadow:trace-1", "tasks": [{"raw": "must not leak"}]}),
    }
    assert summary["decision_input_ref"] == {
        "input_ref": "trace:1:decision_input_candidate",
        "input_hash": "sha256:decision",
        "artifact_hash": stable_hash(
            {
                "input_ref": "trace:1:decision_input_candidate",
                "input_hash": "sha256:decision",
                "raw": "must not leak",
            }
        ),
    }
    assert summary["gate_result_refs"]["replayable_input_candidate"] == {
        "input_ref": "trace:1:replayable_input_candidate",
        "input_hash": "sha256:replayable",
        "artifact_hash": stable_hash(
            {
                "input_ref": "trace:1:replayable_input_candidate",
                "input_hash": "sha256:replayable",
                "raw": "must not leak",
            }
        ),
    }
    serialized = str(summary)
    assert "raw exchange json must not leak" not in serialized
    assert "raw contribution text must not leak" not in serialized
    assert "must not leak" not in serialized


def test_decision_run_context_contribution_refs_include_pre_final_safety_fields():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    contribution = {
        "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
        "agent_name": "ExecutionRiskAgent",
        "task_id": "shadow:ExecutionRiskAgent",
        "status": "ok",
        "required": True,
        "input_ref": "trace:1:shadow_input",
        "output_hash": "sha256:risk",
        "trace_ref": "trace-1:shadow:ExecutionRiskAgent",
        "evidence_ids": ["ev-order-book"],
        "confidence_cap": 0.55,
        "blocked_actions": ["open long"],
        "constraints": {
            "decision_effect": "none",
            "confidence_cap_reasons": ["facts_gate:execution_facts_missing"],
            "hard_block": True,
            "hard_block_reasons": ["facts_gate:execution_facts_missing"],
            "manual_review_reminders": ["manual review required until order_book is fresh"],
            "allowed_action_class_reduction": {
                "remaining_action_classes": ["manual_review_only"],
            },
            "required_confirmations": ["confirm order_book is fresh"],
        },
    }

    context.append_contribution(contribution, writer_role="worker")

    ref = context.to_artifact_summary()["contribution_refs"][0]

    assert ref == {
        "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
        "agent_name": "ExecutionRiskAgent",
        "task_id": "shadow:ExecutionRiskAgent",
        "status": "ok",
        "required": True,
        "input_ref": "trace:1:shadow_input",
        "output_hash": "sha256:risk",
        "trace_ref": "trace-1:shadow:ExecutionRiskAgent",
        "evidence_ids": ["ev-order-book"],
        "confidence_cap": 0.55,
        "confidence_cap_reasons": ["facts_gate:execution_facts_missing"],
        "blocked_actions": ["open long"],
        "hard_block": True,
        "hard_block_reasons": ["facts_gate:execution_facts_missing"],
        "manual_review_reminders": ["manual review required until order_book is fresh"],
        "allowed_action_class_reduction": {
            "remaining_action_classes": ["manual_review_only"],
        },
        "required_confirmations": ["confirm order_book is fresh"],
        "artifact_hash": stable_hash(contribution),
    }


def test_decision_run_context_contribution_refs_include_tool_call_artifact_refs_without_raw_payloads():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    contribution = {
        "contribution_id": "shadow_swarm:shadow:RootCauseAgent",
        "agent_name": "RootCauseAgent",
        "status": "ok",
        "input_ref": "trace:1:shadow_input",
        "output_hash": "sha256:root",
        "tool_call_artifact_refs": [
            {
                "tool_call_id": "tool-call-1",
                "skill_name": "root_cause_search",
                "status": "ok",
                "source_type": "search_derived",
                "source_tier": "external_search",
                "retrieved_at": "2026-07-04T01:00:00Z",
                "freshness_status": "fresh",
                "result_ref": "skill:root_cause_search:trace-1:1",
                "output_hash": "sha256:tool-output",
                "can_satisfy_execution_fact": False,
                "result_count": 3,
                "raw_payload": "raw tool payload must not leak",
                "snippet": "raw snippet must not leak",
                "error": {"message": "raw error must not leak"},
            }
        ],
    }

    context.append_contribution(contribution, writer_role="worker")

    ref = context.to_artifact_summary()["contribution_refs"][0]

    assert ref["tool_call_artifact_refs"] == [
        {
            "tool_call_id": "tool-call-1",
            "skill_name": "root_cause_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "external_search",
            "retrieved_at": "2026-07-04T01:00:00Z",
            "freshness_status": "fresh",
            "result_ref": "skill:root_cause_search:trace-1:1",
            "output_hash": "sha256:tool-output",
            "can_satisfy_execution_fact": False,
            "result_count": 3,
        }
    ]
    serialized = str(ref)
    assert "raw tool payload must not leak" not in serialized
    assert "raw snippet must not leak" not in serialized
    assert "raw error must not leak" not in serialized
    assert "raw_payload" not in serialized
    assert "snippet" not in serialized


def test_decision_run_context_artifact_accessors_return_copies():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    context.append_evidence({"evidence_id": "ev-1", "nested": {"value": 1}}, writer_role="workflow")
    context.append_contribution({"contribution_id": "c-1", "nested": {"value": 1}}, writer_role="worker")
    context.set_gate_result("facts_gate", {"nested": {"value": 1}}, writer_role="gate")

    evidence = context.evidence_packets
    contributions = context.agent_contributions
    gates = context.gate_results
    evidence[0]["nested"]["value"] = 99
    contributions[0]["nested"]["value"] = 99
    gates["facts_gate"]["nested"]["value"] = 99

    assert context.evidence_packets[0]["nested"]["value"] == 1
    assert context.agent_contributions[0]["nested"]["value"] == 1
    assert context.gate_results["facts_gate"]["nested"]["value"] == 1


def test_decision_run_context_rejects_worker_writes_to_reserved_sections():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))

    try:
        context.write_section("final_decision", {"main_action": "trigger long"}, writer_role="worker")
    except ReservedContextWriteError as exc:
        assert exc.section_name == "final_decision"
        assert exc.writer_role == "worker"
    else:
        raise AssertionError("worker should not write final_decision")

    context.write_section("lead_plan", {"plan_id": "lead-1"}, writer_role="lead")

    assert context.lead_plan == {"plan_id": "lead-1"}


def test_worker_role_cannot_write_lead_plan_decision_input_or_gate_results():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))

    for section_name in ("lead_plan", "decision_input", "facts_gate"):
        try:
            context.write_section(section_name, {"attempt": section_name}, writer_role="worker")
        except ReservedContextWriteError as exc:
            assert exc.section_name == section_name
            assert exc.writer_role == "worker"
        else:
            raise AssertionError(f"worker should not write {section_name}")

    assert context.lead_plan is None
    assert context.decision_input is None
    assert context.gate_results == {}


def test_direct_context_setters_require_authorized_writer_roles():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))

    unsafe_writes = (
        lambda: context.set_lead_plan({"plan_id": "lead-1"}),
        lambda: context.set_decision_input({"input_ref": "trace:1:decision_input_candidate"}),
        lambda: context.set_gate_result("facts_gate", {"passed": True}),
        lambda: context.set_lead_plan({"plan_id": "lead-1"}, writer_role="worker"),
        lambda: context.set_decision_input(
            {"input_ref": "trace:1:decision_input_candidate"},
            writer_role="worker",
        ),
        lambda: context.set_decision_input(
            {"input_ref": "trace:1:decision_input_candidate"},
            writer_role="final",
        ),
        lambda: context.set_gate_result("facts_gate", {"passed": True}, writer_role="worker"),
        lambda: context.set_gate_result("final_decision", {"main_action": "trigger long"}, writer_role="gate"),
    )

    for write in unsafe_writes:
        try:
            write()
        except ReservedContextWriteError:
            pass
        else:
            raise AssertionError("direct context setter should enforce writer role")

    context.set_lead_plan({"plan_id": "lead-1"}, writer_role="lead")
    context.set_decision_input(
        {"input_ref": "trace:1:decision_input_candidate"},
        writer_role="decision_input_builder",
    )
    context.set_gate_result("facts_gate", {"passed": True}, writer_role="gate")

    assert context.lead_plan == {"plan_id": "lead-1"}
    assert context.decision_input == {"input_ref": "trace:1:decision_input_candidate"}
    assert context.gate_results == {"facts_gate": {"passed": True}}


def test_decision_run_context_requires_authorized_append_writer_roles():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))

    for append in (context.append_evidence, context.append_contribution):
        try:
            append({"id": "missing-role"})
        except ReservedContextWriteError as exc:
            assert exc.writer_role == "unknown"
        else:
            raise AssertionError("append should require explicit writer_role")

    for writer_role in ("final", "external"):
        try:
            context.append_evidence({"evidence_id": "ev-final"}, writer_role=writer_role)
        except ReservedContextWriteError as exc:
            assert exc.writer_role == writer_role
            assert exc.section_name == "evidence_store"
        else:
            raise AssertionError(f"{writer_role} should not append evidence")

        try:
            context.append_contribution({"contribution_id": "c-final"}, writer_role=writer_role)
        except ReservedContextWriteError as exc:
            assert exc.writer_role == writer_role
            assert exc.section_name == "contribution_store"
        else:
            raise AssertionError(f"{writer_role} should not append contribution")

    context.append_evidence({"evidence_id": "ev-worker"}, writer_role="worker")
    context.append_contribution({"contribution_id": "c-workflow"}, writer_role="workflow")

    assert context.evidence_packets == [{"evidence_id": "ev-worker"}]
    assert context.agent_contributions == [{"contribution_id": "c-workflow"}]
