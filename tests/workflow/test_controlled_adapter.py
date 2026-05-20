from __future__ import annotations

from dataclasses import replace
import sqlite3

from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.controlled_adapter import ControlledSwarmAuditAdapter
from crypto_manual_alert.workflow.executor import RunExecutor


def test_controlled_swarm_audit_adapter_persists_traceable_audit_only_run(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    context = DecisionRunContext.create(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="controlled audit", horizon="6h")
    )
    before_counts = _prod_counts(journal)

    run_result = ControlledSwarmAuditAdapter(config, journal).run(context)
    plan, verdict = run_result

    after_counts = _prod_counts(journal)
    assert after_counts["plan_runs"] == before_counts["plan_runs"] + 1
    assert after_counts["traces"] == before_counts["traces"] + 1
    assert after_counts["notifications"] == before_counts["notifications"]
    assert plan.instrument == "ETH-USDT-SWAP"
    assert plan.main_action == "no trade"
    assert verdict.allowed is False
    assert "controlled_swarm_audit_only" in verdict.reasons
    assert run_result.trace_id
    detail = journal.get_trace_detail(run_result.trace_id)
    assert detail is not None
    assert detail["trace"]["status"] == "blocked"
    assert detail["trace"]["metadata"]["execution_mode"] == "controlled_shadow"
    assert detail["trace"]["metadata"]["audit_only"] is True
    assert detail["plan_run"]["trace_id"] == run_result.trace_id
    assert detail["plan_run"]["agent_audit_view"]["available"] is True
    assert detail["plan_run"]["agent_audit_view"]["mode"] == "controlled_shadow"
    assert detail["plan_run"]["agent_audit_view"]["controlled_shadow"]["audit_only"] is True
    assert detail["plan_run"]["agent_audit_view"]["controlled_shadow"]["production_final_input"] is False
    assert detail["plan_run"]["agent_audit_view"]["controlled_shadow"]["notification_input"] is False
    assert any(span["span_name"] == "journal.write" for span in detail["spans"])
    payload = journal.get_plan_run_payload(plan.plan_id)
    assert payload is not None
    assert payload["controlled_shadow"]["audit_only"] is True
    assert payload["audit_only"]["controlled_shadow"]["audit_only"] is True
    assert payload["audit_only"]["controlled_shadow"]["production_final_input"] is False
    assert payload["audit_only"]["controlled_shadow"]["notification_input"] is False
    assert payload["audit_only"]["production_final_input"] is False
    assert payload["audit_only"]["notification_input"] is False
    artifacts = context.to_artifact_summary()
    assert artifacts["has_lead_plan"] is True
    assert artifacts["has_decision_input"] is True
    assert artifacts["contribution_count"] >= 4
    assert "lead_synthesis_artifact" in artifacts["gate_result_names"]
    assert artifacts["decision_input_ref"]["input_ref"].endswith(":pre_final_decision_input")


def test_run_executor_default_adapter_remains_legacy_plan_runner(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")

    result = RunExecutor(config=config, journal=journal).submit(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="legacy default", horizon="6h")
    )

    assert result.plan["main_action"] == "trigger long"
    assert "controlled_swarm_audit_only" not in result.verdict["reasons"]


def test_run_executor_with_controlled_adapter_is_still_blocked_audit_only(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    before_counts = _prod_counts(journal)

    result = RunExecutor(
        config=config,
        journal=journal,
        legacy_adapter_factory=ControlledSwarmAuditAdapter,
    ).submit(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="audit only", horizon="6h")
    )

    after_counts = _prod_counts(journal)
    assert after_counts["plan_runs"] == before_counts["plan_runs"] + 1
    assert after_counts["traces"] == before_counts["traces"] + 1
    assert after_counts["notifications"] == before_counts["notifications"]
    assert result.plan["main_action"] == "no trade"
    assert result.verdict["allowed"] is False
    assert "controlled_swarm_audit_only" in result.verdict["reasons"]
    assert journal.get_trace_detail(result.trace_id)["plan_run"]["agent_audit_view"]["controlled_shadow"]["audit_only"] is True
    assert result.context["artifacts"]["has_decision_input"] is True
    assert result.context["artifacts"]["gate_result_refs"]["production_control_gate"]["artifact_hash"]


