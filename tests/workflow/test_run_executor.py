from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Any

from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.agent_swarm.workers import (
    DataQualityLocalWorker,
    MarketSentimentLocalWorker,
    RootCauseLocalWorker,
)
from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.domain import DecisionPlan, MarketSnapshot, RiskVerdict
from crypto_manual_alert.eval.case_builder import EvalCaseBuilder
from crypto_manual_alert.eval.release_gate import build_release_gate_summary
from crypto_manual_alert.eval.replay import ReplayRunner
from crypto_manual_alert.eval.schema import EvalScore
from crypto_manual_alert.eval.store import EvalStore
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.research_pipeline import FixtureSearchAdapter
from crypto_manual_alert.workflow.executor import RunExecutor
from crypto_manual_alert.workflow.results import DecisionStepResult
from crypto_manual_alert.workflow.legacy_plan_runner import PlanRunner


class RecordingLegacyAdapter:
    """测试用 legacy adapter，记录 RunExecutor 是否传入完整 context。"""

    def __init__(self, config, journal):  # noqa: ANN001 - 测试替身只关心调用契约。
        self.config = config
        self.journal = journal
        self.received_contexts = []

    def run(self, context):
        self.received_contexts.append(context)
        now = datetime.now(timezone.utc)
        return DecisionStepResult(
            trace_id="trace-from-recording-adapter",
            plan=DecisionPlan(
                plan_id="plan-from-adapter",
                instrument=context.request.symbol,
                main_action="no trade",
                horizon=context.request.horizon or "unknown",
                manual_execution_required=True,
                generated_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
            verdict=RiskVerdict(allowed=False, reasons=["adapter fixture"]),
        )


class ExplicitTraceAdapter:
    def __init__(self, config, journal):  # noqa: ANN001 - test adapter keeps constructor shape.
        self.config = config
        self.journal = journal

    def run(self, context):
        now = datetime.now(timezone.utc)
        return DecisionStepResult(
            trace_id="trace-from-explicit-adapter",
            plan=DecisionPlan(
                plan_id="explicit-trace-plan",
                instrument=context.request.symbol,
                main_action="no trade",
                horizon=context.request.horizon or "unknown",
                manual_execution_required=True,
                generated_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
            verdict=RiskVerdict(allowed=False, reasons=["adapter fixture"]),
        )


class EmptyTraceAdapter:
    def __init__(self, config, journal):  # noqa: ANN001 - test adapter keeps constructor shape.
        self.config = config
        self.journal = journal

    def run(self, context):
        now = datetime.now(timezone.utc)
        return DecisionStepResult(
            trace_id="",
            plan=DecisionPlan(
                plan_id="empty-trace-plan",
                instrument=context.request.symbol,
                main_action="no trade",
                horizon=context.request.horizon or "unknown",
                manual_execution_required=True,
                generated_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
            verdict=RiskVerdict(allowed=False, reasons=["adapter fixture"]),
        )


class ResearchFixtureLegacyAdapter:
    """Run the real legacy runner with controlled offline research evidence."""

    def __init__(self, config, journal):  # noqa: ANN001 - test adapter keeps the production constructor shape.
        research_config = replace(config.research, enabled=True, search_provider="fixture")
        self.config = replace(config, research=research_config)
        self.journal = journal
        self.search_adapter = FixtureSearchAdapter(
            {
                "eth_derivatives_context": [
                    {
                        "title": "Funding turns hot",
                        "url": "https://example.test/funding",
                        "snippet": "Funding and leverage show crowded longs.",
                    }
                ]
            }
        )

    def run(self, context):
        runner = PlanRunner(
            self.config,
            self.journal,
            market_provider=TimeoutMarketProvider(),
            search_adapter=self.search_adapter,
        )
        return runner.run_once(context.symbol, run_context=context)


class TimeoutMarketProvider:
    """Market provider that forces research fallback without using the network."""

    def fetch_snapshot(self, symbol):
        return MarketSnapshot(
            symbol=symbol,
            fetched_at=datetime.now(timezone.utc),
            points={},
            unavailable=["mark: ConnectTimeout", "order_book: ConnectTimeout"],
        )


def test_run_executor_creates_context_before_calling_legacy_adapter(tmp_path):
    """RunExecutor must create DecisionRunContext before calling the legacy adapter."""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    adapter = RecordingLegacyAdapter(config, journal)
    executor = RunExecutor(config=config, journal=journal, legacy_adapter_factory=lambda _config, _journal: adapter)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))

    assert adapter.received_contexts
    context = adapter.received_contexts[0]
    assert context.request.symbol == "ETH-USDT-SWAP"
    assert context.request.query_text == "评估 ETH"
    assert context.request.horizon == "6h"
    assert context.side_effect_policy.allow_production_journal_write is True
    assert result.context["run_id"] == context.run_id
    assert result.context["symbol"] == "ETH-USDT-SWAP"
    assert result.plan["instrument"] == "ETH-USDT-SWAP"
    assert result.plan["main_action"] == "no trade"
    assert result.verdict["allowed"] is False


def test_run_executor_uses_adapter_trace_id_instead_of_recent_trace_lookup(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    journal.append_trace(
        trace_id="wrong-recent-trace",
        created_at="2026-07-04T00:00:00+00:00",
        run_type="manual",
        symbol="BTC-USDT-SWAP",
        horizon=None,
        status="running",
        metadata={},
    )
    executor = RunExecutor(config=config, journal=journal, legacy_adapter_factory=ExplicitTraceAdapter)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="trace binding", horizon="6h"))

    assert result.trace_id == "trace-from-explicit-adapter"


