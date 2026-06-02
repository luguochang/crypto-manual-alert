from __future__ import annotations

import pytest

from crypto_manual_alert.artifacts.contributions import AgentContribution, from_leader_summary
from crypto_manual_alert.orchestration.harness import (
    load_harness_policy,
    validate_agent_contributions,
    validate_agent_run_request,
)
from crypto_manual_alert.skills.facade import SkillConstraints, SkillToolResult


def test_harness_validation_flags_non_final_trade_fields_in_contributions():
    """Harness 必须把 reviewer 输出交易动作字段标成运行时违规。"""
    contributions = from_leader_summary(
        {
            "bull_reviewer": {
                "root_cause_chain": "long case",
                "main_action": "open long",
                "entry_trigger": 3510,
            },
            "bear_reviewer": {"root_cause_chain": "bear case"},
            "data_quality_reviewer": {"quality": "ok"},
            "execution_risk_reviewer": {"risk": "manual only"},
        },
        input_ref="trace:1:leader_summary",
        trace_ref="trace-1",
    )

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert result.severity == "hard_fail"
    assert {
        violation["rule_id"] for violation in result.violations if violation["agent_name"] == "bull_reviewer"
    } == {
        "agent.required_contribution.failed",
        "agent.non_final.executable_fields",
    }
    assert {
        tuple(violation["fields"])
        for violation in result.violations
        if violation["rule_id"] == "agent.non_final.executable_fields"
    } == {("main_action", "entry_trigger")}


def test_harness_validation_passes_clean_legacy_contributions():
    contributions = from_leader_summary(
        {
            "bull_reviewer": {"root_cause_chain": "long case"},
            "bear_reviewer": {"root_cause_chain": "bear case"},
            "data_quality_reviewer": {"quality": "ok"},
            "execution_risk_reviewer": {"risk": "manual only"},
        },
        input_ref="trace:1:leader_summary",
        trace_ref="trace-1",
    )

    result = validate_agent_contributions(contributions)

    assert result.passed is True
    assert result.severity == "ok"
    assert result.violations == []


def test_harness_validation_fails_required_missing_or_failed_reviewers():
    contributions = from_leader_summary(
        {
            "bull_reviewer": "invalid",
            "bear_reviewer": {"root_cause_chain": "bear case"},
            "data_quality_reviewer": {"quality": "ok"},
        }
    )

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    rule_ids = {violation["rule_id"] for violation in result.violations}
    assert "agent.required_contribution.failed" in rule_ids
    assert any(violation["agent_name"] == "execution_risk_reviewer" for violation in result.violations)


def test_harness_validation_fails_unknown_agent_and_invalid_status():
    contributions = [
        AgentContribution(
            contribution_id="legacy_contribution_wrapper:unknown",
            agent_name="unknown_reviewer",
            status="maybe",
            required=True,
            summary="invalid status",
            input_ref="trace:1:leader_summary",
            output_hash="sha256:unknown",
            failure_policy_applied="none",
            trace_ref="trace-1",
        )
    ]

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "unknown_reviewer",
            "rule_id": "agent.not_enabled",
        },
        {
            "agent_name": "unknown_reviewer",
            "rule_id": "agent.status.invalid",
            "status": "maybe",
        },
    ]


def test_harness_validation_rejects_missing_p3a_audit_fields():
    contributions = [
        AgentContribution(
            contribution_id="legacy_contribution_wrapper:bull_reviewer",
            agent_name="bull_reviewer",
            status="ok",
            required=True,
            summary="missing audit refs",
            output_hash="",
            failure_policy_applied="",
        )
    ]

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert {
        violation["rule_id"]
        for violation in result.violations
        if violation["agent_name"] == "bull_reviewer"
    } == {
        "agent.schema.input_ref_missing",
        "agent.schema.output_hash_missing",
        "agent.schema.failure_policy_missing",
        "agent.schema.trace_ref_missing",
    }


def test_harness_validation_rejects_failed_policy_envelope_with_ok_status():
    contributions = [
        AgentContribution(
            contribution_id="shadow_swarm:shadow:DataQualityAgent",
            agent_name="DataQualityAgent",
            status="ok",
            required=True,
            summary="timeout was incorrectly marked ok",
            input_ref="trace:1:shadow_input",
            output_hash="sha256:timeout",
            failure_policy_applied="hard_block",
            trace_ref="trace-1:shadow:DataQualityAgent",
        )
    ]

    result = validate_agent_contributions(contributions, policy=load_harness_policy("shadow_audit"))

    assert result.passed is False
    assert {
        violation["rule_id"]
        for violation in result.violations
        if violation["agent_name"] == "DataQualityAgent"
    } == {"agent.failure_envelope.status_mismatch"}


