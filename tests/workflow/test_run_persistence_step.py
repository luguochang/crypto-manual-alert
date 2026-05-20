from __future__ import annotations

import json
from datetime import datetime, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.domain import DecisionPlan, NotificationResult, RiskVerdict
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.workflow.run_persistence_step import persist_run_result


def _plan() -> DecisionPlan:
    return DecisionPlan.from_payload(
        {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "no trade",
            "horizon": "6h",
            "manual_execution_required": True,
            "expires_in_seconds": 90,
            "why_not_opposite": "counter thesis",
            "invalidation": "rerun",
        },
        generated_at=datetime.now(timezone.utc),
    )


def _audit_payload() -> dict[str, object]:
    return {
        "evidence_packets": [],
        "facts_gate": {"passed": True, "severity": "ok", "blocked_action_classes": []},
        "harness_validation": {"passed": True},
        "agent_contributions": [],
    }


def _manual_run_context_summary() -> dict[str, object]:
    return {
        "run_type": "manual",
        "side_effect_policy": {
            "allow_production_journal_write": True,
            "allow_notification_intent": True,
        },
    }


def _with_notification(config, *, enabled: bool, send_failure_alerts: bool = True):
    notification = config.notification.__class__(
        **{
            **config.notification.__dict__,
            "enabled": enabled,
            "send_failure_alerts": send_failure_alerts,
        }
    )
    return config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )


class ReturningNotifier:
    def __init__(self, result: NotificationResult):
        self.result = result
        self.sent = []

    def send(self, plan, verdict):
        self.sent.append((plan.plan_id, verdict.allowed))
        return self.result


class ExplodingNotifier:
    def __init__(self):
        self.sent = 0

    def send(self, plan, verdict):
        self.sent += 1
        raise RuntimeError("push crashed")


def test_persistence_step_writes_payload_trace_and_notification_without_changing_verdict(tmp_path):
    config = _with_notification(load_config("config/default.yaml"), enabled=True)
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    verdict = RiskVerdict(allowed=True, reasons=[])
    notifier = ReturningNotifier(NotificationResult(ok=False, error="push failed"))

    result = persist_run_result(
        config=config,
        journal=journal,
        notifier=notifier,
        recorder=recorder,
        trace_id=trace_id,
        plan=_plan(),
        verdict=verdict,
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=_audit_payload(),
        run_context_summary=_manual_run_context_summary(),
        trace_metadata={"source": "unit"},
    )

    assert result.status == "allowed"
    assert result.notification_result == NotificationResult(ok=False, error="push failed")
    assert result.payload["verdict"]["allowed"] is True
    with journal.connect() as conn:
        plan_row = conn.execute("SELECT status, payload_json FROM plan_runs").fetchone()
        trace_row = conn.execute("SELECT status, final_plan_id, allowed, metadata_json FROM traces").fetchone()
        notification_row = conn.execute("SELECT ok, error FROM notifications").fetchone()
    assert plan_row["status"] == "allowed"
    assert json.loads(plan_row["payload_json"])["trace_id"] == trace_id
    assert trace_row["status"] == "allowed"
    assert trace_row["final_plan_id"] == result.plan.plan_id
    assert trace_row["allowed"] == 1
    assert json.loads(trace_row["metadata_json"]) == {"source": "unit"}
    assert notification_row["ok"] == 0
    assert notification_row["error"] == "push failed"


def test_persistence_step_records_notification_exceptions_without_changing_verdict(tmp_path):
    config = _with_notification(load_config("config/default.yaml"), enabled=True)
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    notifier = ExplodingNotifier()

    result = persist_run_result(
        config=config,
        journal=journal,
        notifier=notifier,
        recorder=recorder,
        trace_id=trace_id,
        plan=_plan(),
        verdict=RiskVerdict(allowed=False, reasons=["blocked"]),
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=_audit_payload(),
        run_context_summary=_manual_run_context_summary(),
    )

    assert result.status == "blocked"
    assert result.notification_result is not None
    assert result.notification_result.ok is False
    assert "push crashed" in str(result.notification_result.error)
    with journal.connect() as conn:
        notification_row = conn.execute("SELECT ok, error FROM notifications").fetchone()
        plan_row = conn.execute("SELECT payload_json FROM plan_runs").fetchone()
    assert notification_row["ok"] == 0
    assert "push crashed" in notification_row["error"]
    assert json.loads(plan_row["payload_json"])["verdict"]["allowed"] is False