def test_run_executor_rejects_empty_adapter_trace_id(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal, legacy_adapter_factory=EmptyTraceAdapter)

    try:
        executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="trace binding", horizon="6h"))
    except ValueError as exc:
        assert "trace_id" in str(exc)
    else:
        raise AssertionError("RunExecutor must reject decision steps without an explicit trace_id")


def test_run_executor_still_supports_existing_manual_run_contract(tmp_path):
    """This entry boundary must keep the existing manual run contract stable."""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))

    assert result.trace_id
    assert result.context["symbol"] == "ETH-USDT-SWAP"
    assert result.plan["instrument"] == "ETH-USDT-SWAP"
    assert result.plan["main_action"] == "trigger long"
    assert result.verdict["allowed"] is False
    assert any(
        hit["rule_id"] == "production_control.candidate.action_not_allowed"
        for hit in result.verdict["rule_hits"]
    )
    assert journal.list_traces(limit=1)[0]["trace_id"] == result.trace_id


def test_run_executor_persists_context_in_legacy_plan_payload(tmp_path):
    """入口 context 必须落到可审计 payload，后续替换 legacy 链路才有回放锚点。"""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(
        DecisionRequest(
            run_type="scheduled",
            symbol="ETH-USDT-SWAP",
            query_text="定时评估 ETH",
            horizon="6h",
            session_id="session-ctx",
            position={"side": "flat"},
            risk_mode="normal",
        )
    )

    payload = journal.get_plan_run_payload(result.plan["plan_id"])
    detail = journal.get_trace_detail(result.trace_id)

    assert payload is not None
    assert detail is not None
    assert payload["run_context"]["run_id"] == result.context["run_id"]
    assert payload["run_context"]["run_type"] == "scheduled"
    assert payload["run_context"]["query_text"] == "定时评估 ETH"
    assert payload["run_context"]["horizon"] == "6h"
    assert payload["run_context"]["session_id"] == "session-ctx"
    assert payload["run_context"]["position"] == {"side": "flat"}
    assert payload["run_context"]["risk_mode"] == "normal"
    assert detail["trace"]["run_type"] == "scheduled"
    assert detail["trace"]["horizon"] == "6h"
    assert detail["trace"]["metadata"]["run_context"]["run_id"] == result.context["run_id"]