def test_harness_validation_rejects_non_final_trade_fields_without_constraints_marker():
    contributions = [
        AgentContribution(
            contribution_id="manual:bull",
            agent_name="bull_reviewer",
            status="ok",
            required=True,
            summary="main_action: open long if breakout confirms",
            claims=[{"claim": "entry_trigger: 3500"}],
            constraints={},
            input_ref="trace:1:manual",
            output_hash="sha256:manual",
            failure_policy_applied="none",
            trace_ref="trace-1",
        )
    ]

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "bull_reviewer",
            "rule_id": "agent.non_final.executable_fields",
            "fields": ["main_action", "entry_trigger"],
        }
    ]


def test_harness_validation_rejects_non_none_contribution_decision_effect():
    contributions = [
        AgentContribution(
            contribution_id="manual:effect",
            agent_name="RootCauseAgent",
            status="ok",
            required=True,
            summary="bad decision effect",
            constraints={"decision_effect": "production_final_input"},
            input_ref="trace:1:manual",
            output_hash="sha256:manual",
            failure_policy_applied="none",
            trace_ref="trace-1",
            migration_stage="llm_tool_shadow_worker",
        )
    ]

    result = validate_agent_contributions(contributions, policy=load_harness_policy("shadow_audit"))

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "RootCauseAgent",
            "rule_id": "agent.constraints.decision_effect_not_none",
            "decision_effect": "production_final_input",
        }
    ]


def test_harness_validation_rejects_raw_skill_tool_result_payload_inside_contribution():
    contributions = [
        AgentContribution(
            contribution_id="shadow_swarm:shadow:RootCauseAgent",
            agent_name="RootCauseAgent",
            status="ok",
            required=True,
            summary="raw skill payload leaked into contribution constraints",
            constraints={
                "decision_effect": "none",
                "tool_audit_results": [
                    {
                        "skill_name": "realtime_search",
                        "task_id": "skill:realtime_search",
                        "status": "ok",
                        "decision_effect": "none",
                        "result_type": "evidence_candidates",
                        "source_type": "search_derived",
                        "can_satisfy_execution_fact": False,
                        "evidence_candidates": [],
                        "constraints": {"must_pass_facts_gate": True},
                        "missing_inputs": [],
                        "trace_ref": "trace-1:skill:realtime_search",
                    }
                ],
            },
            input_ref="trace:1:shadow_input",
            output_hash="sha256:root",
            failure_policy_applied="none",
            trace_ref="trace-1:shadow:RootCauseAgent",
            migration_stage="shadow_swarm",
        )
    ]

    result = validate_agent_contributions(contributions, policy=load_harness_policy("shadow_audit"))

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "RootCauseAgent",
            "rule_id": "agent.skill_tool_result_direct_payload",
            "paths": ["constraints.tool_audit_results[0]"],
        }
    ]


def test_harness_validation_rejects_raw_skill_tool_result_object_inside_contribution():
    tool_result = SkillToolResult(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        status="ok",
        result_type="evidence_candidates",
        source_type="search_derived",
        can_satisfy_execution_fact=False,
        constraints=SkillConstraints(raw_snippets_redacted=True),
        trace_ref="trace-1:skill:realtime_search",
    )
    contributions = [
        AgentContribution(
            contribution_id="shadow_swarm:shadow:RootCauseAgent",
            agent_name="RootCauseAgent",
            status="ok",
            required=True,
            summary="raw skill object leaked into contribution constraints",
            constraints={
                "decision_effect": "none",
                "tool_audit_results": [tool_result],
            },
            input_ref="trace:1:shadow_input",
            output_hash="sha256:root",
            failure_policy_applied="none",
            trace_ref="trace-1:shadow:RootCauseAgent",
            migration_stage="shadow_swarm",
        )
    ]

    result = validate_agent_contributions(contributions, policy=load_harness_policy("shadow_audit"))

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "RootCauseAgent",
            "rule_id": "agent.skill_tool_result_direct_payload",
            "paths": ["constraints.tool_audit_results[0]"],
        }
    ]


@pytest.mark.parametrize("field_name", load_harness_policy("production_decision").non_final_forbidden_fields)
def test_harness_validation_rejects_every_non_final_forbidden_field_in_text(field_name):
    contributions = [
        AgentContribution(
            contribution_id=f"manual:{field_name}",
            agent_name="bull_reviewer",
            status="ok",
            required=True,
            summary=f"{field_name}: should not be emitted by non-final agent",
            constraints={},
            input_ref="trace:1:manual",
            output_hash="sha256:manual",
            failure_policy_applied="none",
            trace_ref="trace-1",
        )
    ]

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "bull_reviewer",
            "rule_id": "agent.non_final.executable_fields",
            "fields": [field_name],
        }
    ]


