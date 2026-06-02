import dataclasses

from crypto_manual_alert.artifacts.contributions import (
    AgentContribution,
    contribution_safety_ref_fields,
    from_leader_summary,
)


def test_from_leader_summary_wraps_legacy_reviewers_as_four_contributions():
    leader_summary = {
        "leader_finalizer": {"summary": "legacy finalizer is not a worker contribution"},
        "bull_reviewer": {
            "root_cause_chain": "long setup needs fresh mark and BTC confirmation",
            "confirmation": "OKX mark reclaims trigger",
            "weakness": "search-derived evidence is not executable",
        },
        "bear_reviewer": {
            "root_cause_chain": "risk-off macro can pressure ETH beta",
            "confirmation": "BTC loses structure",
            "weakness": "late short can chase exhausted volatility",
        },
        "data_quality_reviewer": {
            "quality": "search-derived, capped confidence",
            "confidence_cap_hint": 0.58,
            "gaps": ["fresh order book"],
        },
        "execution_risk_reviewer": {
            "risk": "manual only until exchange-native execution facts are fresh",
            "manual_only": True,
        },
    }

    contributions = from_leader_summary(leader_summary, input_ref="artifact://input/1", trace_ref="trace-1")

    assert [item.agent_name for item in contributions] == [
        "bull_reviewer",
        "bear_reviewer",
        "data_quality_reviewer",
        "execution_risk_reviewer",
    ]
    assert all(isinstance(item, AgentContribution) for item in contributions)
    assert all(item.status == "ok" for item in contributions)
    assert all(item.required is True for item in contributions)
    assert all(item.input_ref == "artifact://input/1" for item in contributions)
    assert all(item.trace_ref == "trace-1" for item in contributions)
    assert all(item.output_hash.startswith("sha256:") for item in contributions)
    assert all(item.failure_policy_applied == "none" for item in contributions)
    assert all(item.migration_stage == "legacy_contribution_wrapper" for item in contributions)
    assert "fresh order book" in contributions[2].missing_facts


def test_from_leader_summary_marks_missing_or_invalid_reviewers_without_silent_drop():
    contributions = from_leader_summary(
        {
            "bull_reviewer": "not a structured reviewer",
            "bear_reviewer": {"root_cause_chain": "bear case"},
            "data_quality_reviewer": {"quality": "missing execution facts"},
        }
    )

    by_name = {item.agent_name: item for item in contributions}

    assert set(by_name) == {
        "bull_reviewer",
        "bear_reviewer",
        "data_quality_reviewer",
        "execution_risk_reviewer",
    }
    assert by_name["bull_reviewer"].status == "failed"
    assert "invalid_reviewer_payload" in by_name["bull_reviewer"].conflicts
    assert by_name["execution_risk_reviewer"].status == "failed"
    assert "missing_reviewer_key" in by_name["execution_risk_reviewer"].conflicts
    assert by_name["bear_reviewer"].status == "ok"


def test_from_leader_summary_marks_empty_reviewer_as_partial():
    contributions = from_leader_summary(
        {
            "bull_reviewer": {},
            "bear_reviewer": {"root_cause_chain": "bear case"},
            "data_quality_reviewer": {"quality": "ok"},
            "execution_risk_reviewer": {"risk": "audit existing stop only"},
        }
    )

    bull = contributions[0]

    assert bull.status == "partial"
    assert "empty_reviewer_payload" in bull.conflicts
    assert bull.failure_policy_applied == "soft_downgrade"


def test_from_leader_summary_marks_executable_trade_fields_as_non_final_violations():
    contributions = from_leader_summary(
        {
            "bull_reviewer": {
                "root_cause_chain": "long case",
                "main_action": "open long",
                "entry_trigger": "breakout now",
                "stop_price": 3450,
                "target_1": 3700,
                "target_2": 3900,
                "max_leverage": 5,
                "risk_pct": 0.02,
            },
            "bear_reviewer": {"root_cause_chain": "bear case"},
            "data_quality_reviewer": {"quality": "ok"},
            "execution_risk_reviewer": {"risk": "audit existing stop only"},
        }
    )

    bull = contributions[0]

    assert bull.status == "partial"
    assert bull.constraints["forbidden_executable_fields"] == [
        "main_action",
        "entry_trigger",
        "stop_price",
        "target_1",
        "target_2",
        "max_leverage",
        "risk_pct",
    ]
    assert any("non_final_executable_field" in conflict for conflict in bull.conflicts)
    assert all("main_action" not in claim for claim in bull.claims)


def test_agent_contribution_has_explicit_p3a_compatibility_fields():
    fields = {field.name for field in dataclasses.fields(AgentContribution)}

    assert {
        "contribution_id",
        "agent_name",
        "status",
        "required",
        "summary",
        "claims",
        "constraints",
        "conflicts",
        "missing_facts",
        "input_ref",
        "output_hash",
        "failure_policy_applied",
        "trace_ref",
        "migration_stage",
    } <= fields


def test_agent_contribution_has_explicit_business_projection_fields():
    fields = {field.name for field in dataclasses.fields(AgentContribution)}

    assert {
        "task_id",
        "evidence_ids",
        "confidence_cap",
        "blocked_actions",
    } <= fields


def test_agent_contribution_public_dict_projects_business_fields_from_claims_and_constraints():
    contribution = AgentContribution(
        contribution_id="shadow_swarm:shadow:ExecutionRiskAgent",
        agent_name="ExecutionRiskAgent",
        status="ok",
        required=True,
        summary="execution risk blocks opening",
        claims=[
            {"claim": "order book missing", "evidence_ids": ["ev-order-book"]},
            {"claim": "funding crowded", "evidence_ids": ["ev-funding", "ev-order-book"]},
        ],
        constraints={
            "confidence_cap": 0.55,
            "blocked_actions": ["open long", "trigger long"],
        },
        input_ref="trace:1:shadow_input",
        output_hash="sha256:execution",
        failure_policy_applied="none",
        trace_ref="trace-1:shadow:ExecutionRiskAgent",
    )

    public = contribution.to_public_dict()

    assert public["task_id"] == "shadow:ExecutionRiskAgent"
    assert public["evidence_ids"] == ["ev-order-book", "ev-funding"]
    assert public["confidence_cap"] == 0.55
    assert public["blocked_actions"] == ["open long", "trigger long"]


def test_contribution_safety_ref_fields_projects_top_level_and_constraint_values():
    contribution = {
        "blocked_actions": ["open long"],
        "constraints": {
            "confidence_cap_reasons": ["facts_gate:execution_facts_missing"],
            "hard_block": True,
            "hard_block_reasons": ["facts_gate:execution_facts_missing"],
            "manual_review_reminders": ["manual review required"],
            "allowed_action_class_reduction": {"remaining_action_classes": ["manual_review_only"]},
            "required_confirmations": ["confirm order_book"],
        },
    }

    assert contribution_safety_ref_fields(contribution) == {
        "confidence_cap": None,
        "confidence_cap_reasons": ["facts_gate:execution_facts_missing"],
        "blocked_actions": ["open long"],
        "hard_block": True,
        "hard_block_reasons": ["facts_gate:execution_facts_missing"],
        "manual_review_reminders": ["manual review required"],
        "allowed_action_class_reduction": {"remaining_action_classes": ["manual_review_only"]},
        "required_confirmations": ["confirm order_book"],
    }