def test_run_executor_populates_context_artifact_store_from_real_pipeline(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))

    artifacts = result.context["artifacts"]
    assert artifacts["evidence_count"] == 7
    assert artifacts["contribution_count"] == 7
    assert artifacts["has_lead_plan"] is True
    assert artifacts["has_decision_input"] is True
    assert artifacts["gate_result_names"] == [
        "candidate_final_decision",
        "decision_input_candidate",
        "facts_gate",
        "final_decision_switch_readiness",
        "gate_candidate",
        "lead_synthesis_artifact",
        "plan_semantic_candidate",
        "pre_final_bundle",
        "production_control_gate",
        "replayable_input_candidate",
    ]
    assert artifacts["reserved_sections"] == []
    assert len(artifacts["evidence_refs"]) == 7
    assert {ref["agent_name"] for ref in artifacts["contribution_refs"]} == {
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
    assert artifacts["lead_plan_ref"]["plan_id"].startswith("shadow:")
    assert artifacts["decision_input_ref"]["input_ref"].endswith(":pre_final_decision_input")
    assert artifacts["gate_result_refs"]["decision_input_candidate"]["input_ref"].endswith(
        ":decision_input_candidate"
    )
    assert artifacts["gate_result_refs"]["candidate_final_decision"]["decision_effect"] == "none"
    assert artifacts["gate_result_refs"]["candidate_final_decision"]["production_final_input"] is False
    assert artifacts["gate_result_refs"]["lead_synthesis_artifact"]["artifact_ref"] == "candidate:lead_synthesis"
    pre_final_bundle_ref = artifacts["gate_result_refs"]["pre_final_bundle"]
    assert pre_final_bundle_ref["artifact_ref"].endswith(":pre_final_bundle")
    assert pre_final_bundle_ref["decision_effect"] == "none"
    assert len(pre_final_bundle_ref["artifact_hash"]) == 64
    assert artifacts["gate_result_refs"]["replayable_input_candidate"]["input_ref"].endswith(
        ":replayable_input_candidate"
    )
    serialized_artifacts = json.dumps(artifacts, ensure_ascii=False)
    assert "raw_decision" not in serialized_artifacts
    assert "raw_payload" not in serialized_artifacts
    assert "snippet" not in serialized_artifacts.lower()


def test_run_executor_full_legacy_chain_feeds_candidate_replay_and_release_gate(tmp_path):
    """Full legacy entry path must produce replayable no-side-effect swarm audit."""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])

    assert payload is not None
    assert payload["final_input_selection"] == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "decision_effect": "production_final_input",
        "readiness_ready": False,
    }
    assert payload["legacy_prompt_lifecycle"] == {
        "status": "legacy_primary_until_switch_review",
        "selected_as_final_input": True,
        "allowed_uses": [
            "production_primary_until_switch_review",
            "replay_baseline",
            "legacy_comparison",
        ],
        "replacement_target": "decision_input",
    }
    assert payload["shadow_swarm_audit"]["decision_effect"] == "none"
    assert payload["pre_final_decision_input"]["decision_effect"] == "none"
    assert payload["audit_only"]["decision_effect"] == "none"
    assert payload["audit_only"]["production_final_input"] is False
    assert payload["audit_only"]["notification_input"] is False
    assert payload["decision_input_candidate"]["decision_effect"] == "none"
    assert payload["replayable_input_candidate"]["decision_effect"] == "none"
    assert any(
        hit["rule_id"] == "production_control.worker_hard_block"
        for hit in payload["production_control_gate"]["rule_hits"]
    )

    badcase_id = journal.record_badcase(
        trace_id=result.trace_id,
        plan_id=result.plan["plan_id"],
        category="grounding_error",
        severity="high",
        summary="full runner candidate replay seed",
        expected_behavior="candidate audit remains no-side-effect and blocks unsafe executable action",
        actual_behavior="legacy chain produced candidate audit",
        eval_dataset_name="failure_cases",
        evidence_refs=["plan_run.audit_only", "plan_run.run_context"],
    )
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    stored_artifacts = store.get_candidate_artifacts(case.case_id)
    before_eval_replay = _prod_counts(journal.path)

    replay_output = ReplayRunner(store).replay(case, mode="candidate_decision")
    release_gate = build_release_gate_summary(
        scores=[_passing_eval_score(case)],
        replay_outputs={case.case_id: replay_output},
        cases=[case],
    )

    assert _prod_counts(journal.path) == before_eval_replay
    candidate_audit = case.input_summary["candidate_audit"]
    assert candidate_audit["decision_input_candidate"]["decision_effect"] == "none"
    assert candidate_audit["replayable_input_candidate"]["decision_effect"] == "none"
    assert candidate_audit["replayable_input_candidate"]["coverage"]["worker_artifact_count"] == 7
    assert candidate_audit["replayable_input_candidate"]["coverage"]["has_version_lock"] is True
    assert candidate_audit["replayable_input_candidate"]["coverage"]["has_telemetry_refs"] is True
    assert candidate_audit["replayable_input_candidate"]["coverage"]["has_evidence_snapshot_refs"] is True
    assert candidate_audit["replayable_input_candidate"]["coverage"]["has_memory_snapshot_refs"] is True
    assert candidate_audit["replayable_input_candidate"]["coverage"]["has_span_tree_refs"] is True
    assert candidate_audit["replayable_input_candidate"]["coverage"]["span_tree_parent_complete"] is True
    assert candidate_audit["replayable_input_candidate"]["coverage"]["span_tree_missing_parent_count"] == 0
    version_lock = candidate_audit["replayable_input_candidate"]["artifact_refs"]["version_lock"]
    assert version_lock["config_hash"].startswith("sha256:")
    assert version_lock["skill_hashes"]["crypto-macro-decision"].startswith("sha256:")
    assert version_lock["prompt_hashes"]["legacy_final_prompt"].startswith("sha256:")
    assert version_lock["model"] == "fixture"
    assert version_lock["rule_hashes"]["risk_gate"].startswith("sha256:")
    assert version_lock["redaction_policy_hash"].startswith("sha256:")
    telemetry_refs = candidate_audit["replayable_input_candidate"]["artifact_refs"]["telemetry_refs"]
    assert telemetry_refs["telemetry_ref"].endswith(":telemetry")
    assert telemetry_refs["telemetry_hash"].startswith("sha256:")
    assert telemetry_refs["span_count"] >= 1
    assert telemetry_refs["llm_interaction_count"] >= 0
    assert telemetry_refs["total_duration_ms"] is not None
    assert telemetry_refs["span_refs"]
    assert isinstance(telemetry_refs["llm_interaction_refs"], list)
    assert "request_json" not in str(telemetry_refs)
    assert "response_json" not in str(telemetry_refs)
    evidence_refs = candidate_audit["replayable_input_candidate"]["artifact_refs"]["evidence_snapshot_refs"]
    assert evidence_refs["evidence_snapshot_ref"].endswith(":evidence_snapshot")
    assert evidence_refs["evidence_snapshot_hash"].startswith("sha256:")
    assert evidence_refs["facts_gate_hash"].startswith("sha256:")
    assert evidence_refs["evidence_count"] >= 1
    assert evidence_refs["evidence_refs"]
    assert "value" not in str(evidence_refs)
    assert "claims" not in str(evidence_refs)
    memory_refs = candidate_audit["replayable_input_candidate"]["artifact_refs"]["memory_snapshot_refs"]
    assert memory_refs["memory_snapshot_ref"].startswith("memory:")
    assert memory_refs["memory_snapshot_hash"].startswith("sha256:")
    assert memory_refs["allowed_fields"] == {}
    assert memory_refs["allowed_field_names"] == []
    assert memory_refs["recent_turn_count"] == 0
    assert "messages" not in str(memory_refs)
    span_tree_refs = candidate_audit["replayable_input_candidate"]["artifact_refs"]["span_tree_refs"]
    assert span_tree_refs["span_tree_ref"].endswith(":span_tree")
    assert span_tree_refs["span_tree_hash"].startswith("sha256:")
    assert span_tree_refs["span_count"] >= 1
    assert span_tree_refs["parent_complete"] is True
    assert span_tree_refs["missing_parent_span_ids"] == []
    assert span_tree_refs["span_refs"]
    assert "input_summary" not in str(span_tree_refs)
    assert "output_summary" not in str(span_tree_refs)
    context_gate_refs = candidate_audit["context_artifacts"]["gate_result_refs"]
    for gate_name, artifact_type in {
        "decision_input_candidate": "decision_input_candidate",
        "lead_synthesis_artifact": "lead_synthesis",
        "gate_candidate": "gate_candidate",
        "plan_semantic_candidate": "plan_semantic_candidate",
        "final_decision_switch_readiness": "final_decision_switch_readiness",
    }.items():
        assert context_gate_refs[gate_name]["artifact_hash"] == stored_artifacts[artifact_type]["artifact_hash"]
    assert {
        key: context_gate_refs["replayable_input_candidate"][key]
        for key in ("input_ref", "input_hash", "decision_effect")
    } == {
        key: stored_artifacts["replayable_input_candidate"][key]
        for key in ("input_ref", "input_hash", "decision_effect")
    }
    lead_sidecar = stored_artifacts["lead_synthesis"]
    assert lead_sidecar["counter_thesis_count"] >= 1
    assert lead_sidecar["counter_thesis_refs"]
    assert lead_sidecar["strongest_counter_thesis_ref"]["agent_name"] == "MarketSentimentAgent"
    assert lead_sidecar["conflict_count"] >= 1
    assert lead_sidecar["conflict_refs"]
    assert replay_output.status == "completed"
    assert replay_output.mode == "candidate_decision"
    assert replay_output.metadata == {
        "source": "eval.candidate_decision_replay",
        "decision_effect": "none",
    }

    candidate = replay_output.output_payload["candidate_decision"]
    assert candidate["decision_effect"] == "none"
    assert candidate["worker_artifact_count"] == 7
    assert candidate["worker_manifest_complete"] is True
    assert candidate["worker_manifest_consistency"]["passed"] is True
    assert candidate["context_artifact_consistency"]["passed"] is True
    assert candidate["artifact_snapshot_consistency"]["passed"] is True
    assert candidate["counter_conflict_coverage"]["passed"] is True
    assert candidate["complete_replay_refs"]["has_version_lock"] is True
    assert candidate["complete_replay_refs"]["has_telemetry_refs"] is True
    assert candidate["complete_replay_refs"]["has_evidence_snapshot_refs"] is True
    assert candidate["complete_replay_refs"]["has_memory_snapshot_refs"] is True
    assert candidate["complete_replay_refs"]["has_span_tree_refs"] is True
    assert candidate["span_tree_parent_complete"] is True
    assert candidate["span_tree_missing_parent_count"] == 0
    assert "version_lock" not in candidate["complete_replay_missing_refs"]
    assert "telemetry_refs" not in candidate["complete_replay_missing_refs"]
    assert "evidence_snapshot_refs" not in candidate["complete_replay_missing_refs"]
    assert "memory_snapshot_refs" not in candidate["complete_replay_missing_refs"]
    assert "span_tree_refs" not in candidate["complete_replay_missing_refs"]
    assert candidate["counter_conflict_coverage"]["violations"] == []
    assert candidate["counter_conflict_coverage"]["counter_thesis_count"] >= 1
    assert candidate["counter_conflict_coverage"]["counter_thesis_ref_count"] >= 1
    assert candidate["worker_hard_blocks"] == [
        {
            "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
            "agent_name": "ExecutionRiskAgent",
            "reasons": ["facts_gate:execution_facts_missing"],
        }
    ]
    assert "worker_hard_block" in candidate["blocking_reasons"]

    assert release_gate["candidate_replay_available"] == 1
    assert release_gate["worker_artifact_count_min"] == 7
    assert "worker_hard_block" in release_gate["blocking_reasons"]
    assert release_gate["hard_gate_results"]["counter_conflict_coverage"] == {
        "passed": True,
        "blocking_reasons": [],
        "violations": [],
    }
    assert release_gate["hard_gate_results"]["worker_hard_blocks"] == {
        "passed": False,
        "blocking_reasons": ["worker_hard_block"],
        "worker_hard_blocks": [
            {
                "case_id": case.case_id,
                "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
                "agent_name": "ExecutionRiskAgent",
                "reasons": ["facts_gate:execution_facts_missing"],
            }
        ],
    }
    assert release_gate["decision_effect"] == "none"
    assert release_gate["promotion_approved"] is False
    assert release_gate["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_run_executor_passes_pre_final_decision_input_to_final_step_boundary(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    captured: dict[str, Any] = {}

    class FinalStepResult:
        raw_decision = json.dumps(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "no trade",
                "horizon": "6h",
                "manual_execution_required": True,
                "expires_in_seconds": 90,
            }
        )
        final_input_selection = {
            "mode": "legacy_prompt",
            "source_ref": "legacy_prompt_packet",
            "decision_effect": "production_final_input",
            "readiness_ready": False,
        }

        @property
        def output_summary(self):
            return {"raw_decision_chars": len(self.raw_decision)}

    def fake_final_step(**kwargs):
        captured.update(kwargs)
        return FinalStepResult()

    monkeypatch.setattr(
        "crypto_manual_alert.workflow.legacy_decision_workflow.run_final_decision_step",
        fake_final_step,
    )
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])

    assert captured["final_input_mode"] == "legacy_prompt"
    assert captured["decision_input_candidate"]["input_ref"].endswith(":pre_final_decision_input")
    assert captured["decision_input_candidate"]["decision_effect"] == "none"
    switch_readiness = captured["switch_readiness"]
    assert switch_readiness["ready"] is False
    assert switch_readiness["stage"] == "pre_final"
    assert switch_readiness["decision_effect"] == "none"
    assert switch_readiness["blocking_reasons"] == [
        "candidate_audit_not_built_before_legacy_final",
        "pre_final_decision_input_invalid",
        "pre_final_input_gate_failed",
    ]
    assert switch_readiness["missing_post_final_gates"] == [
        "decision_input_candidate",
        "replayable_input_candidate",
        "gate_candidate",
        "plan_semantic_candidate",
        "production_control_gate",
    ]
    assert switch_readiness["pre_final_checks"] == {
        "has_pre_final_decision_input": True,
        "pre_final_validation_passed": False,
        "pre_final_input_gate_passed": False,
    }
    assert switch_readiness["input_gate"]["passed"] is False
    assert switch_readiness["input_ref"] == captured["decision_input_candidate"]["input_ref"]
    assert switch_readiness["input_hash"] == captured["decision_input_candidate"]["input_hash"]
    assert payload["final_input_selection"]["mode"] == "legacy_prompt"
    assert payload["pre_final_decision_input"]["input_ref"] == captured["decision_input_candidate"]["input_ref"]