def test_harness_validation_recursively_rejects_non_final_forbidden_structured_fields():
    contributions = [
        AgentContribution(
            contribution_id="manual:structured",
            agent_name="bull_reviewer",
            status="ok",
            required=True,
            summary="structured payload",
            claims=[{"risk_verdict": "allowed"}],
            constraints={"notification": {"channel": "bark"}, "nested": {"order_payload": {"side": "buy"}}},
            input_ref="trace:1:manual",
            output_hash="sha256:manual",
            failure_policy_applied="none",
            trace_ref="trace-1",
        )
    ]

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert result.violations[0]["agent_name"] == "bull_reviewer"
    assert result.violations[0]["rule_id"] == "agent.non_final.executable_fields"
    assert set(result.violations[0]["fields"]) == {"risk_verdict", "notification", "order_payload"}


def test_harness_validation_fails_final_agent_tool_requests():
    contributions = [
        AgentContribution(
            contribution_id="final",
            agent_name="FinalDecisionAgent",
            status="ok",
            required=True,
            summary="final decision requests a tool",
            constraints={"requested_tools": ["web_search"]},
            input_ref="trace:1:final",
            output_hash="sha256:final",
            failure_policy_applied="none",
            trace_ref="trace-1",
        )
    ]

    result = validate_agent_contributions(contributions)

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "FinalDecisionAgent",
            "rule_id": "final_agent.tool_request_forbidden",
            "requested_tools": ["web_search"],
        }
    ]


def test_harness_policy_defines_shadow_audit_as_read_only_run_mode():
    policy = load_harness_policy("shadow_audit")

    assert policy.run_mode == "shadow_audit"
    assert policy.allow_journal_write is False
    assert policy.allow_notification is False
    assert policy.agent_policy("LiveFactAgent").allowed_tools == ("realtime_search",)
    assert policy.agent_policy("MacroEventAgent").allowed_tools == ("macro_event",)
    assert policy.agent_policy("RootCauseAgent").allowed_tools == ("root_cause_search",)
    assert policy.agent_policy("MarketSentimentAgent").allowed_tools == ("market_sentiment",)
    assert policy.agent_policy("ExecutionRiskAgent").allowed_tools == ("liquidity_order_book",)
    assert policy.agent_policy("FinalDecisionAgent").allowed_tools == ()


def test_harness_run_request_blocks_unknown_agent_and_unapproved_tools():
    policy = load_harness_policy("shadow_audit")

    result = validate_agent_run_request(
        policy,
        agent_name="UnknownAgent",
        requested_tools=["root_cause_search", "place_order"],
    )

    assert result.passed is False
    assert result.severity == "hard_fail"
    assert result.violations == [
        {
            "agent_name": "UnknownAgent",
            "rule_id": "agent.not_enabled",
        },
        {
            "agent_name": "UnknownAgent",
            "rule_id": "agent.tool_not_allowed",
            "requested_tools": ["root_cause_search", "place_order"],
            "allowed_tools": [],
        },
    ]


def test_harness_run_request_blocks_enabled_agent_unapproved_tool():
    policy = load_harness_policy("shadow_audit")

    result = validate_agent_run_request(policy, agent_name="DataQualityAgent", requested_tools=["root_cause_search"])

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "DataQualityAgent",
            "rule_id": "agent.tool_not_allowed",
            "requested_tools": ["root_cause_search"],
            "allowed_tools": [],
        }
    ]


def test_harness_run_request_blocks_legacy_web_search_as_primary_worker_tool():
    policy = load_harness_policy("shadow_audit")

    result = validate_agent_run_request(policy, agent_name="RootCauseAgent", requested_tools=["web_search"])

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "RootCauseAgent",
            "rule_id": "agent.tool_not_allowed",
            "requested_tools": ["web_search"],
            "allowed_tools": ["root_cause_search"],
        }
    ]


def test_harness_run_request_blocks_final_agent_tools_even_if_requested_tool_is_known():
    policy = load_harness_policy("shadow_audit")

    result = validate_agent_run_request(policy, agent_name="FinalDecisionAgent", requested_tools=["root_cause_search"])

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "FinalDecisionAgent",
            "rule_id": "final_agent.tool_request_forbidden",
            "requested_tools": ["root_cause_search"],
        },
        {
            "agent_name": "FinalDecisionAgent",
            "rule_id": "agent.tool_not_allowed",
            "requested_tools": ["root_cause_search"],
            "allowed_tools": [],
        },
    ]


def test_harness_rejects_unknown_run_mode():
    try:
        load_harness_policy("live_trading")
    except ValueError as exc:
        assert "run_mode" in str(exc)
    else:
        raise AssertionError("unknown harness run_mode should be rejected")
