from __future__ import annotations

from crypto_manual_alert.lead.synthesis_artifact import build_lead_synthesis_artifact


def test_lead_synthesis_artifact_records_replayable_contract_refs_and_hashes():
    artifact = build_lead_synthesis_artifact(
        input_ref="trace:trace-1:lead_synthesis_input",
        lead_synthesis={
            "included_contribution_ids": ["c-root", "c-sentiment"],
            "dropped_contributions": [
            {
                "contribution_id": "c-quality",
                "agent_name": "DataQualityAgent",
                "reason": "status=failed",
                "required": True,
                "failure_policy_applied": "hard_block",
                "error_type": "TimeoutError",
                "raw_payload": "do not copy dropped raw payload",
            }
            ],
            "conflicts": ["bullish_root_cause_vs_crowded_longs"],
            "counter_thesis": ["Crowded longs can reverse"],
            "decision_effect": "none",
        },
        lead_plan={
            "plan_id": "shadow:trace-1",
            "plan_ref": "lead_plan:trace-1",
            "plan_hash": "sha256:lead-plan-a",
            "raw_prompt": "do not copy plan prompt",
        },
        worker_manifest=[
            {
                "task_id": "shadow:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "contribution_id": "c-root",
                "output_hash": "sha256:root",
                "raw_snippet": "do not copy worker snippet",
            }
        ],
        required_workers=["RootCauseAgent", "MarketSentimentAgent"],
        policy_version="lead_synthesis_artifact.v1",
    )

    public = artifact.to_public_dict()

    assert public["schema_version"] == 1
    assert public["artifact_type"] == "lead_synthesis"
    assert public["artifact_ref"] == "candidate:lead_synthesis"
    assert public["decision_effect"] == "none"
    assert public["input_ref"] == "trace:trace-1:lead_synthesis_input"
    assert public["input_hash"].startswith("sha256:")
    assert public["lead_plan_ref"] == "lead_plan:trace-1"
    assert public["lead_plan_hash"] == "sha256:lead-plan-a"
    assert public["worker_manifest_hash"].startswith("sha256:")
    assert public["included_contribution_refs"] == [
        {"contribution_id": "c-root", "output_hash": "sha256:root"},
        {"contribution_id": "c-sentiment"},
    ]
    assert public["dropped_contribution_refs"] == [
        {
            "contribution_id": "c-quality",
            "agent_name": "DataQualityAgent",
            "reason": "status=failed",
            "required": True,
            "failure_policy_applied": "hard_block",
            "error_type": "TimeoutError",
        },
        {
            "contribution_id": None,
            "agent_name": "MarketSentimentAgent",
            "reason": "missing_required_worker",
        },
    ]
    assert public["conflict_refs"] == [
        {
            "conflict_id": "bullish_root_cause_vs_crowded_longs",
            "summary": "bullish_root_cause_vs_crowded_longs",
        }
    ]
    assert public["policy_version"] == "lead_synthesis_artifact.v1"

    serialized = str(public)
    assert "do not copy" not in serialized
    assert "raw_payload" not in serialized
    assert "raw_snippet" not in serialized
    assert "raw_prompt" not in serialized


def test_lead_synthesis_artifact_preserves_counter_thesis_refs_without_raw_payloads():
    artifact = build_lead_synthesis_artifact(
        input_ref="trace:trace-1:lead_synthesis_input",
        lead_synthesis={
            "included_contribution_ids": ["c-root", "c-sentiment"],
            "counter_thesis": ["Crowded longs can force a short-term reversal"],
            "counter_thesis_refs": [
                {
                    "contribution_id": "c-sentiment",
                    "agent_name": "MarketSentimentAgent",
                    "claim": "Crowded longs can force a short-term reversal",
                    "side": "bearish",
                    "evidence_ids": ["ev-funding", "ev-oi"],
                    "raw_payload": "do not copy counter raw payload",
                }
            ],
            "strongest_counter_thesis_ref": {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "claim": "Crowded longs can force a short-term reversal",
                "side": "bearish",
                "evidence_ids": ["ev-funding", "ev-oi"],
                "raw_payload": "do not copy strongest counter raw payload",
            },
            "conflict_refs": [
                {
                    "conflict_id": "trend_vs_crowding",
                    "summary": "Bullish trend conflicts with crowded positioning.",
                    "sides": ["bullish", "bearish"],
                    "contribution_refs": ["c-root", "c-sentiment"],
                    "raw_snippet": "do not copy conflict snippet",
                }
            ],
            "decision_effect": "none",
        },
        lead_plan={"plan_id": "shadow:trace-1"},
        worker_manifest=[],
    )

    public = artifact.to_public_dict()

    assert public["counter_thesis_refs"] == [
        {
            "contribution_id": "c-sentiment",
            "agent_name": "MarketSentimentAgent",
            "claim": "Crowded longs can force a short-term reversal",
            "side": "bearish",
            "evidence_ids": ["ev-funding", "ev-oi"],
        }
    ]
    assert public["strongest_counter_thesis_ref"] == {
        "contribution_id": "c-sentiment",
        "agent_name": "MarketSentimentAgent",
        "claim": "Crowded longs can force a short-term reversal",
        "side": "bearish",
        "evidence_ids": ["ev-funding", "ev-oi"],
    }
    assert public["conflict_refs"] == [
        {
            "conflict_id": "trend_vs_crowding",
            "summary": "Bullish trend conflicts with crowded positioning.",
            "sides": ["bullish", "bearish"],
            "contribution_refs": ["c-root", "c-sentiment"],
        }
    ]
    assert public["counter_thesis_count"] == 1
    assert public["conflict_count"] == 1
    serialized = str(public)
    assert "do not copy" not in serialized
    assert "raw_payload" not in serialized
    assert "raw_snippet" not in serialized