def test_run_executor_falls_back_to_legacy_when_decision_input_mode_is_approved_but_runtime_not_ready(tmp_path):
    review_path = tmp_path / "switch-review.json"
    review_path.write_text(_final_input_switch_review_json(), encoding="utf-8")
    config_path = tmp_path / "decision-input-config.yaml"
    config_path.write_text(
        f"""
decision:
  final_input_mode: decision_input
  final_input_mode_switch_review_path: "{review_path.as_posix()}"
""",
        encoding="utf-8",
    )
    config = load_config("config/default.yaml", config_path)
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])

    selection = payload["final_input_selection"]
    assert selection["mode"] == "legacy_prompt"
    assert selection["source_ref"] == "legacy_prompt_packet"
    assert selection["fallback_from_mode"] == "decision_input"
    assert selection["fallback_reason"] == "decision_input_not_ready"
    assert selection["candidate_input_ref"] == payload["pre_final_decision_input"]["input_ref"]
    assert selection["candidate_input_hash"] == payload["pre_final_decision_input"]["input_hash"]
    assert "pre_final_input_gate_failed" in selection["fallback_blocking_reasons"]
    assert payload["legacy_prompt_lifecycle"] == {
        "status": "decision_input_fallback",
        "selected_as_final_input": True,
        "allowed_uses": ["decision_input_fallback", "replay_baseline", "legacy_comparison"],
        "replacement_target": "decision_input",
        "fallback_reason": "decision_input_not_ready",
        "fallback_blocking_reasons": selection["fallback_blocking_reasons"],
    }


