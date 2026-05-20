from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.workflow.pre_final_orchestration import run_pre_final_orchestration
from crypto_manual_alert.research_pipeline import ResearchAudit, ResearchPlan, SearchResult


def test_pre_final_orchestration_builds_shadow_audit_pre_final_input_and_records_context(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={},
        unavailable=["mark: timeout"],
    )

    result = run_pre_final_orchestration(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=snapshot,
        research_audit=None,
        run_context=context,
    )

    assert result.audit_payload["facts_gate"]["severity"] == "hard_fail"
    assert result.shadow_swarm_audit["decision_effect"] == "none"
    assert result.shadow_swarm_audit["worker_count"] == 7
    contribution_refs = result.pre_final_decision_input["contribution_refs"]
    assert [ref["agent_name"] for ref in contribution_refs] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    for ref in contribution_refs:
        assert ref["task_id"].startswith("shadow:")
        assert ref["trace_ref"].startswith(f"{trace_id}:shadow:")
        assert ref["output_hash"].startswith("sha256:")
        assert "evidence_ids" in ref
        assert "confidence_cap_reasons" in ref
        assert "blocked_actions" in ref
        assert "hard_block" in ref
        assert "hard_block_reasons" in ref
        assert "manual_review_reminders" in ref
        assert "allowed_action_class_reduction" in ref
        assert "required_confirmations" in ref
    assert result.pre_final_decision_input["decision_effect"] == "none"
    assert result.pre_final_bundle["artifact_type"] == "pre_final_bundle"
    assert result.pre_final_bundle["decision_effect"] == "none"
    assert result.pre_final_bundle["production_final_input"] is False
    assert result.pre_final_bundle["notification_input"] is False
    assert result.pre_final_bundle["pre_final_decision_input_ref"]["input_ref"] == (
        result.pre_final_decision_input["input_ref"]
    )
    assert result.pre_final_summary == {
        "mode": "pre_final_candidate",
        "decision_effect": "none",
        "validation_passed": False,
        "bundle_ref": result.pre_final_bundle["artifact_ref"],
    }
    assert context.to_artifact_summary()["has_lead_plan"] is True
    assert context.to_artifact_summary()["has_decision_input"] is True
    assert "pre_final_bundle" in context.to_artifact_summary()["gate_result_names"]
    assert "facts_gate" in context.gate_results


def test_pre_final_orchestration_carries_local_worker_counter_and_hard_block_to_pre_final_input(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=now,
        points={
            "mark": DataPoint(name="mark", value=3500, timestamp_ms=None, source="okx_public"),
            "index": DataPoint(name="index", value=3498, timestamp_ms=None, source="okx_public"),
        },
        unavailable=["order_book: ConnectTimeout"],
    )
    research_audit = ResearchAudit(
        plan=ResearchPlan(queries=[], reason="fixture"),
        results={
            "derivatives_context": [
                SearchResult(
                    title="Funding turns hot",
                    url="https://example.test/funding",
                    snippet="Funding and leverage show crowded longs.",
                    source="fixture-search",
                )
            ]
        },
    )

    result = run_pre_final_orchestration(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=snapshot,
        research_audit=research_audit,
        run_context=context,
    )

    synthesis = result.shadow_swarm_audit["lead_synthesis"]
    pre_final = result.pre_final_decision_input
    worker_results = {
        item["agent_name"]: item["contribution"]
        for item in result.shadow_swarm_audit["worker_results"]
    }

    assert result.shadow_swarm_audit["decision_effect"] == "none"
    assert result.shadow_swarm_audit["failed_workers"] == []
    assert any("crowded" in claim.lower() for claim in synthesis["counter_thesis"])
    assert synthesis["strongest_counter_thesis_ref"]["agent_name"] == "MarketSentimentAgent"
    assert synthesis["strongest_counter_thesis_ref"]["side"] == "bearish"
    assert "execution_risk_hard_block" in synthesis["conflicts"]
    assert worker_results["ExecutionRiskAgent"]["constraints"]["hard_block"] is True
    assert worker_results["ExecutionRiskAgent"]["constraints"]["hard_block_reasons"] == [
        "facts_gate:execution_facts_missing"
    ]
    assert pre_final["decision_effect"] == "none"
    assert pre_final["lead_synthesis"]["strongest_counter_thesis_ref"]["agent_name"] == "MarketSentimentAgent"
    assert pre_final["validation"]["passed"] is False
    assert {
        violation["rule_id"] for violation in pre_final["validation"]["violations"]
    } >= {
        "decision_input.facts_gate_hard_fail",
        "decision_input.worker_hard_block",
    }
    assert context.to_artifact_summary()["has_decision_input"] is True
    rendered = __import__("json").dumps(pre_final, ensure_ascii=False).lower()
    assert "funding and leverage show crowded longs" not in rendered


