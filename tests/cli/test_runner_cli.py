import json
import os
import sqlite3
import hashlib
import importlib
import importlib.util
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from crypto_manual_alert.cli import main
from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import MarketSnapshot, NotificationResult
from crypto_manual_alert.eval.errors import EvalRunError
from crypto_manual_alert.eval.outcome_store import OutcomeStore
import crypto_manual_alert.eval.cli as eval_cli
import crypto_manual_alert.cli as app_cli
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.legacy_plan_runner import PlanRunner
from crypto_manual_alert.research_pipeline import FixtureSearchAdapter
from crypto_manual_alert.orchestration.shadow_failure import failed_shadow_swarm_audit
from crypto_manual_alert.agent_swarm.shadow_runner import build_default_lead_plan
from crypto_manual_alert.lead.synthesis import build_lead_synthesis_candidate


ROOT = Path(__file__).resolve().parents[2]
LOCAL_STACK_TOOLS = ROOT / "tools" / "local_stack"


def _manual_run_context_summary() -> dict[str, object]:
    return {
        "run_type": "manual",
        "side_effect_policy": {
            "allow_production_journal_write": True,
            "allow_notification_intent": True,
        },
    }


def _load_mock_okx_server():
    path = LOCAL_STACK_TOOLS / "mock_okx_server.py"
    spec = importlib.util.spec_from_file_location("mock_okx_server_for_cli_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(LOCAL_STACK_TOOLS))
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_runner_fixture_flow(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")
    runner = PlanRunner(config, journal)

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert plan.instrument == "ETH-USDT-SWAP"
    assert plan.manual_execution_required is True
    assert verdict.allowed is False
    assert "production_control.candidate.action_not_allowed" in {
        hit.rule_id for hit in verdict.rule_hits if hit.blocking
    }
    with journal.connect() as conn:
        plan_row = conn.execute("SELECT payload_json FROM plan_runs").fetchone()
        trace_rows = conn.execute("SELECT span_name, status FROM trace_spans ORDER BY started_at").fetchall()
    payload = json.loads(plan_row["payload_json"])
    assert payload["trace_id"]
    assert any(row["span_name"] == "market.fetch" and row["status"] == "ok" for row in trace_rows)
    assert any(row["span_name"] == "decision.final" and row["status"] == "ok" for row in trace_rows)


def test_runner_persists_exact_frozen_input_sent_to_decision_engine(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    class CapturingEngine:
        def __init__(self):
            self.prompt_packet = None

        def run(self, prompt_packet):
            self.prompt_packet = json.loads(json.dumps(prompt_packet, ensure_ascii=False, default=str))
            return """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "reference_price": 3500,
  "entry_trigger": null,
  "stop_price": null,
  "target_1": null,
  "target_2": null,
  "probability": 0.51,
  "position_size_class": "none",
  "max_leverage": 0,
  "risk_pct": 0,
  "expires_in_seconds": 90,
  "why_not_opposite": "No confirmed short setup.",
  "invalidation": "Re-run after market structure changes.",
  "unavailable_data": [],
  "manual_execution_required": true
}
"""

    engine = CapturingEngine()
    runner = PlanRunner(config, journal, decision_engine=engine)

    _plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert verdict.allowed is True
    with journal.connect() as conn:
        row = conn.execute("SELECT payload_json FROM plan_runs").fetchone()
        freeze_span = conn.execute("SELECT output_summary_json FROM trace_spans WHERE span_name = 'input.freeze'").fetchone()
        shadow_spans = conn.execute(
            "SELECT input_summary_json, output_summary_json FROM trace_spans WHERE span_name = 'shadow_swarm.worker'"
        ).fetchall()
        ordered_span_names = [
            item["span_name"]
            for item in conn.execute("SELECT span_name FROM trace_spans ORDER BY started_at, span_id").fetchall()
        ]
    payload = json.loads(row["payload_json"])
    frozen = payload["frozen_input"]
    expected_hash = hashlib.sha256(
        json.dumps(engine.prompt_packet, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    assert frozen["schema_version"] == 1
    assert frozen["kind"] == "decision_prompt_packet"
    assert frozen["sha256"] == expected_hash
    assert frozen["payload"] == engine.prompt_packet
    assert payload["frozen_input_hash"] == expected_hash
    assert payload["final_input_selection"] == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "decision_effect": "production_final_input",
        "readiness_ready": False,
    }
    assert payload["evidence_packets"]
    assert {packet["source_type"] for packet in payload["evidence_packets"]} == {"fixture"}
    assert payload["facts_gate"]["passed"] is False
    assert payload["facts_gate"]["severity"] == "hard_fail"
    assert payload["harness_validation"]["passed"] is True
    assert payload["shadow_swarm_audit"]["mode"] == "shadow"
    assert payload["shadow_swarm_audit"]["decision_effect"] == "none"
    assert payload["shadow_swarm_audit"]["worker_count"] == 7
    assert payload["shadow_swarm_audit"]["failed_workers"] == []
    assert len(payload["shadow_swarm_audit"]["worker_results"]) == 7
    assert max(
        index for index, name in enumerate(ordered_span_names) if name == "shadow_swarm.worker"
    ) < ordered_span_names.index("decision.final")
    for task in payload["shadow_swarm_audit"]["lead_plan"]["tasks"]:
        assert "plan" not in task["input_view"]
        assert "verdict" not in task["input_view"]
    by_agent = {
        result["agent_name"]: result
        for result in payload["shadow_swarm_audit"]["worker_results"]
    }
    assert by_agent["LiveFactAgent"]["status"] == "ok"
    assert by_agent["DerivativesAgent"]["status"] == "ok"
    assert by_agent["MacroEventAgent"]["status"] == "ok"
    assert by_agent["RootCauseAgent"]["status"] == "ok"
    assert by_agent["MarketSentimentAgent"]["status"] == "ok"
    assert by_agent["DataQualityAgent"]["status"] == "ok"
    assert by_agent["ExecutionRiskAgent"]["status"] == "ok"
    assert set(by_agent["DataQualityAgent"]["contribution"]["missing_facts"]) >= {"index", "mark", "order_book"}
    assert payload["shadow_swarm_audit"]["harness_validation"]["passed"] is True
    assert payload["pre_final_decision_input"]["mode"] == "pre_final_candidate"
    assert payload["pre_final_decision_input"]["decision_effect"] == "none"
    assert payload["pre_final_decision_input"]["input_ref"].endswith(":pre_final_decision_input")
    assert "legacy_decision_ref" not in payload["pre_final_decision_input"]
    assert payload["pre_final_decision_input"]["lead_synthesis"]["included_contribution_ids"]
    assert payload["decision_input_candidate"]["decision_effect"] == "none"
    assert payload["decision_input_candidate"]["input_ref"].endswith(":decision_input_candidate")
    assert "trigger long" not in payload["decision_input_candidate"]["effective_allowed_actions"]
    assert "no trade" in payload["decision_input_candidate"]["effective_allowed_actions"]
    assert payload["decision_input_candidate"]["lead_synthesis"]["included_contribution_ids"]
    assert payload["replayable_input_candidate"]["decision_effect"] == "none"
    assert payload["replayable_input_candidate"]["legacy_frozen_input_hash"] == expected_hash
    assert payload["replayable_input_candidate"]["artifact_refs"]["decision_input_candidate"]["input_ref"].endswith(
        ":decision_input_candidate"
    )
    assert payload["replayable_input_candidate"]["coverage"]["worker_artifact_count"] == 7
    assert payload["gate_candidate"]["decision_effect"] == "none"
    assert payload["gate_candidate"]["passed"] is True
    assert payload["plan_semantic_candidate"]["decision_effect"] == "none"
    assert payload["plan_semantic_candidate"]["passed"] is True
    assert payload["final_decision_switch_readiness"]["decision_effect"] == "none"
    assert payload["final_decision_switch_readiness"]["required_shadow_worker_count"] == 7
    assert len(shadow_spans) == 7
    assert {
        json.loads(row["input_summary_json"])["agent_name"]
        for row in shadow_spans
    } == {
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
    assert "evidence_packets" not in frozen["payload"]
    assert "facts_gate" not in frozen["payload"]
    assert "harness_validation" not in frozen["payload"]
    assert "agent_contributions" not in frozen["payload"]
    assert "shadow_swarm_audit" not in frozen["payload"]
    assert "pre_final_decision_input" not in frozen["payload"]
    assert "decision_input_candidate" not in frozen["payload"]
    assert "replayable_input_candidate" not in frozen["payload"]
    assert "gate_candidate" not in frozen["payload"]
    assert "plan_semantic_candidate" not in frozen["payload"]
    assert "final_decision_switch_readiness" not in frozen["payload"]
    assert payload["verdict"]["rule_hits"]
    assert all(hit["blocking"] is False for hit in payload["verdict"]["rule_hits"])
    assert json.loads(freeze_span["output_summary_json"])["frozen_input_hash"] == expected_hash


def test_runner_records_failure_when_decision_engine_raises(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    class BadEngine:
        def run(self, prompt_packet):
            raise RuntimeError("model down")

    runner = PlanRunner(config, journal, decision_engine=BadEngine())

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert verdict.allowed is False
    assert plan.main_action == "no trade"
    with journal.connect() as conn:
        rows = conn.execute("SELECT status, payload_json FROM plan_runs").fetchall()
    assert rows
    assert rows[0]["status"] == "blocked"
    assert "model down" in rows[0]["payload_json"]
    payload = json.loads(rows[0]["payload_json"])
    assert payload["frozen_input_hash"]
    assert payload["frozen_input"]["payload"]["market_snapshot"]["symbol"] == "ETH-USDT-SWAP"
    assert any(hit["rule_id"] == "pipeline.decision_engine.error" for hit in payload["verdict"]["rule_hits"])


def test_runner_records_notification_failure_without_changing_verdict(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class FailingNotifier:
        def send(self, plan, verdict):
            return NotificationResult(ok=False, error="push failed")

    runner = PlanRunner(config, journal, notifier=FailingNotifier())

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert verdict.allowed is False
    with journal.connect() as conn:
        row = conn.execute("SELECT ok, error FROM notifications").fetchone()
    assert row["ok"] == 0
    assert row["error"] == "push failed"


def test_runner_direct_eval_context_respects_side_effect_policy(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class CapturingNotifier:
        def __init__(self):
            self.sent = []

        def send(self, plan, verdict):
            self.sent.append((plan.plan_id, verdict.allowed))
            return NotificationResult(ok=True, status_code=200)

    notifier = CapturingNotifier()
    run_context = DecisionRunContext.create(
        DecisionRequest(run_type="eval", symbol="ETH-USDT-SWAP", query_text="eval bypass")
    )

    plan, verdict = PlanRunner(config, journal, notifier=notifier).run_once(
        "ETH-USDT-SWAP",
        run_context=run_context,
    )

    assert plan.instrument == "ETH-USDT-SWAP"
    assert verdict.allowed is False
    assert notifier.sent == []
    with journal.connect() as conn:
        plan_count = conn.execute("SELECT COUNT(*) FROM plan_runs").fetchone()[0]
        notification_count = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        trace_count = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    assert plan_count == 0
    assert notification_count == 0
    assert trace_count == 1


def test_runner_direct_call_without_context_is_marked_legacy_and_has_no_side_effects(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    plan, verdict = PlanRunner(config, journal).run_once("ETH-USDT-SWAP")

    assert plan.instrument == "ETH-USDT-SWAP"
    assert verdict.allowed is False
    with journal.connect() as conn:
        plan_count = conn.execute("SELECT COUNT(*) FROM plan_runs").fetchone()[0]
        notification_count = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        trace_row = conn.execute("SELECT metadata_json FROM traces").fetchone()
    assert plan_count == 0
    assert notification_count == 0
    assert json.loads(trace_row["metadata_json"]) == {
        "legacy_direct_invocation": {
            "entrypoint": "PlanRunner.run_once",
            "side_effect_policy": "missing",
        }
    }


def test_runner_records_shadow_swarm_failure_without_changing_verdict(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    def failing_shadow_audit(**kwargs):
        return failed_shadow_swarm_audit(RuntimeError("shadow worker pool down"))

    monkeypatch.setattr("crypto_manual_alert.workflow.pre_final_orchestration.run_shadow_swarm_audit", failing_shadow_audit)

    runner = PlanRunner(config, journal)

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert plan.main_action == "trigger long"
    assert verdict.allowed is False
    with journal.connect() as conn:
        row = conn.execute("SELECT status, payload_json FROM plan_runs").fetchone()
    payload = json.loads(row["payload_json"])
    assert row["status"] == "blocked"
    assert payload["shadow_swarm_audit"]["mode"] == "shadow"
    assert payload["shadow_swarm_audit"]["decision_effect"] == "none"
    assert payload["shadow_swarm_audit"]["worker_count"] == 0
    assert payload["shadow_swarm_audit"]["failed_workers"] == ["shadow_swarm_audit"]
    assert payload["shadow_swarm_audit"]["worker_results"] == []
    assert [task["agent_name"] for task in payload["shadow_swarm_audit"]["lead_plan"]["tasks"]] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    assert {
        (item["agent_name"], item["reason"])
        for item in payload["shadow_swarm_audit"]["lead_synthesis"]["dropped_contributions"]
    } == {
        ("shadow_swarm_audit", "status=failed"),
        ("LiveFactAgent", "missing_required_contribution"),
        ("DerivativesAgent", "missing_required_contribution"),
        ("MacroEventAgent", "missing_required_contribution"),
        ("RootCauseAgent", "missing_required_contribution"),
        ("MarketSentimentAgent", "missing_required_contribution"),
        ("DataQualityAgent", "missing_required_contribution"),
        ("ExecutionRiskAgent", "missing_required_contribution"),
    }
    assert "shadow_swarm.audit_failed" in payload["shadow_swarm_audit"]["lead_synthesis"]["conflicts"]
    assert payload["shadow_swarm_audit"]["harness_validation"] == {
        "passed": False,
        "severity": "hard_fail",
        "violations": [
            {
                "agent_name": "shadow_swarm_audit",
                "rule_id": "shadow_swarm.audit_failed",
                "error_type": "RuntimeError",
                "error_message": "shadow worker pool down",
            }
        ],
    }
    assert "production_control.shadow_swarm_harness_failed" in {
        hit["rule_id"] for hit in payload["verdict"]["rule_hits"] if hit["blocking"]
    }


def test_runner_shadow_swarm_uses_lead_agent_planner(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")
    planned_calls = []

    class RecordingLeadAgent:
        def __init__(self, policy):
            self.policy = policy

        def plan_tasks(self, *, symbol, trace_id, base_input_view, worker_mode="local_audit"):
            planned_calls.append(
                {
                    "symbol": symbol,
                    "trace_id": trace_id,
                    "base_input_keys": sorted(base_input_view),
                    "policy_run_mode": self.policy.run_mode,
                    "worker_mode": worker_mode,
                }
            )
            return build_default_lead_plan(
                symbol=symbol,
                trace_id=trace_id,
                policy=self.policy,
                base_input_view=base_input_view,
            )

        def synthesize(self, lead_plan, *, agent_contributions):
            return build_lead_synthesis_candidate(
                agent_contributions=agent_contributions,
                required_agents=tuple(task.agent_name for task in lead_plan.tasks if task.required),
            )

    monkeypatch.setattr("crypto_manual_alert.orchestration.shadow_audit.LeadAgent", RecordingLeadAgent)

    plan, verdict = PlanRunner(config, journal).run_once(
        "ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary()
    )

    assert plan.main_action == "trigger long"
    assert verdict.allowed is False
    assert len(planned_calls) == 1
    assert planned_calls[0]["symbol"] == "ETH-USDT-SWAP"
    assert planned_calls[0]["trace_id"]
    assert planned_calls[0]["base_input_keys"] == ["evidence_packets", "facts_gate", "research", "snapshot"]
    assert planned_calls[0]["policy_run_mode"] == "shadow_audit"
    assert planned_calls[0]["worker_mode"] == "local_audit"


def test_runner_applies_production_control_gate_before_legacy_risk_gate(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    plan, verdict = PlanRunner(config, journal).run_once(
        "ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary()
    )

    assert plan.main_action == "trigger long"
    assert verdict.allowed is False
    assert {
        hit.rule_id
        for hit in verdict.rule_hits
        if hit.blocking
    } >= {
        "production_control.candidate.action_not_allowed",
    }
    with journal.connect() as conn:
        plan_row = conn.execute("SELECT status, payload_json FROM plan_runs").fetchone()
        span_names = [row["span_name"] for row in conn.execute("SELECT span_name FROM trace_spans ORDER BY started_at").fetchall()]
    payload = json.loads(plan_row["payload_json"])
    assert plan_row["status"] == "blocked"
    assert payload["production_control_gate"]["allowed"] is False
    assert payload["decision_input_candidate"]["legacy_decision_ref"]["allowed"] is False
    assert "production_control.check" in span_names
    assert span_names.index("production_control.check") < span_names.index("risk.check")


def test_runner_sends_notification_even_when_shadow_swarm_fails(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        security=config.security,
        research=config.research,
    )
    journal = Journal(tmp_path / "journal.db")

    def failing_shadow_audit(**kwargs):
        return failed_shadow_swarm_audit(RuntimeError("shadow worker pool down"))

    class CapturingNotifier:
        def __init__(self):
            self.sent = []

        def send(self, plan, verdict):
            self.sent.append((plan.main_action, verdict.allowed))
            return NotificationResult(ok=True, status_code=200)

    notifier = CapturingNotifier()
    monkeypatch.setattr("crypto_manual_alert.workflow.pre_final_orchestration.run_shadow_swarm_audit", failing_shadow_audit)

    runner = PlanRunner(config, journal, notifier=notifier)

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert plan.main_action == "trigger long"
    assert verdict.allowed is False
    assert notifier.sent == [("trigger long", False)]
    with journal.connect() as conn:
        notification_row = conn.execute("SELECT ok, status_code, error FROM notifications").fetchone()
        plan_row = conn.execute("SELECT status, payload_json FROM plan_runs").fetchone()
    assert notification_row["ok"] == 1
    assert notification_row["status_code"] == 200
    assert notification_row["error"] is None
    assert plan_row["status"] == "blocked"
    assert json.loads(plan_row["payload_json"])["shadow_swarm_audit"]["failed_workers"] == ["shadow_swarm_audit"]


def test_runner_records_decision_input_candidate_failure_without_changing_verdict_or_notification(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        security=config.security,
        research=config.research,
    )
    journal = Journal(tmp_path / "journal.db")

    def exploding_candidate_builder(**kwargs):
        raise RuntimeError("candidate build crashed")

    class CapturingNotifier:
        def __init__(self):
            self.sent = []

        def send(self, plan, verdict):
            self.sent.append((plan.main_action, verdict.allowed))
            return NotificationResult(ok=True, status_code=200)

    notifier = CapturingNotifier()
    monkeypatch.setattr(
        "crypto_manual_alert.decision.candidate_audit.build_decision_input_candidate",
        exploding_candidate_builder,
    )

    runner = PlanRunner(config, journal, notifier=notifier)

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert plan.main_action == "trigger long"
    assert verdict.allowed is False
    assert notifier.sent == [("trigger long", False)]
    with journal.connect() as conn:
        plan_row = conn.execute("SELECT status, payload_json FROM plan_runs").fetchone()
        notification_row = conn.execute("SELECT ok, status_code FROM notifications").fetchone()
    payload = json.loads(plan_row["payload_json"])
    assert plan_row["status"] == "blocked"
    assert notification_row["ok"] == 1
    assert notification_row["status_code"] == 200
    assert payload["decision_input_candidate"]["decision_effect"] == "none"
    assert payload["decision_input_candidate"]["error"] == {
        "type": "RuntimeError",
        "message": "candidate build crashed",
    }


def test_runner_shadow_swarm_does_not_change_blocked_risk_verdict(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    class OverRiskEngine:
        def run(self, prompt_packet):
            return """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "reference_price": 3500,
  "entry_trigger": 3501,
  "stop_price": 3400,
  "target_1": 3700,
  "target_2": 3900,
  "probability": 0.67,
  "position_size_class": "large",
  "max_leverage": 10,
  "risk_pct": 9,
  "expires_in_seconds": 90,
  "why_not_opposite": "Fixture blocked risk regression.",
  "invalidation": "Invalid below stop.",
  "unavailable_data": [],
  "manual_execution_required": true
}
"""

    def failing_shadow_audit(**kwargs):
        return failed_shadow_swarm_audit(RuntimeError("shadow worker pool down"))

    monkeypatch.setattr("crypto_manual_alert.workflow.pre_final_orchestration.run_shadow_swarm_audit", failing_shadow_audit)

    runner = PlanRunner(config, journal, decision_engine=OverRiskEngine())

    _plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert verdict.allowed is False
    with journal.connect() as conn:
        row = conn.execute("SELECT status, payload_json FROM plan_runs").fetchone()
    payload = json.loads(row["payload_json"])
    assert row["status"] == "blocked"
    assert payload["verdict"] == verdict.to_public_dict()
    assert {hit["rule_id"] for hit in payload["verdict"]["rule_hits"]} >= {
        "leverage.max",
        "risk_pct.max",
    }
    assert all(not hit["rule_id"].startswith("shadow_swarm") for hit in payload["verdict"]["rule_hits"])
    assert payload["shadow_swarm_audit"]["decision_effect"] == "none"


def test_runner_records_notification_exception_without_changing_verdict(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class ExplodingNotifier:
        def send(self, plan, verdict):
            raise RuntimeError("push crashed")

    runner = PlanRunner(config, journal, notifier=ExplodingNotifier())

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert verdict.allowed is False
    with journal.connect() as conn:
        row = conn.execute("SELECT ok, error FROM notifications").fetchone()
    assert row["ok"] == 0
    assert "push crashed" in row["error"]


def test_runner_sends_failure_alert_when_pipeline_fails_and_failure_alerts_enabled(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(
        **{**config.notification.__dict__, "enabled": True, "send_failure_alerts": True}
    )
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class BadEngine:
        def run(self, prompt_packet):
            raise RuntimeError("model down")

    class CapturingNotifier:
        def __init__(self):
            self.sent = []

        def send(self, plan, verdict):
            self.sent.append((plan, verdict))
            return NotificationResult(ok=True, status_code=200)

    notifier = CapturingNotifier()
    runner = PlanRunner(config, journal, decision_engine=BadEngine(), notifier=notifier)

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert verdict.allowed is False
    assert notifier.sent
    assert notifier.sent[0][0].plan_id == plan.plan_id
    with journal.connect() as conn:
        row = conn.execute("SELECT ok, status_code FROM notifications").fetchone()
    assert row["ok"] == 1
    assert row["status_code"] == 200


def test_runner_research_fallback_enriches_prompt_and_journal(tmp_path):
    config = load_config("config/default.yaml")
    research = config.research.__class__(**{**config.research.__dict__, "enabled": True, "search_provider": "fixture"})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=config.notification,
        scheduler=config.scheduler,
        security=config.security,
        research=research,
    )
    journal = Journal(tmp_path / "journal.db")

    class TimeoutMarketProvider:
        def fetch_snapshot(self, symbol):
            return MarketSnapshot(
                symbol=symbol,
                fetched_at=datetime.now(timezone.utc),
                points={},
                unavailable=["mark: ConnectTimeout", "order_book: ConnectTimeout"],
            )

    class CapturingEngine:
        def __init__(self):
            self.prompt_packet = None

        def run(self, prompt_packet):
            self.prompt_packet = prompt_packet
            return """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "reference_price": null,
  "entry_trigger": null,
  "stop_price": null,
  "target_1": null,
  "target_2": null,
  "probability": null,
  "position_size_class": "none",
  "max_leverage": 0,
  "risk_pct": 0,
  "expires_in_seconds": 90,
  "why_not_opposite": "Core exchange-native execution data remains unavailable.",
  "invalidation": "Recheck after mark and order book recover.",
  "unavailable_data": ["mark", "order_book"],
  "manual_execution_required": true
}
"""

    engine = CapturingEngine()
    adapter = FixtureSearchAdapter(
        {
            "eth_price_context": [
                {
                    "title": "ETH search context",
                    "url": "https://example.test/eth",
                    "snippet": "ETH fallback context from search.",
                }
            ]
        }
    )

    runner = PlanRunner(
        config,
        journal,
        market_provider=TimeoutMarketProvider(),
        decision_engine=engine,
        search_adapter=adapter,
    )

    plan, verdict = runner.run_once("ETH-USDT-SWAP", run_context_summary=_manual_run_context_summary())

    assert plan.main_action == "no trade"
    assert verdict.allowed is True
    assert "research" in engine.prompt_packet
    assert engine.prompt_packet["research"]["leader_summary"]
    assert "ETH fallback context from search." not in json.dumps(engine.prompt_packet, ensure_ascii=False)
    first_prompt_result = engine.prompt_packet["research"]["results"]["eth_price_context"][0]
    assert first_prompt_result["title"] == "ETH search context"
    assert first_prompt_result["url"] == "https://example.test/eth"
    assert first_prompt_result["snippet_ref"] == "research.results.eth_price_context[0].snippet_redacted"
    assert "snippet" not in first_prompt_result
    assert "web_eth_price_context" in engine.prompt_packet["market_snapshot"]["points"]
    assert "evidence_packets" not in engine.prompt_packet
    assert "facts_gate" not in engine.prompt_packet
    assert "agent_contributions" not in engine.prompt_packet
    assert "shadow_swarm_audit" not in engine.prompt_packet
    with journal.connect() as conn:
        row = conn.execute("SELECT payload_json FROM plan_runs").fetchone()
    payload = json.loads(row["payload_json"])
    assert "research" in payload
    assert payload["research"]["plan"]["queries"]
    assert payload["research"]["leader_summary"]
    assert payload["raw_decision"]
    assert payload["parsed_plan"]["main_action"] == "no trade"
    assert payload["evidence_snapshot"]["points"]["web_eth_price_context"]
    assert any(packet["source_type"] == "search_derived" for packet in payload["evidence_packets"])
    assert payload["facts_gate"]["passed"] is False
    assert payload["facts_gate"]["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert payload["harness_validation"]["passed"] is True
    assert payload["shadow_swarm_audit"]["mode"] == "shadow"
    assert payload["shadow_swarm_audit"]["decision_effect"] == "none"
    assert payload["shadow_swarm_audit"]["worker_count"] == 7
    assert {
        result["agent_name"]: result["status"]
        for result in payload["shadow_swarm_audit"]["worker_results"]
    } == {
        "LiveFactAgent": "ok",
        "DerivativesAgent": "ok",
        "MacroEventAgent": "ok",
        "RootCauseAgent": "ok",
        "MarketSentimentAgent": "ok",
        "DataQualityAgent": "ok",
        "ExecutionRiskAgent": "ok",
    }
    assert payload["shadow_swarm_audit"]["harness_validation"]["passed"] is True
    assert [item["agent_name"] for item in payload["agent_contributions"]] == [
        "bull_reviewer",
        "bear_reviewer",
        "data_quality_reviewer",
        "execution_risk_reviewer",
    ]
    assert {item["migration_stage"] for item in payload["agent_contributions"]} == {"legacy_contribution_wrapper"}


def test_cli_show_config_redacts(capsys):
    exit_code = main(["show-config"])

    assert exit_code == 0
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["trading"]["auto_order_enabled"] is False
    assert data["notification"]["bark_device_key_value"] in {"<unset>", "<redacted>"}


def test_cli_run_once_uses_workflow_executor(tmp_path, capsys, monkeypatch):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    received_requests = []

    class StubExecutor:
        def __init__(self, *, config, journal):
            self.config = config
            self.journal = journal

        def submit(self, request):
            received_requests.append(request)
            return app_cli.RunResult(
                trace_id="trace-1",
                context={"run_id": "run-1"},
                plan={
                    "plan_id": "plan-1",
                    "instrument": request.symbol,
                    "main_action": "no trade",
                    "horizon": request.horizon or "unknown",
                    "manual_execution_required": True,
                    "expires_at": "2026-06-30T00:00:00+00:00",
                    "reference_price": None,
                    "entry_trigger": None,
                    "stop_price": None,
                    "target_1": None,
                    "target_2": None,
                    "probability": None,
                },
                verdict={"allowed": False, "reasons": ["stub"], "warnings": [], "rule_hits": []},
            )

    monkeypatch.setattr(app_cli, "RunExecutor", StubExecutor)

    exit_code = main(
        [
            "--config",
            str(config_path),
            "run-once",
            "--symbol",
            "sol-usdt-swap",
            "--query",
            "  评估 SOL 还能不能追多  ",
            "--horizon",
            "6h",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert received_requests[0].run_type == "manual"
    assert received_requests[0].symbol == "SOL-USDT-SWAP"
    assert received_requests[0].query_text == "评估 SOL 还能不能追多"
    assert received_requests[0].horizon == "6h"
    assert output["trace_id"] == "trace-1"
    assert output["instrument"] == "SOL-USDT-SWAP"
    assert output["horizon"] == "6h"
    assert output["allowed"] is False
    assert output["business_summary"]["title"] == "SOL-USDT-SWAP 手动提醒计划"
    assert output["business_summary"]["notification"]["status"] == "disabled"
    assert output["notification"]["status"] == "disabled"
    assert output["result_review"]["status"] == "not_collected"


def test_cli_run_once_surfaces_projection_error_when_persisted_detail_missing(tmp_path, capsys, monkeypatch):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    cli_main_module = importlib.import_module("crypto_manual_alert.cli.main")

    class MissingDetailRepository:
        def __init__(self, journal, outcome_store=None, config=None):
            self.journal = journal
            self.outcome_store = outcome_store
            self.config = config

        def get_run_detail(self, trace_id, *, include_payloads=False):
            return None

    monkeypatch.setattr(cli_main_module, "JournalQueryRepository", MissingDetailRepository)

    exit_code = main(["--config", str(config_path), "run-once", "--symbol", "ETH-USDT-SWAP"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["ok"] is False
    assert output["error"]["code"] == "cli_projection_missing_detail"
    assert output["trace_id"]


def test_cli_run_once_distinguishes_requested_horizon_from_generated_plan_horizon(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "run-once",
            "--symbol",
            "ETH-USDT-SWAP",
            "--query",
            "评估 ETH",
            "--horizon",
            "12h",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert output["requested_horizon"] == "12h"
    assert output["plan_horizon"] == "6h"
    assert output["horizon"] == "6h"
    assert output["horizon_semantics"]["requested_horizon_drives_final_plan"] is False


def test_cli_scheduler_uses_workflow_executor(tmp_path, capsys, monkeypatch):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
scheduler:
  enabled: true
  max_iterations: 1
  interval_seconds: 0
""",
        encoding="utf-8",
    )
    received_requests = []

    class StubExecutor:
        def __init__(self, *, config, journal):
            self.config = config
            self.journal = journal

        def submit(self, request):
            received_requests.append(request)
            return app_cli.RunResult(
                trace_id="trace-1",
                context={"run_id": "run-1"},
                plan={
                    "plan_id": "plan-1",
                    "instrument": request.symbol,
                    "main_action": "no trade",
                    "horizon": request.horizon or "unknown",
                    "manual_execution_required": True,
                    "expires_at": "2026-06-30T00:00:00+00:00",
                    "reference_price": None,
                    "entry_trigger": None,
                    "stop_price": None,
                    "target_1": None,
                    "target_2": None,
                    "probability": None,
                },
                verdict={"allowed": True, "reasons": [], "warnings": [], "rule_hits": []},
            )

    monkeypatch.setattr(app_cli, "RunExecutor", StubExecutor)

    exit_code = main(["--config", str(config_path), "scheduler", "--symbol", "btc-usdt-swap"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert received_requests[0].run_type == "scheduled"
    assert received_requests[0].symbol == "BTC-USDT-SWAP"
    assert output["instrument"] == "BTC-USDT-SWAP"


def test_cli_scheduler_refuses_when_config_disabled(tmp_path, capsys, monkeypatch):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
scheduler:
  enabled: false
  max_iterations: 1
  interval_seconds: 0
""",
        encoding="utf-8",
    )
    called = False

    def fake_run_scheduler(*args, **kwargs):
        nonlocal called
        called = True

    cli_main_module = importlib.import_module("crypto_manual_alert.cli.main")
    monkeypatch.setattr(cli_main_module, "run_scheduler", fake_run_scheduler)

    exit_code = main(["--config", str(config_path), "scheduler", "--symbol", "ETH-USDT-SWAP"])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert called is False
    assert "SCHEDULER_DISABLED" in output
    assert "scheduler.enabled=false" in output


def test_cli_trace_query_and_badcase_flow(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )

    run_code = main(["--config", str(config_path), "run-once", "--symbol", "ETH-USDT-SWAP"])
    assert run_code == 3
    capsys.readouterr()

    list_code = main(["--config", str(config_path), "trace-list", "--limit", "5"])
    list_output = capsys.readouterr().out
    assert list_code == 0
    traces = json.loads(list_output)
    trace_id = traces[0]["trace_id"]
    plan_id = traces[0]["final_plan_id"]
    assert traces[0]["final_action"] == "trigger long"
    assert traces[0]["span_count"] >= 1

    show_code = main(["--config", str(config_path), "trace-show", "--trace-id", trace_id])
    show_output = capsys.readouterr().out
    assert show_code == 0
    detail = json.loads(show_output)
    assert detail["trace"]["trace_id"] == trace_id
    assert detail["plan_run"]["plan_id"] == plan_id
    assert detail["plan_run"]["business_summary"]["title"] == "ETH-USDT-SWAP 手动提醒计划"
    assert detail["notification"]["status"] == "not_recorded"
    assert detail["notification_history"] == []
    assert detail["result_review"]["status"] == "not_collected"
    assert "raw_decision" not in detail["plan_run"]
    assert detail["spans"]
    assert all("request_json" not in item for item in detail["llm_interactions"])

    badcase_code = main(
        [
            "--config",
            str(config_path),
            "record-badcase",
            "--plan-id",
            plan_id,
            "--category",
            "execution_plan_unclear",
            "--severity",
            "medium",
            "--summary",
            "用于回归评估",
            "--source",
            "developer",
            "--eval-dataset",
            "failure_cases",
        ]
    )
    assert badcase_code == 0
    capsys.readouterr()

    badcase_list_code = main(["--config", str(config_path), "badcase-list", "--limit", "5"])
    badcase_output = capsys.readouterr().out
    assert badcase_list_code == 0
    badcases = json.loads(badcase_output)
    assert badcases[0]["trace_id"] == trace_id
    assert badcases[0]["plan_id"] == plan_id
    assert badcases[0]["category"] == "execution_plan_unclear"
    assert badcases[0]["summary"] == "用于回归评估"
    assert badcases[0]["eval_dataset_name"] == "failure_cases"


def test_cli_collect_outcomes_collects_legacy_candidate_and_no_trade_baselines(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    created_at = "2026-07-06T00:00:00+00:00"
    trace_id = "trace-baseline-1"
    plan_id = "plan-baseline-1"
    journal.append_trace(
        trace_id=trace_id,
        created_at=created_at,
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        status="running",
        metadata={},
    )
    journal.finish_trace(
        trace_id=trace_id,
        ended_at="2026-07-06T00:01:00+00:00",
        status="allowed",
        final_plan_id=plan_id,
        final_action="trigger long",
        allowed=True,
        metadata={},
    )
    journal.append_plan_run(
        plan_id,
        "allowed",
        {
            "trace_id": trace_id,
            "parsed_plan": {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "probability": 0.61,
                "entry_trigger": 3500.0,
                "stop_price": 3420.0,
                "target_1": 3600.0,
                "target_2": 3720.0,
            },
            "candidate_final_decision": {
                "artifact_type": "candidate_final_decision",
                "mode": "candidate_final_sidecar",
                "decision_effect": "none",
                "production_final_input": False,
                "input_gate_passed": True,
                "input_ref": f"trace:{trace_id}:pre_final_decision_input",
                "input_hash": "sha256:candidate-input",
                "raw_candidate_decision": json.dumps(
                    {
                        "instrument": "ETH-USDT-SWAP",
                        "main_action": "trigger short",
                        "probability": 0.55,
                        "entry_trigger": 3490.0,
                        "stop_price": 3560.0,
                        "target_1": 3380.0,
                        "target_2": 3300.0,
                    },
                    ensure_ascii=False,
                ),
                "error": None,
            },
        },
    )

    collected_inputs = []

    class StubCollector:
        def __init__(self, config, outcome_store):
            self.config = config
            self.outcome_store = outcome_store
            assert outcome_store.path == data_dir / "eval" / "crypto-outcomes.db"

        def collect(self, plan):
            collected_inputs.append(plan)
            return object()

    monkeypatch.setattr("crypto_manual_alert.eval.outcome_collector.OutcomeCollector", StubCollector)

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output == {"collected": 3, "skipped": 0, "limit": 5}
    assert [item.evaluation_target for item in collected_inputs] == [
        "legacy_final",
        "swarm_candidate_final",
        "hold_no_trade",
    ]
    assert [item.decision_ref for item in collected_inputs] == [
        f"{plan_id}:legacy_final",
        f"{plan_id}:swarm_candidate_final",
        f"{plan_id}:hold_no_trade",
    ]
    assert collected_inputs[0].action == "trigger long"
    assert collected_inputs[0].entry_price == 3500.0
    assert collected_inputs[1].action == "trigger short"
    assert collected_inputs[1].stop_price == 3560.0
    assert collected_inputs[2].action == "no trade"
    assert collected_inputs[2].probability == 0.5
    assert collected_inputs[2].entry_price is None
    assert all(item.symbol == "ETH-USDT-SWAP" for item in collected_inputs)
    assert all(item.horizon_seconds == 6 * 3600 for item in collected_inputs)


def test_cli_collect_outcomes_expands_default_multi_horizon_and_uses_plan_created_at(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    trace_id = "trace-default-horizon"
    plan_id = "plan-default-horizon"
    _seed_collectible_trace(
        journal,
        trace_id=trace_id,
        plan_id=plan_id,
        horizon="6h/12h/1d/3d",
        trace_created_at="2026-07-06T00:00:00+00:00",
        plan_created_at="2026-07-06T00:10:00+00:00",
        payload={
            "trace_id": trace_id,
            "parsed_plan": _legacy_outcome_plan(),
            "candidate_final_decision": {
                "artifact_type": "candidate_final_decision",
                "mode": "candidate_final_sidecar",
                "decision_effect": "none",
                "production_final_input": False,
                "input_gate_passed": True,
                "raw_candidate_decision": json.dumps(_candidate_outcome_plan(), ensure_ascii=False),
                "error": None,
            },
        },
    )

    collected_inputs = []

    class StubCollector:
        def __init__(self, config, outcome_store):
            pass

        def collect(self, plan):
            collected_inputs.append(plan)
            return object()

    monkeypatch.setattr("crypto_manual_alert.eval.outcome_collector.OutcomeCollector", StubCollector)

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output == {"collected": 12, "skipped": 0, "limit": 5}
    assert [item.horizon_seconds for item in collected_inputs] == [
        6 * 3600,
        6 * 3600,
        6 * 3600,
        12 * 3600,
        12 * 3600,
        12 * 3600,
        24 * 3600,
        24 * 3600,
        24 * 3600,
        3 * 24 * 3600,
        3 * 24 * 3600,
        3 * 24 * 3600,
    ]
    assert {item.generated_at.isoformat() for item in collected_inputs} == {"2026-07-06T00:10:00+00:00"}


def test_cli_collect_outcomes_isolates_collector_errors_per_plan(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    _seed_collectible_trace(
        journal,
        trace_id="trace-error",
        plan_id="plan-error",
        payload={"trace_id": "trace-error", "parsed_plan": _legacy_outcome_plan()},
    )
    _seed_collectible_trace(
        journal,
        trace_id="trace-success",
        plan_id="plan-success",
        payload={"trace_id": "trace-success", "parsed_plan": _legacy_outcome_plan()},
    )

    class StubCollector:
        def __init__(self, config, outcome_store):
            pass

        def collect(self, plan):
            if plan.decision_ref.startswith("plan-error:legacy_final"):
                raise RuntimeError("OKX timeout")
            return object()

    monkeypatch.setattr("crypto_manual_alert.eval.outcome_collector.OutcomeCollector", StubCollector)

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["collected"] == 3
    assert output["skipped"] == 1
    assert output["limit"] == 5
    assert output["errors"] == [
        {
            "trace_id": "trace-error",
            "plan_id": "plan-error",
            "decision_ref": "plan-error:legacy_final",
            "error_type": "RuntimeError",
            "error_message": "OKX timeout",
        }
    ]


def test_cli_collect_outcomes_does_not_create_baseline_without_a_decision(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    journal.append_trace(
        trace_id="trace-empty-decision",
        created_at="2026-07-06T00:00:00+00:00",
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        status="ok",
        metadata={},
    )
    journal.finish_trace(
        trace_id="trace-empty-decision",
        ended_at="2026-07-06T00:01:00+00:00",
        status="ok",
        final_plan_id="plan-empty-decision",
        final_action=None,
        allowed=None,
        metadata={},
    )
    journal.append_plan_run(
        "plan-empty-decision",
        "blocked",
        {"trace_id": "trace-empty-decision", "parsed_plan": {}},
    )

    class StubCollector:
        def __init__(self, config, outcome_store):
            pass

        def collect(self, plan):
            raise AssertionError("collector must not score a trace without a decision action")

    monkeypatch.setattr("crypto_manual_alert.eval.outcome_collector.OutcomeCollector", StubCollector)

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output == {"collected": 0, "skipped": 1, "limit": 5}


def test_cli_collect_outcomes_rejects_candidate_sidecar_without_strict_audit_only_flags(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    trace_id = "trace-nonstrict-candidate"
    plan_id = "plan-nonstrict-candidate"
    _seed_collectible_trace(
        journal,
        trace_id=trace_id,
        plan_id=plan_id,
        plan_created_at="2026-07-06T00:00:00+00:00",
        payload={
            "trace_id": trace_id,
            "parsed_plan": _legacy_outcome_plan(),
            "candidate_final_decision": {
                "artifact_type": "candidate_final_decision",
                "mode": "candidate_final_sidecar",
                "decision_effect": "none",
                "input_gate_passed": True,
                "raw_candidate_decision": json.dumps(_candidate_outcome_plan(), ensure_ascii=False),
                "error": None,
            },
        },
    )

    collected_inputs = []

    class StubCollector:
        def __init__(self, config, outcome_store):
            pass

        def collect(self, plan):
            collected_inputs.append(plan)
            return object()

    monkeypatch.setattr("crypto_manual_alert.eval.outcome_collector.OutcomeCollector", StubCollector)

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output == {"collected": 2, "skipped": 0, "limit": 5}
    assert [item.evaluation_target for item in collected_inputs] == ["legacy_final", "hold_no_trade"]


def test_cli_collect_outcomes_skips_failed_or_unfinished_traces(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    _seed_collectible_trace(
        journal,
        trace_id="trace-failed",
        plan_id="plan-failed",
        trace_status="failed",
        payload={"trace_id": "trace-failed", "parsed_plan": _legacy_outcome_plan()},
    )
    journal.append_trace(
        trace_id="trace-unfinished",
        created_at="2026-07-06T00:00:00+00:00",
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        status="ok",
        metadata={},
    )
    journal.append_plan_run(
        "plan-unfinished",
        "allowed",
        {"trace_id": "trace-unfinished", "parsed_plan": _legacy_outcome_plan()},
    )

    class StubCollector:
        def __init__(self, config, outcome_store):
            pass

        def collect(self, plan):
            raise AssertionError("collector must not score failed or unfinished traces")

    monkeypatch.setattr("crypto_manual_alert.eval.outcome_collector.OutcomeCollector", StubCollector)

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output == {"collected": 0, "skipped": 2, "limit": 5}


def test_cli_collect_outcomes_direct_module_execution_uses_all_helpers(tmp_path):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    _seed_collectible_trace(
        journal,
        trace_id="trace-direct-module",
        plan_id="plan-direct-module",
        trace_status="failed",
        payload={"trace_id": "trace-direct-module", "parsed_plan": _legacy_outcome_plan()},
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "crypto_manual_alert.cli.main",
            "--config",
            str(config_path),
            "collect-outcomes",
            "--limit",
            "5",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"collected": 0, "skipped": 1, "limit": 5}


def test_cli_collect_outcomes_writes_real_outcomes_to_eval_sidecar_store(
    tmp_path,
    capsys,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    trace_id = "trace-real-store"
    plan_id = "plan-real-store"
    _seed_collectible_trace(
        journal,
        trace_id=trace_id,
        plan_id=plan_id,
        plan_created_at="2026-07-06T00:00:00+00:00",
        payload={
            "trace_id": trace_id,
            "parsed_plan": _legacy_outcome_plan(),
            "candidate_final_decision": {
                "artifact_type": "candidate_final_decision",
                "mode": "candidate_final_sidecar",
                "decision_effect": "none",
                "production_final_input": False,
                "input_gate_passed": True,
                "raw_candidate_decision": json.dumps(_candidate_outcome_plan(), ensure_ascii=False),
                "error": None,
            },
        },
    )
    candle_ts = int(datetime(2026, 7, 6, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    candle_payload = {
        "code": "0",
        "data": [[str(candle_ts), "3500", "3560", "3440", "3525", "100", "100", "1", "1"]],
    }
    monkeypatch.setattr(
        "crypto_manual_alert.eval.outcome_collector.httpx.Client",
        lambda *args, **kwargs: _FakeOkxClient(candle_payload),
    )
    before_counts = _prod_table_counts(data_dir / "crypto-alert.db")

    exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["collected"] == 3
    assert output["skipped"] == 0
    assert output["limit"] == 5
    _assert_collected_refs(
        output,
        [
            (f"{plan_id}:legacy_final", "legacy_final"),
            (f"{plan_id}:swarm_candidate_final", "swarm_candidate_final"),
            (f"{plan_id}:hold_no_trade", "hold_no_trade"),
        ],
    )
    assert _prod_table_counts(data_dir / "crypto-alert.db") == before_counts
    store = OutcomeStore(data_dir / "eval" / "crypto-outcomes.db")
    outcomes = store.list_outcomes()
    assert [item.evaluation_target for item in outcomes] == [
        "hold_no_trade",
        "legacy_final",
        "swarm_candidate_final",
    ]
    assert {item.decision_ref for item in outcomes} == {
        f"{plan_id}:legacy_final",
        f"{plan_id}:swarm_candidate_final",
        f"{plan_id}:hold_no_trade",
    }


def test_cli_collect_outcomes_reads_history_candles_from_local_mock_okx_http(
    tmp_path,
    capsys,
):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    port = _free_port()
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
market_data:
  provider: okx_public
  okx_base_url: http://127.0.0.1:{port}
  candle_bar: 1H
""",
        encoding="utf-8",
    )
    journal = Journal(data_dir / "crypto-alert.db")
    trace_id = "trace-local-okx-http"
    plan_id = "plan-local-okx-http"
    _seed_collectible_trace(
        journal,
        trace_id=trace_id,
        plan_id=plan_id,
        plan_created_at="2026-07-06T00:00:00+00:00",
        payload={"trace_id": trace_id, "parsed_plan": _legacy_outcome_plan()},
    )
    before_counts = _prod_table_counts(data_dir / "crypto-alert.db")

    mock_okx = _load_mock_okx_server()
    server = ThreadingHTTPServer(("127.0.0.1", port), mock_okx._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        exit_code = main(["--config", str(config_path), "collect-outcomes", "--limit", "5"])
        output = json.loads(capsys.readouterr().out)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert exit_code == 0
    assert output["collected"] == 2
    assert output["skipped"] == 0
    assert output["limit"] == 5
    _assert_collected_refs(
        output,
        [
            (f"{plan_id}:legacy_final", "legacy_final"),
            (f"{plan_id}:hold_no_trade", "hold_no_trade"),
        ],
    )
    assert _prod_table_counts(data_dir / "crypto-alert.db") == before_counts
    outcomes = OutcomeStore(data_dir / "eval" / "crypto-outcomes.db").list_outcomes()
    assert [item.evaluation_target for item in outcomes] == ["hold_no_trade", "legacy_final"]
    legacy = next(item for item in outcomes if item.evaluation_target == "legacy_final")
    hold = next(item for item in outcomes if item.evaluation_target == "hold_no_trade")
    assert legacy.decision_ref == f"{plan_id}:legacy_final"
    assert legacy.window.source_type == "exchange_native"
    assert legacy.window.matured is True
    assert legacy.window.can_score_execution_outcome is True
    assert legacy.can_score is True
    assert hold.decision_ref == f"{plan_id}:hold_no_trade"
    assert hold.window.source_type == "exchange_native"
    assert hold.can_score is False
    assert hold.unscored_reason == "no_trade_action"


def test_cli_eval_run_and_report_flow(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )

    assert main(["--config", str(config_path), "run-once", "--symbol", "ETH-USDT-SWAP"]) == 3
    capsys.readouterr()
    with sqlite3.connect(data_dir / "crypto-alert.db") as conn:
        conn.row_factory = sqlite3.Row
        run = conn.execute("SELECT payload_json FROM plan_runs ORDER BY created_at DESC LIMIT 1").fetchone()
    assert run is not None
    run_payload = json.loads(run["payload_json"])
    badcase_code = main(
        [
            "--config",
            str(config_path),
            "record-badcase",
            "--trace-id",
            run_payload["trace_id"],
            "--category",
            "grounding_error",
            "--severity",
            "high",
            "--summary",
            "eval cli regression",
            "--expected",
            "data gap requires no trade",
            "--actual",
            "trigger long",
            "--eval-dataset",
            "failure_cases",
        ]
    )
    assert badcase_code == 0
    capsys.readouterr()

    eval_code = main(["--config", str(config_path), "eval-run", "--dataset", "failure_cases", "--mode", "cheap"])
    eval_output = capsys.readouterr().out

    assert eval_code == 0
    eval_payload = json.loads(eval_output)
    assert eval_payload["mode"] == "cheap"
    assert eval_payload["metadata"]["report_json_ref"]
    assert (data_dir / eval_payload["metadata"]["report_json_ref"]).exists()
    assert (data_dir / eval_payload["metadata"]["report_markdown_ref"]).exists()

    report_code = main(["--config", str(config_path), "eval-report", "--eval-run-id", eval_payload["eval_run_id"]])
    report_output = capsys.readouterr().out

    assert report_code == 0
    report_payload = json.loads(report_output)
    assert report_payload["eval_run_id"] == eval_payload["eval_run_id"]
    assert report_payload["report_json_ref"] == eval_payload["metadata"]["report_json_ref"]


def test_cli_eval_run_empty_selection_returns_stable_error(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )

    exit_code = main(["--config", str(config_path), "eval-run", "--dataset", "missing", "--mode", "cheap"])
    output = capsys.readouterr().out

    assert exit_code == 2
    payload = json.loads(output)
    assert payload["error"] == "eval_no_cases"


def test_cli_eval_run_runtime_error_returns_json(tmp_path, capsys, monkeypatch):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )

    class FailingRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise EvalRunError("failed to write eval report: PermissionError")

    monkeypatch.setattr(eval_cli, "EvalRunner", FailingRunner)

    exit_code = main(["--config", str(config_path), "eval-run", "--dataset", "failure_cases", "--mode", "cheap"])
    output = capsys.readouterr().out

    assert exit_code == 1
    payload = json.loads(output)
    assert payload["error"] == "eval_run_failed"


def _seed_collectible_trace(
    journal: Journal,
    *,
    trace_id: str,
    plan_id: str,
    payload: dict[str, object],
    trace_status: str = "allowed",
    horizon: str = "6h",
    trace_created_at: str = "2026-07-06T00:00:00+00:00",
    plan_created_at: str | None = None,
) -> None:
    journal.append_trace(
        trace_id=trace_id,
        created_at=trace_created_at,
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon=horizon,
        status="running",
        metadata={},
    )
    journal.finish_trace(
        trace_id=trace_id,
        ended_at="2026-07-06T06:01:00+00:00",
        status=trace_status,
        final_plan_id=plan_id,
        final_action="trigger long",
        allowed=trace_status == "allowed",
        metadata={},
    )
    journal.append_plan_run(plan_id, trace_status if trace_status in {"allowed", "blocked"} else "failed", payload)
    if plan_created_at is not None:
        with journal.connect() as conn:
            conn.execute("UPDATE plan_runs SET created_at = ? WHERE plan_id = ?", (plan_created_at, plan_id))


def _legacy_outcome_plan() -> dict[str, object]:
    return {
        "instrument": "ETH-USDT-SWAP",
        "main_action": "trigger long",
        "probability": 0.61,
        "entry_trigger": 3500.0,
        "stop_price": 3420.0,
        "target_1": 3600.0,
        "target_2": 3720.0,
    }


def _candidate_outcome_plan() -> dict[str, object]:
    return {
        "instrument": "ETH-USDT-SWAP",
        "main_action": "trigger short",
        "probability": 0.55,
        "entry_trigger": 3490.0,
        "stop_price": 3560.0,
        "target_1": 3380.0,
        "target_2": 3300.0,
    }


def _assert_collected_refs(output: dict[str, object], expected: list[tuple[str, str]]) -> None:
    refs = output.get("collected_refs")
    assert isinstance(refs, list)
    assert [(item["decision_ref"], item["evaluation_target"]) for item in refs] == expected
    for ref in refs:
        assert ref["symbol"] == "ETH-USDT-SWAP"
        assert ref["window_name"] == "ETH-USDT-SWAP:21600s"
        collected_at = datetime.fromisoformat(str(ref["collected_at"]))
        assert collected_at.tzinfo is not None


class _FakeOkxClient:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, path, params):
        return _FakeOkxResponse(self.payload)


class _FakeOkxResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _prod_table_counts(db_path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes", "traces", "trace_spans", "llm_interactions")
        }