def test_run_executor_blocks_executable_action_when_required_shadow_worker_fails(tmp_path, monkeypatch):
    """Required worker failure must survive the full runner and release readback path."""

    def fail_root_cause(self, subtask, input_view):  # noqa: ANN001 - test patch mirrors worker signature.
        raise RuntimeError("required root-cause worker failed")

    monkeypatch.setattr(RootCauseLocalWorker, "run", fail_root_cause)
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])
    assert payload is not None

    assert "RootCauseAgent" in payload["shadow_swarm_audit"]["failed_workers"]
    root_result = _worker_result(payload, "RootCauseAgent")
    assert root_result["status"] == "failed"
    assert root_result["required"] is True
    assert root_result["failure_policy_applied"] == "soft_downgrade"
    assert root_result["agent_run_result"]["error"]["type"] == "RuntimeError"
    dropped = payload["decision_input_candidate"]["lead_synthesis"]["dropped_contributions"]
    assert any(item["agent_name"] == "RootCauseAgent" and item["required"] is True for item in dropped)
    assert any(
        violation["rule_id"] == "decision_input.required_worker_missing_or_failed"
        for violation in payload["decision_input_candidate"]["validation"]["violations"]
    )
    assert any(
        hit["rule_id"] == "production_control.required_worker_missing_or_failed"
        for hit in payload["production_control_gate"]["rule_hits"]
    )
    assert any(
        hit["rule_id"] == "production_control.required_worker_missing_or_failed"
        for hit in result.verdict["rule_hits"]
    )

    case, _stored_artifacts, replay_output, release_gate = _candidate_replay_readback(
        tmp_path,
        journal=journal,
        result=result,
        summary="required worker failure full runner readback",
    )
    candidate = replay_output.output_payload["candidate_decision"]
    assert candidate["worker_manifest_consistency"]["passed"] is True
    assert "required_worker_missing_or_failed" in candidate["blocking_reasons"]
    assert release_gate["decision_effect"] == "none"
    assert "required_worker_missing_or_failed" in release_gate["blocking_reasons"]
    assert release_gate["hard_gate_results"]["candidate_replay"]["passed"] is True
    assert release_gate["hard_gate_results"]["worker_artifact_coverage"]["observed_min"] == 7
    assert case.case_id