def test_pre_final_orchestration_passes_config_to_shadow_worker_registry(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    received: dict[str, object] = {}

    class ShadowConfig:
        worker_mode = "llm_tool_shadow"

    class Config:
        shadow = ShadowConfig()

    def fake_shadow_audit(**kwargs):
        received["config"] = kwargs["config"]
        return {
            "mode": "shadow",
            "decision_effect": "none",
            "worker_count": 0,
            "failed_workers": [],
            "worker_results": [],
            "lead_plan": {"tasks": []},
            "harness_validation": {"passed": True},
        }

    monkeypatch.setattr(
        "crypto_manual_alert.workflow.pre_final_orchestration.run_shadow_swarm_audit",
        fake_shadow_audit,
    )

    run_pre_final_orchestration(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
        run_context=None,
        config=Config(),
    )

    assert received["config"].shadow.worker_mode == "llm_tool_shadow"


def test_pre_final_orchestration_passes_tool_executor_to_shadow_swarm(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    received: dict[str, object] = {}
    tool_executor = object()

    def fake_shadow_audit(**kwargs):
        received["tool_executor"] = kwargs["tool_executor"]
        return {
            "mode": "shadow",
            "decision_effect": "none",
            "worker_count": 0,
            "failed_workers": [],
            "worker_results": [],
            "lead_plan": {"tasks": []},
            "harness_validation": {"passed": True},
        }

    monkeypatch.setattr(
        "crypto_manual_alert.workflow.pre_final_orchestration.run_shadow_swarm_audit",
        fake_shadow_audit,
    )

    run_pre_final_orchestration(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
        run_context=None,
        tool_executor=tool_executor,
    )

    assert received["tool_executor"] is tool_executor


def test_pre_final_orchestration_builds_single_audit_payload_source(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    audit_payload = {
        "evidence_packets": [],
        "facts_gate": {
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": ["mark"],
            "blocked_action_classes": ["trigger"],
            "reasons": ["mark: missing"],
        },
        "harness_validation": {"passed": True, "severity": "ok", "violations": []},
        "agent_contributions": [],
    }
    calls = {"build_audit_artifacts": 0}
    received: dict[str, object] = {}

    def fake_build_audit_artifacts(**kwargs):
        calls["build_audit_artifacts"] += 1
        return audit_payload

    def fake_shadow_audit(**kwargs):
        received["audit_payload"] = kwargs["audit_payload"]
        return {
            "mode": "shadow",
            "decision_effect": "none",
            "worker_count": 0,
            "failed_workers": [],
            "worker_results": [],
            "lead_plan": {"tasks": []},
            "harness_validation": {"passed": True},
        }

    monkeypatch.setattr(
        "crypto_manual_alert.workflow.pre_final_orchestration.build_audit_artifacts",
        fake_build_audit_artifacts,
    )
    monkeypatch.setattr(
        "crypto_manual_alert.workflow.pre_final_orchestration.run_shadow_swarm_audit",
        fake_shadow_audit,
    )

    result = run_pre_final_orchestration(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
        run_context=None,
    )

    assert calls["build_audit_artifacts"] == 1
    assert received["audit_payload"] is audit_payload
    assert result.audit_payload is audit_payload