def test_lead_synthesis_artifact_input_hash_changes_with_synthesis_plan_and_manifest():
    base_kwargs = {
        "input_ref": "trace:trace-1:lead_synthesis_input",
        "lead_synthesis": {
            "included_contribution_ids": ["c-root"],
            "dropped_contributions": [],
            "conflicts": [],
        },
        "lead_plan": {"plan_ref": "lead_plan:trace-1", "plan_hash": "sha256:lead-plan-a"},
        "worker_manifest": [
            {
                "task_id": "shadow:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "contribution_id": "c-root",
                "output_hash": "sha256:root-a",
            }
        ],
    }

    base = build_lead_synthesis_artifact(**base_kwargs).to_public_dict()
    changed_synthesis = build_lead_synthesis_artifact(
        **{
            **base_kwargs,
            "lead_synthesis": {
                **base_kwargs["lead_synthesis"],
                "conflicts": ["new_conflict"],
            },
        }
    ).to_public_dict()
    changed_plan = build_lead_synthesis_artifact(
        **{
            **base_kwargs,
            "lead_plan": {"plan_ref": "lead_plan:trace-1", "plan_hash": "sha256:lead-plan-b"},
        }
    ).to_public_dict()
    changed_manifest = build_lead_synthesis_artifact(
        **{
            **base_kwargs,
            "worker_manifest": [
                {
                    **base_kwargs["worker_manifest"][0],
                    "output_hash": "sha256:root-b",
                }
            ],
        }
    ).to_public_dict()

    assert base["input_hash"] != changed_synthesis["input_hash"]
    assert base["input_hash"] != changed_plan["input_hash"]
    assert base["input_hash"] != changed_manifest["input_hash"]
    assert base["worker_manifest_hash"] != changed_manifest["worker_manifest_hash"]


def test_lead_synthesis_artifact_preserves_structured_missing_conflict_and_drop_summaries():
    artifact = build_lead_synthesis_artifact(
        input_ref="trace:trace-2:lead_synthesis_input",
        lead_synthesis={
            "included_contribution_ids": [],
            "dropped_contributions": [
                {
                    "contribution_id": "c-timeout",
                    "agent_name": "ExecutionRiskAgent",
                            "reason": "status=timeout",
                            "required": True,
                            "failure_policy_applied": "soft_downgrade",
                            "error_type": "TimeoutError",
                            "summary": "Execution worker timed out before producing a safe ref.",
                            "raw_decision": "do not copy raw decision",
                }
            ],
            "conflicts": [
                {
                    "conflict_id": "bullish_vs_bearish",
                    "summary": "Lead synthesis found opposing bullish and bearish chains.",
                    "sides": ["bullish", "bearish"],
                    "raw_snippet": "do not copy conflict raw snippet",
                }
            ],
            "missing_facts": ["order_book_depth"],
        },
        lead_plan={"plan_id": "shadow:trace-2"},
        worker_manifest=[],
        required_workers=["RootCauseAgent", "ExecutionRiskAgent"],
    )

    public = artifact.to_public_dict()

    assert public["required_worker_status"] == [
        {"agent_name": "RootCauseAgent", "status": "missing"},
        {"agent_name": "ExecutionRiskAgent", "status": "missing"},
    ]
    assert public["dropped_contribution_refs"] == [
        {
            "contribution_id": "c-timeout",
            "agent_name": "ExecutionRiskAgent",
            "reason": "status=timeout",
            "required": True,
            "failure_policy_applied": "soft_downgrade",
            "error_type": "TimeoutError",
            "summary": "Execution worker timed out before producing a safe ref.",
        },
        {
            "contribution_id": None,
            "agent_name": "RootCauseAgent",
            "reason": "missing_required_worker",
        },
    ]
    assert public["conflict_refs"] == [
        {
            "conflict_id": "bullish_vs_bearish",
            "summary": "Lead synthesis found opposing bullish and bearish chains.",
            "sides": ["bullish", "bearish"],
        }
    ]
    assert public["missing_fact_refs"] == [{"fact_ref": "order_book_depth"}]
    serialized = str(public)
    assert "do not copy" not in serialized
    assert "raw_decision" not in serialized