def test_run_executor_soft_downgrades_optional_shadow_worker_failure(tmp_path, monkeypatch):
    """Optional worker failures should be visible without becoming required-worker hard blocks."""

    from crypto_manual_alert.lead.agent import LeadAgent as CanonicalLeadAgent
    import crypto_manual_alert.orchestration.shadow_audit as shadow_audit

    class OptionalMarketSentimentLeadAgent:
        def __init__(self, policy):
            self._inner = CanonicalLeadAgent(policy=policy)

        def plan_tasks(self, **kwargs):
            plan = self._inner.plan_tasks(**kwargs)
            tasks = tuple(
                replace(task, required=False)
                if task.agent_name == "MarketSentimentAgent"
                else task
                for task in plan.tasks
            )
            return replace(plan, tasks=tasks)

        def synthesize(self, lead_plan, *, agent_contributions):
            return self._inner.synthesize(lead_plan, agent_contributions=agent_contributions)

    def fail_market_sentiment(self, subtask, input_view):  # noqa: ANN001 - test patch mirrors worker signature.
        raise RuntimeError("optional market sentiment worker failed")

    monkeypatch.setattr(shadow_audit, "LeadAgent", OptionalMarketSentimentLeadAgent)
    monkeypatch.setattr(MarketSentimentLocalWorker, "run", fail_market_sentiment)
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])
    assert payload is not None

    market_task = _lead_plan_task(payload, "MarketSentimentAgent")
    market_result = _worker_result(payload, "MarketSentimentAgent")
    assert market_task["required"] is False
    assert market_result["status"] == "failed"
    assert market_result["required"] is False
    assert market_result["failure_policy_applied"] == "soft_downgrade"
    assert payload["shadow_swarm_audit"]["harness_validation"]["passed"] is True
    dropped = payload["decision_input_candidate"]["lead_synthesis"]["dropped_contributions"]
    assert any(item["agent_name"] == "MarketSentimentAgent" and item["required"] is False for item in dropped)
    assert not any(
        violation["rule_id"] == "decision_input.required_worker_missing_or_failed"
        for violation in payload["decision_input_candidate"]["validation"]["violations"]
    )
    production_rule_ids = {hit["rule_id"] for hit in payload["production_control_gate"]["rule_hits"]}
    assert "production_control.required_worker_missing_or_failed" not in production_rule_ids
    assert "production_control.shadow_swarm_harness_failed" not in production_rule_ids

    _case, _stored_artifacts, replay_output, release_gate = _candidate_replay_readback(
        tmp_path,
        journal=journal,
        result=result,
        summary="optional worker soft downgrade full runner readback",
    )
    candidate = replay_output.output_payload["candidate_decision"]
    assert candidate["worker_manifest_consistency"]["passed"] is True
    assert candidate["worker_manifest_consistency"]["advisories"] == [
        {
            "rule_id": "lead_synthesis_missing_optional_worker_drop",
            "task_id": "shadow:MarketSentimentAgent",
            "agent_name": "MarketSentimentAgent",
            "failure_policy_applied": "soft_downgrade",
        }
    ]
    assert "required_worker_missing_or_failed" not in candidate["blocking_reasons"]
    assert "required_worker_missing_or_failed" not in release_gate["blocking_reasons"]
    assert release_gate["hard_gate_results"]["worker_artifact_coverage"]["passed"] is True
    assert release_gate["hard_gate_results"]["worker_artifact_coverage"]["observed_min"] == 7


