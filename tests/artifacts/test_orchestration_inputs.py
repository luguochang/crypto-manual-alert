from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts
from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.research_pipeline import ResearchAudit, ResearchPlan


def test_build_audit_artifacts_normalizes_evidence_facts_and_legacy_contributions():
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, None, "fixture"),
            "index": DataPoint("index", 3498.0, None, "fixture"),
        },
    )
    research_audit = ResearchAudit(
        plan=ResearchPlan(queries=[], reason="fixture"),
        leader_summary={
            "bull_reviewer": {"summary": "bull", "confirmation": "breakout"},
            "bear_reviewer": {"summary": "bear"},
            "data_quality_reviewer": {"quality": "missing book", "gaps": ["order_book"]},
            "execution_risk_reviewer": {"risk": "manual only", "manual_only": True},
        },
    )

    payload = build_audit_artifacts(
        trace_id="trace-1",
        snapshot=snapshot,
        research_audit=research_audit,
    )

    assert [packet["data_type"] for packet in payload["evidence_packets"]] == ["index", "mark"]
    assert payload["facts_gate"]["passed"] is False
    assert payload["facts_gate"]["missing_execution_facts"] == ["index", "mark", "order_book"]
    assert [item["agent_name"] for item in payload["agent_contributions"]] == [
        "bull_reviewer",
        "bear_reviewer",
        "data_quality_reviewer",
        "execution_risk_reviewer",
    ]
    assert payload["harness_validation"]["passed"] is True
    assert payload["agent_contributions"][0]["input_ref"] == "trace:trace-1:leader_summary"


def test_build_audit_artifacts_handles_missing_snapshot_and_research():
    payload = build_audit_artifacts(trace_id="trace-1", snapshot=None, research_audit=None)

    assert payload == {
        "evidence_packets": [],
        "facts_gate": {
            "passed": False,
            "severity": "hard_fail",
                "missing_execution_facts": ["index", "mark", "order_book"],
                "blocked_action_classes": ["opening", "trigger", "flip"],
                "reasons": [
                    "index: missing",
                    "mark: missing",
                    "order_book: missing",
                    "active_event_status: missing",
                ],
                "missing_auxiliary_facts": ["funding", "liquidation", "open_interest"],
                "missing_event_facts": ["active_event_status"],
                "missing_macro_facts": [],
                "confidence_cap": 0.55,
                "confidence_cap_reasons": [
                    "facts_gate:derivatives_facts_missing",
                    "facts_gate:event_status_stale",
                ],
            "conflicting_execution_facts": [],
            "fallback_used": False,
            "fallback_source_types": [],
        },
        "harness_validation": {"passed": True, "severity": "ok", "violations": []},
        "agent_contributions": [],
    }


def test_orchestration_inputs_use_artifacts_package_not_legacy_root_wrappers():
    source = Path("src/crypto_manual_alert/artifacts/orchestration_inputs.py").read_text(encoding="utf-8")

    assert "from crypto_manual_alert.artifacts.contributions import" in source
    assert "from crypto_manual_alert.artifacts.evidence import" in source
    assert "from crypto_manual_alert.contributions import" not in source
    assert "from crypto_manual_alert.evidence import" not in source