def test_persistence_step_sends_failure_alert_only_when_enabled(tmp_path):
    base_config = load_config("config/default.yaml")
    error = {"type": "RuntimeError", "message": "model down", "traceback": "stack"}

    disabled_journal = Journal(tmp_path / "disabled.db")
    disabled_recorder = ObservabilityRecorder(disabled_journal)
    disabled_trace_id = disabled_recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    disabled_notifier = ReturningNotifier(NotificationResult(ok=True, status_code=200))
    persist_run_result(
        config=_with_notification(base_config, enabled=True, send_failure_alerts=False),
        journal=disabled_journal,
        notifier=disabled_notifier,
        recorder=disabled_recorder,
        trace_id=disabled_trace_id,
        plan=_plan(),
        verdict=RiskVerdict(allowed=False, reasons=["pipeline failed"]),
        snapshot=None,
        raw_decision=None,
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=_audit_payload(),
        run_context_summary=_manual_run_context_summary(),
        trace_metadata={},
        error=error,
    )

    enabled_journal = Journal(tmp_path / "enabled.db")
    enabled_recorder = ObservabilityRecorder(enabled_journal)
    enabled_trace_id = enabled_recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    enabled_notifier = ReturningNotifier(NotificationResult(ok=True, status_code=200))
    result = persist_run_result(
        config=_with_notification(base_config, enabled=True, send_failure_alerts=True),
        journal=enabled_journal,
        notifier=enabled_notifier,
        recorder=enabled_recorder,
        trace_id=enabled_trace_id,
        plan=_plan(),
        verdict=RiskVerdict(allowed=False, reasons=["pipeline failed"]),
        snapshot=None,
        raw_decision=None,
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=_audit_payload(),
        run_context_summary=_manual_run_context_summary(),
        trace_metadata={},
        error=error,
    )

    assert disabled_notifier.sent == []
    assert enabled_notifier.sent == [(result.plan.plan_id, False)]
    with enabled_journal.connect() as conn:
        trace_row = conn.execute("SELECT status, metadata_json FROM traces").fetchone()
        notification_row = conn.execute("SELECT ok, status_code FROM notifications").fetchone()
    assert trace_row["status"] == "blocked"
    assert json.loads(trace_row["metadata_json"])["error_type"] == "RuntimeError"
    assert notification_row["ok"] == 1
    assert notification_row["status_code"] == 200


def test_persistence_step_respects_side_effect_policy_for_direct_non_production_context(tmp_path):
    config = _with_notification(load_config("config/default.yaml"), enabled=True)
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="eval", symbol="ETH-USDT-SWAP")
    notifier = ReturningNotifier(NotificationResult(ok=True, status_code=200))

    result = persist_run_result(
        config=config,
        journal=journal,
        notifier=notifier,
        recorder=recorder,
        trace_id=trace_id,
        plan=_plan(),
        verdict=RiskVerdict(allowed=True, reasons=[]),
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=_audit_payload(),
        run_context_summary={
            "run_type": "eval",
            "side_effect_policy": {
                "allow_production_journal_write": False,
                "allow_notification_intent": False,
            },
        },
        trace_metadata={"source": "eval"},
    )

    assert result.status == "allowed"
    assert result.notification_result is None
    assert notifier.sent == []
    with journal.connect() as conn:
        plan_count = conn.execute("SELECT COUNT(*) FROM plan_runs").fetchone()[0]
        notification_count = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        journal_span = conn.execute(
            "SELECT output_summary_json FROM trace_spans WHERE span_name = 'journal.write'"
        ).fetchone()
        notification_span = conn.execute(
            "SELECT output_summary_json FROM trace_spans WHERE span_name = 'notification.send'"
        ).fetchone()
    assert plan_count == 0
    assert notification_count == 0
    assert json.loads(journal_span["output_summary_json"])["skipped"] == "side_effect_policy"
    assert notification_span is None


def test_persistence_step_defaults_to_no_side_effects_without_run_context_summary(tmp_path):
    config = _with_notification(load_config("config/default.yaml"), enabled=True)
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    notifier = ReturningNotifier(NotificationResult(ok=True, status_code=200))

    result = persist_run_result(
        config=config,
        journal=journal,
        notifier=notifier,
        recorder=recorder,
        trace_id=trace_id,
        plan=_plan(),
        verdict=RiskVerdict(allowed=True, reasons=[]),
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=_audit_payload(),
        run_context_summary=None,
        trace_metadata={"source": "direct-call"},
    )

    assert result.status == "allowed"
    assert result.notification_result is None
    assert notifier.sent == []
    with journal.connect() as conn:
        plan_count = conn.execute("SELECT COUNT(*) FROM plan_runs").fetchone()[0]
        notification_count = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        trace_row = conn.execute("SELECT status, metadata_json FROM traces").fetchone()
        journal_span = conn.execute(
            "SELECT output_summary_json FROM trace_spans WHERE span_name = 'journal.write'"
        ).fetchone()
    assert plan_count == 0
    assert notification_count == 0
    assert trace_row["status"] == "allowed"
    assert json.loads(trace_row["metadata_json"]) == {"source": "direct-call"}
    assert json.loads(journal_span["output_summary_json"])["skipped"] == "side_effect_policy_missing"