def test_run_executor_records_multi_worker_conflict_refs_without_production_effect(tmp_path, monkeypatch):
    """Multi-worker conflicts should be replayable audit refs, not hidden production actions."""

    def root_conflict(self, subtask, input_view):  # noqa: ANN001 - test patch mirrors worker signature.
        return _conflict_contribution(subtask, side="macro_catalyst")

    def data_conflict(self, subtask, input_view):  # noqa: ANN001 - test patch mirrors worker signature.
        return _conflict_contribution(subtask, side="data_quality")

    monkeypatch.setattr(RootCauseLocalWorker, "run", root_conflict)
    monkeypatch.setattr(DataQualityLocalWorker, "run", data_conflict)
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])
    assert payload is not None

    lead_conflict_refs = payload["decision_input_candidate"]["lead_synthesis"]["conflict_refs"]
    conflict_refs = [ref for ref in lead_conflict_refs if ref.get("conflict_id") == "macro-data-conflict"]
    assert len(conflict_refs) == 2
    assert {ref["sides"][0] for ref in conflict_refs} == {"macro_catalyst", "data_quality"}
    production_rule_ids = {hit["rule_id"] for hit in payload["production_control_gate"]["rule_hits"]}
    assert "production_control.worker_conflict" not in production_rule_ids

    _case, stored_artifacts, replay_output, release_gate = _candidate_replay_readback(
        tmp_path,
        journal=journal,
        result=result,
        summary="multi worker conflict readback",
    )
    sidecar_conflict_refs = [
        ref for ref in stored_artifacts["lead_synthesis"]["conflict_refs"] if ref.get("conflict_id") == "macro-data-conflict"
    ]
    assert len(sidecar_conflict_refs) == 2
    candidate = replay_output.output_payload["candidate_decision"]
    assert candidate["counter_conflict_coverage"]["passed"] is True
    assert candidate["counter_conflict_coverage"]["conflict_count"] >= 2
    assert candidate["counter_conflict_coverage"]["conflict_ref_count"] >= 2
    assert release_gate["hard_gate_results"]["counter_conflict_coverage"] == {
        "passed": True,
        "blocking_reasons": [],
        "violations": [],
    }


def test_run_executor_research_fixture_feeds_counter_thesis_into_replay_and_release_gate(tmp_path):
    """Explicit research evidence should enter worker counter readback without becoming execution facts."""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(
        config=config,
        journal=journal,
        legacy_adapter_factory=ResearchFixtureLegacyAdapter,
    )

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH 拥挤风险", horizon="6h"))
    payload = journal.get_plan_run_payload(result.plan["plan_id"])

    assert payload is not None
    assert payload["final_input_selection"]["mode"] == "legacy_prompt"
    assert payload["decision_input_candidate"]["decision_effect"] == "none"
    assert payload["facts_gate"]["severity"] == "hard_fail"
    assert any(packet["source_type"] == "search_derived" for packet in payload["evidence_packets"])
    assert any(
        hit["rule_id"] == "production_control.worker_hard_block"
        for hit in payload["production_control_gate"]["rule_hits"]
    )

    badcase_id = journal.record_badcase(
        trace_id=result.trace_id,
        plan_id=result.plan["plan_id"],
        category="counter_thesis_readback",
        severity="high",
        summary="research fixture counter thesis replay seed",
        expected_behavior="counter thesis remains audit-only and executable action stays blocked",
        actual_behavior="legacy chain produced research-backed counter audit",
        eval_dataset_name="failure_cases",
        evidence_refs=["plan_run.lead_synthesis_artifact", "plan_run.replayable_input_candidate"],
    )
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    stored_artifacts = store.get_candidate_artifacts(case.case_id)
    before_eval_replay = _prod_counts(journal.path)

    replay_output = ReplayRunner(store).replay(case, mode="candidate_decision")
    release_gate = build_release_gate_summary(
        scores=[_passing_eval_score(case)],
        replay_outputs={case.case_id: replay_output},
        cases=[case],
    )

    assert _prod_counts(journal.path) == before_eval_replay
    lead_sidecar = stored_artifacts["lead_synthesis"]
    assert lead_sidecar["counter_thesis_count"] >= 1
    assert lead_sidecar["counter_thesis_refs"]
    assert lead_sidecar["strongest_counter_thesis_ref"]["agent_name"] == "MarketSentimentAgent"
    assert lead_sidecar["conflict_count"] >= 1
    assert lead_sidecar["conflict_refs"]

    candidate = replay_output.output_payload["candidate_decision"]
    assert candidate["decision_effect"] == "none"
    assert candidate["counter_conflict_coverage"]["passed"] is True
    assert candidate["counter_conflict_coverage"]["counter_thesis_count"] >= 1
    assert candidate["counter_conflict_coverage"]["counter_thesis_ref_count"] >= 1
    assert candidate["worker_hard_blocks"] == [
        {
            "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
            "agent_name": "ExecutionRiskAgent",
            "reasons": ["facts_gate:execution_facts_missing"],
        }
    ]
    assert "worker_hard_block" in candidate["blocking_reasons"]

    assert release_gate["decision_effect"] == "none"
    assert release_gate["promotion_approved"] is False
    assert release_gate["hard_gate_results"]["counter_conflict_coverage"]["passed"] is True
    assert release_gate["hard_gate_results"]["worker_hard_blocks"]["passed"] is False


def test_run_executor_rejects_eval_and_replay_side_effect_runs(tmp_path):
    """eval/replay 不应从首版执行入口误触发生产 plan 或 Bark。"""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    adapter = RecordingLegacyAdapter(config, Journal(tmp_path / "journal.db"))
    executor = RunExecutor(
        config=config,
        journal=Journal(tmp_path / "journal.db"),
        legacy_adapter_factory=lambda _config, _journal: adapter,
    )

    for run_type in ("eval", "replay", "postmortem"):
        try:
            executor.submit(DecisionRequest(run_type=run_type, symbol="ETH-USDT-SWAP"))
        except ValueError as exc:
            assert "manual or scheduled" in str(exc)
        else:
            raise AssertionError(f"{run_type} should be rejected by the live executor")

    assert adapter.received_contexts == []