def test_run_executor_can_route_to_controlled_shadow_mode_from_config(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(
        config,
        app=replace(config.app, data_dir=str(tmp_path)),
        workflow=replace(config.workflow, execution_mode="controlled_shadow"),
    )
    journal = Journal(tmp_path / "journal.db")
    before_counts = _prod_counts(journal)

    result = RunExecutor(config=config, journal=journal).submit(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="controlled route", horizon="6h")
    )

    after_counts = _prod_counts(journal)
    assert after_counts["plan_runs"] == before_counts["plan_runs"] + 1
    assert after_counts["traces"] == before_counts["traces"] + 1
    assert after_counts["notifications"] == before_counts["notifications"]
    assert result.plan["main_action"] == "no trade"
    assert result.verdict["allowed"] is False
    assert "controlled_swarm_audit_only" in result.verdict["reasons"]
    assert result.trace_id.startswith("controlled-audit-")
    detail = journal.get_trace_detail(result.trace_id)
    assert detail["plan_run"]["agent_audit_view"]["controlled_shadow"]["audit_only"] is True
    assert result.context["artifacts"]["has_lead_plan"] is True
    assert result.context["artifacts"]["has_decision_input"] is True


def test_run_executor_can_route_to_production_candidate_swarm_but_keeps_it_blocked(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(
        config,
        app=replace(config.app, data_dir=str(tmp_path)),
        workflow=replace(config.workflow, execution_mode="production_candidate_swarm"),
    )
    journal = Journal(tmp_path / "journal.db")
    before_counts = _prod_counts(journal)

    result = RunExecutor(config=config, journal=journal).submit(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="candidate swarm route", horizon="6h")
    )

    after_counts = _prod_counts(journal)
    assert after_counts["plan_runs"] == before_counts["plan_runs"] + 1
    assert after_counts["traces"] == before_counts["traces"] + 1
    assert after_counts["notifications"] == before_counts["notifications"]
    assert result.trace_id.startswith("production-candidate-swarm-")
    assert result.plan["main_action"] == "no trade"
    assert result.verdict["allowed"] is False
    assert "production_candidate_swarm_audit_only" in result.verdict["reasons"]
    detail = journal.get_trace_detail(result.trace_id)
    assert detail["trace"]["metadata"]["execution_mode"] == "production_candidate_swarm"
    audit_view = detail["plan_run"]["agent_audit_view"]
    assert audit_view["mode"] == "production_candidate_swarm"
    assert audit_view["controlled_shadow"]["audit_only"] is True
    assert audit_view["controlled_shadow"]["status"] == "blocked"
    assert audit_view["controlled_shadow"]["production_candidate"] is False
    assert audit_view["controlled_shadow"]["blocked"] is True
    assert audit_view["controlled_shadow"]["production_final_input"] is False
    assert audit_view["controlled_shadow"]["notification_input"] is False
    assert audit_view["candidate_final_comparison"]["production_control_gate"] == {
        "allowed": False,
        "reasons": ["production_candidate_swarm_audit_only"],
        "blocking_rule_ids": ["production_candidate_swarm_audit_only.blocked"],
    }
    payload = journal.get_plan_run_payload(result.plan["plan_id"])
    assert payload["candidate_final_decision"]["artifact_type"] == "candidate_final_decision"
    assert payload["candidate_final_decision"]["decision_effect"] == "none"
    assert payload["candidate_final_decision"]["production_final_input"] is False


def _prod_counts(journal: Journal) -> dict[str, int]:
    with sqlite3.connect(journal.path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "traces")
        }