def _passing_eval_score(case) -> EvalScore:  # noqa: ANN001 - test helper accepts EvalCase-like objects.
    return EvalScore(
        score_id=f"score:{case.case_id}:fixture-pass",
        eval_run_id="eval-run",
        case_id=case.case_id,
        source_trace_id=case.source_trace_id,
        source_badcase_id=case.source_badcase_id,
        judge_name="rule.fixture",
        judge_type="rule",
        passed=True,
        severity="low",
        failure_category="none",
        reason_summary="fixture score",
        evidence_refs=[],
    )


def _candidate_replay_readback(tmp_path, *, journal: Journal, result, summary: str):  # noqa: ANN001
    badcase_id = journal.record_badcase(
        trace_id=result.trace_id,
        plan_id=result.plan["plan_id"],
        category="agent_swarm_full_runner",
        severity="high",
        summary=summary,
        expected_behavior="candidate audit remains no-side-effect and replayable",
        actual_behavior="legacy chain produced candidate audit",
        eval_dataset_name="failure_cases",
        evidence_refs=["plan_run.decision_input_candidate", "plan_run.replayable_input_candidate"],
    )
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store = EvalStore(tmp_path / "eval" / f"{badcase_id}.db")
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    stored_artifacts = store.get_candidate_artifacts(case.case_id)
    replay_output = ReplayRunner(store).replay(case, mode="candidate_decision")
    release_gate = build_release_gate_summary(
        scores=[_passing_eval_score(case)],
        replay_outputs={case.case_id: replay_output},
        cases=[case],
    )
    return case, stored_artifacts, replay_output, release_gate


def _worker_result(payload: dict[str, Any], agent_name: str) -> dict[str, Any]:
    for result in payload["shadow_swarm_audit"]["worker_results"]:
        if result["agent_name"] == agent_name:
            return result
    raise AssertionError(f"worker result not found: {agent_name}")


def _lead_plan_task(payload: dict[str, Any], agent_name: str) -> dict[str, Any]:
    for task in payload["shadow_swarm_audit"]["lead_plan"]["tasks"]:
        if task["agent_name"] == agent_name:
            return task
    raise AssertionError(f"lead plan task not found: {agent_name}")


def _conflict_contribution(subtask: SubTask, *, side: str) -> AgentContribution:
    payload = {
        "agent_name": subtask.agent_name,
        "task_id": subtask.task_id,
        "side": side,
        "conflict_id": "macro-data-conflict",
    }
    return AgentContribution(
        contribution_id=f"shadow_swarm:{subtask.task_id}",
        agent_name=subtask.agent_name,
        status="ok",
        required=subtask.required,
        summary=f"{subtask.agent_name} reports {side} conflict",
        claims=[
            {
                "claim": f"{side} view conflicts with another worker",
                "claim_type": "audit_observation",
                "side": "neutral",
                "evidence_ids": ["conflict.fixture"],
                "confidence": "medium",
            }
        ],
        constraints={"decision_effect": "none"},
        conflicts=[
            {
                "conflict_id": "macro-data-conflict",
                "summary": "macro catalyst and data quality disagree",
                "sides": [side],
                "contribution_refs": [f"shadow_swarm:{subtask.task_id}"],
            }
        ],
        missing_facts=[],
        input_ref=subtask.input_ref,
        output_hash=_test_hash(payload),
        failure_policy_applied="none",
        trace_ref=subtask.trace_ref,
        migration_stage="shadow_swarm",
    )


def _final_input_switch_review_json() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "artifact_type": "final_input_mode_switch_review",
            "artifact_ref": "eval:eval-run:final_input_mode_switch_review",
            "eval_run_id": "eval-run",
            "decision_effect": "none",
            "allowed_to_change_production_final_input": True,
            "baseline_final_input_mode": "legacy_prompt",
            "target_final_input_mode": "decision_input",
            "release_gate_status": "ready",
            "release_gate_ref": "eval:eval-run:release_gate",
            "release_gate_hash": "sha256:release-gate",
            "promotion_review_status": "config_change_review_approved",
            "config_change_review_approval_ref": "eval:eval-run:config_change_review_approval:config-owner",
            "config_change_review_approval_hash": "sha256:config-approval",
            "manual_release_decision_ref": "eval:eval-run:manual_release_decision:release-owner",
            "manual_release_decision_hash": "sha256:manual-release",
            "config_change_review_request_ref": "eval:eval-run:config_change_review_request:release-owner",
            "config_change_review_request_hash": "sha256:config-request",
            "candidate_input_ref": "trace:eval:decision_input_candidate",
            "candidate_input_hash": "sha256:decision",
            "config_hash": "sha256:config",
            "rollback_plan_ref": "eval:eval-run:rollback_plan",
            "rollback_plan_hash": "sha256:rollback",
            "rollback_target": "config:decision.final_input_mode=legacy_prompt",
            "rollback_steps": [
                "restore decision.final_input_mode=legacy_prompt",
                "rerun release gate smoke",
            ],
            "fallback_behavior": "legacy_prompt_on_candidate_failure",
            "manual_execution_required": True,
            "auto_order_enabled": False,
        }
    )


def _test_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _prod_counts(path) -> dict[str, int]:  # noqa: ANN001 - sqlite accepts PathLike.
    with sqlite3.connect(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes")
        }
