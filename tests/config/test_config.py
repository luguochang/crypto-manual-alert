import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from crypto_manual_alert.config import ConfigError, load_config


def test_default_config_disables_auto_ordering():
    config = load_config("config/default.yaml")

    assert config.trading.auto_order_enabled is False
    assert config.trading.manual_execution_required is True
    assert config.market_data.http_trust_env is False
    assert config.market_data.http_proxy == ""
    assert config.notification.bark_device_key_env == "BARK_DEVICE_KEY"
    assert config.decision.final_input_mode == "legacy_prompt"
    assert config.decision.candidate_sidecar_mode == "same_engine"
    assert config.workflow.execution_mode == "legacy_baseline"
    assert config.shadow.worker_mode == "local_audit"
    assert config.eval.release_gate.minimum_case_count == 20
    assert config.eval.release_gate.schema_valid_rate_threshold == 0.95
    assert config.eval.release_gate.required_badcase_severities == ["high", "critical"]
    assert config.eval.financial_quality.evaluation_targets == ["legacy_final", "swarm_candidate_final"]
    assert config.eval.financial_quality.minimum_scored_count == 30
    assert config.eval.financial_quality.minimum_direction_hit_rate == 0.52
    assert config.eval.financial_quality.maximum_brier_score == 0.25
    assert config.diagnostic.routes_enabled is False


def test_diagnostic_routes_can_be_enabled_by_environment(monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_ROUTES_ENABLED", "true")

    config = load_config("config/default.yaml")

    assert config.diagnostic.routes_enabled is True
    assert config.safe_dict()["diagnostic"] == {"routes_enabled": True}


def test_prod_config_uses_real_public_market_data_provider():
    config = load_config("config/default.yaml", "config/prod.yaml")

    assert config.market_data.provider == "okx_public"
    assert config.decision.candidate_sidecar_mode == "disabled"


def test_prod_config_declares_manual_only_legacy_main_path_explicitly():
    prod_overlay = yaml.safe_load(Path("config/prod.yaml").read_text(encoding="utf-8"))
    config = load_config("config/default.yaml", "config/prod.yaml")

    assert prod_overlay["trading"]["auto_order_enabled"] is False
    assert prod_overlay["trading"]["manual_execution_required"] is True
    assert prod_overlay["decision"]["final_input_mode"] == "legacy_prompt"
    assert prod_overlay["decision"]["candidate_sidecar_mode"] == "disabled"
    assert prod_overlay["workflow"]["execution_mode"] == "legacy_baseline"
    assert config.trading.auto_order_enabled is False
    assert config.trading.manual_execution_required is True
    assert config.decision.final_input_mode == "legacy_prompt"
    assert config.workflow.execution_mode == "legacy_baseline"


def test_explicit_missing_config_path_fails_fast(tmp_path):
    missing = tmp_path / "missing-prod-overlay.yaml"

    with pytest.raises(ConfigError, match="Config file does not exist"):
        load_config("config/default.yaml", missing)


def test_candidate_sidecar_mode_can_be_disabled_by_environment(monkeypatch):
    monkeypatch.setenv("CANDIDATE_SIDECAR_MODE", "disabled")

    config = load_config("config/default.yaml")

    assert config.decision.candidate_sidecar_mode == "disabled"


def test_macro_event_assertion_metadata_can_be_set_by_environment(monkeypatch):
    confirmed_at = datetime.now(timezone.utc).isoformat()
    valid_until = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    monkeypatch.setenv("MACRO_EVENT_PROVIDER", "no_active_event")
    monkeypatch.setenv("MACRO_EVENT_OPERATOR_REF", "ops:macro-desk")
    monkeypatch.setenv("MACRO_EVENT_CONFIRMED_AT", confirmed_at)
    monkeypatch.setenv("MACRO_EVENT_SOURCE_REF", "calendar:forexfactory:2026-07-09:no-high-impact")
    monkeypatch.setenv("MACRO_EVENT_ASSERTION_HORIZON", "6h")
    monkeypatch.setenv("MACRO_EVENT_VALID_UNTIL", valid_until)

    config = load_config("config/default.yaml")

    assert config.macro_event.provider == "no_active_event"
    assert config.macro_event.no_active_event_operator_ref == "ops:macro-desk"
    assert config.macro_event.no_active_event_confirmed_at == confirmed_at
    assert config.macro_event.no_active_event_source_ref == "calendar:forexfactory:2026-07-09:no-high-impact"
    assert config.macro_event.no_active_event_horizon == "6h"
    assert config.macro_event.no_active_event_valid_until == valid_until


def test_macro_event_assertion_rejects_invalid_timestamp(tmp_path):
    path = tmp_path / "bad-macro-event.yaml"
    path.write_text(
        """
macro_event:
  provider: no_active_event
  no_active_event_confirmed_at: yesterday
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="macro_event.no_active_event_confirmed_at"):
        load_config(path)


def test_macro_event_assertion_rejects_expired_valid_until(tmp_path):
    confirmed_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    valid_until = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    path = tmp_path / "expired-macro-event.yaml"
    path.write_text(
        f"""
macro_event:
  provider: no_active_event
  no_active_event_operator_ref: ops:macro-desk
  no_active_event_confirmed_at: {confirmed_at}
  no_active_event_source_ref: calendar:forexfactory:no-high-impact
  no_active_event_horizon: 6h
  no_active_event_valid_until: {valid_until}
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="macro_event.no_active_event_valid_until must be in the future"):
        load_config(path)


def test_config_rejects_unknown_candidate_sidecar_mode(tmp_path):
    path = tmp_path / "bad-sidecar.yaml"
    path.write_text(
        """
decision:
  candidate_sidecar_mode: always_on
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="candidate_sidecar_mode"):
        load_config(path)


def test_market_data_okx_base_url_can_be_overridden_for_local_stack(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_OKX_BASE_URL", "http://127.0.0.1:8012")

    config = load_config("config/default.yaml", "config/staging.yaml")

    assert config.market_data.provider == "okx_public"
    assert config.market_data.okx_base_url == "http://127.0.0.1:8012"


def test_market_data_http_trust_env_can_be_enabled_for_prod_network(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_HTTP_TRUST_ENV", "true")

    config = load_config("config/default.yaml")

    assert config.market_data.http_trust_env is True


def test_market_data_http_proxy_can_be_configured_without_leaking_from_safe_snapshot(monkeypatch):
    proxy_url = "http://proxy-user:proxy-password@127.0.0.1:8888"
    monkeypatch.setenv("MARKET_DATA_HTTP_PROXY", proxy_url)

    config = load_config("config/default.yaml")
    safe_market_data = config.safe_dict()["market_data"]

    assert config.market_data.http_proxy == proxy_url
    assert safe_market_data["http_proxy"] == "<redacted>"
    assert safe_market_data["http_proxy_set"] is True
    assert proxy_url not in json.dumps(config.safe_dict())
    assert "proxy-password" not in json.dumps(config.safe_dict())


def test_market_data_http_proxy_rejects_invalid_url(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_HTTP_PROXY", "proxy.internal:8888")

    with pytest.raises(ConfigError, match="market_data.http_proxy"):
        load_config("config/default.yaml")


def test_config_rejects_unknown_market_data_provider(tmp_path):
    path = tmp_path / "bad-market-provider.yaml"
    path.write_text(
        """
market_data:
  provider: paper_feed
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="market_data.provider"):
        load_config(path)


def test_config_rejects_auto_ordering(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
app:
  mode: MANUAL_ALERT
trading:
  auto_order_enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="auto_order_enabled"):
        load_config(path)


def test_config_rejects_command_decision_engine(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
decision:
  engine: command
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="command"):
        load_config(path)


def test_config_rejects_decision_input_final_mode_until_switch_readiness_is_promoted(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
decision:
  final_input_mode: decision_input
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="final_input_mode=decision_input"):
        load_config(path)


def test_config_rejects_decision_input_even_after_manual_release_review_artifacts(tmp_path):
    release_gate_review = {
        "status": "ready_for_config_change_review",
        "promotion_approved": False,
        "allowed_to_change_production_final_input": False,
    }
    assert release_gate_review["status"] == "ready_for_config_change_review"

    path = tmp_path / "bad.yaml"
    path.write_text(
        """
decision:
  final_input_mode: decision_input
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="final_input_mode=decision_input"):
        load_config(path)


def test_config_accepts_decision_input_only_with_runtime_switch_review_artifact(tmp_path):
    review_path = tmp_path / "switch-review.json"
    review_path.write_text(
        _final_input_switch_review_json(
            rollback_plan_ref="eval:eval-run:rollback_plan",
            fallback_behavior="legacy_prompt_on_candidate_failure",
        ),
        encoding="utf-8",
    )
    path = tmp_path / "ok.yaml"
    path.write_text(
        f"""
decision:
  final_input_mode: decision_input
  final_input_mode_switch_review_path: "{review_path.as_posix()}"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.decision.final_input_mode == "decision_input"
    assert config.decision.final_input_mode_switch_review_path == review_path.as_posix()


def test_config_rejects_decision_input_when_runtime_switch_review_lacks_rollback(tmp_path):
    review_path = tmp_path / "switch-review.json"
    review_path.write_text(
        _final_input_switch_review_json(rollback_plan_ref="", fallback_behavior="legacy_prompt_on_candidate_failure"),
        encoding="utf-8",
    )
    path = tmp_path / "bad.yaml"
    path.write_text(
        f"""
decision:
  final_input_mode: decision_input
  final_input_mode_switch_review_path: "{review_path.as_posix()}"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="rollback_plan_ref"):
        load_config(path)


def test_config_rejects_decision_input_when_runtime_switch_review_lacks_fallback(tmp_path):
    review_path = tmp_path / "switch-review.json"
    review_path.write_text(
        _final_input_switch_review_json(rollback_plan_ref="eval:eval-run:rollback_plan", fallback_behavior=""),
        encoding="utf-8",
    )
    path = tmp_path / "bad.yaml"
    path.write_text(
        f"""
decision:
  final_input_mode: decision_input
  final_input_mode_switch_review_path: "{review_path.as_posix()}"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="fallback_behavior"):
        load_config(path)


def test_config_rejects_decision_input_when_runtime_switch_review_lacks_ref_hash_bindings(tmp_path):
    cases = [
        ("artifact_ref", "", "artifact_ref"),
        ("eval_run_id", "", "eval_run_id"),
        ("release_gate_hash", "", "release_gate_hash"),
        ("config_change_review_approval_hash", "", "config_change_review_approval_hash"),
        ("manual_release_decision_hash", "", "manual_release_decision_hash"),
        ("config_change_review_request_hash", "", "config_change_review_request_hash"),
        ("candidate_input_hash", "", "candidate_input_hash"),
        ("config_hash", "", "config_hash"),
        ("rollback_plan_hash", "", "rollback_plan_hash"),
    ]
    for field_name, value, message in cases:
        review_path = tmp_path / f"switch-review-{field_name}.json"
        review_path.write_text(
            _final_input_switch_review_json(**{field_name: value}),
            encoding="utf-8",
        )
        path = tmp_path / f"bad-{field_name}.yaml"
        path.write_text(
            f"""
decision:
  final_input_mode: decision_input
  final_input_mode_switch_review_path: "{review_path.as_posix()}"
""",
            encoding="utf-8",
        )

        with pytest.raises(ConfigError, match=message):
            load_config(path)


def test_final_input_mode_cannot_be_enabled_by_environment(monkeypatch):
    monkeypatch.setenv("DECISION_FINAL_INPUT_MODE", "decision_input")
    monkeypatch.setenv("FINAL_INPUT_MODE", "decision_input")

    config = load_config("config/default.yaml")

    assert config.decision.final_input_mode == "legacy_prompt"


def test_config_rejects_forbidden_trade_key_env(monkeypatch):
    monkeypatch.setenv("OKX_TRADE_API_KEY", "not-allowed")

    with pytest.raises(ConfigError, match="forbidden"):
        load_config("config/default.yaml")


@pytest.mark.parametrize(
    "env_name",
    ["OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"],
)
def test_config_rejects_okx_private_account_envs_in_v1(monkeypatch, env_name):
    monkeypatch.setenv(env_name, "not-allowed")

    with pytest.raises(ConfigError, match=env_name):
        load_config("config/default.yaml")


def test_secret_redaction(monkeypatch):
    monkeypatch.setenv("BARK_DEVICE_KEY", "secret-bark-key")
    config = load_config("config/default.yaml")

    rendered = str(config.safe_dict())

    assert "secret-bark-key" not in rendered
    assert "BARK_DEVICE_KEY" in rendered


def test_research_env_overrides(monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("RESEARCH_SEARCH_PROVIDER", "responses_web_search")
    monkeypatch.setenv("RESEARCH_PLANNER", "llm")
    monkeypatch.setenv("RESEARCH_LEADER_MODE", "llm")
    monkeypatch.setenv("RESEARCH_MAX_QUERIES", "2")
    monkeypatch.setenv("RESEARCH_MAX_WORKERS", "2")
    monkeypatch.setenv("RESEARCH_REQUEST_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("SCHEDULER_JOB_TIMEOUT_SECONDS", "1800")

    config = load_config("config/default.yaml")

    assert config.research.enabled is True
    assert config.research.search_provider == "responses_web_search"
    assert config.research.planner == "llm"
    assert config.research.leader_mode == "llm"
    assert config.research.max_queries == 2
    assert config.research.max_workers == 2
    assert config.research.request_timeout_seconds == 5
    assert config.scheduler.job_timeout_seconds == 1800


def test_config_accepts_llm_research_planner_and_leader_mode(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
research:
  planner: llm
  leader_mode: llm
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.research.planner == "llm"
    assert config.research.leader_mode == "llm"


def test_config_rejects_unknown_research_planner(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
research:
  planner: magic
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="research.planner"):
        load_config(path)


def test_config_rejects_unknown_research_leader_mode(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
research:
  leader_mode: magic
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="research.leader_mode"):
        load_config(path)


def test_config_accepts_llm_tool_shadow_worker_mode(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
shadow:
  worker_mode: llm_tool_shadow
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.shadow.worker_mode == "llm_tool_shadow"


def test_config_accepts_skill_provider_modes(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
skill_providers:
  realtime_search: fixture
  root_cause: fixture
  liquidity_order_book: fixture
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.skill_providers.realtime_search == "fixture"
    assert config.skill_providers.root_cause == "fixture"
    assert config.skill_providers.liquidity_order_book == "fixture"


def test_config_rejects_unknown_skill_provider_mode(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
skill_providers:
  realtime_search: free_web
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="skill_providers.realtime_search"):
        load_config(path)


def test_config_accepts_controlled_shadow_workflow_mode(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
workflow:
  execution_mode: controlled_shadow
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.workflow.execution_mode == "controlled_shadow"


def test_config_accepts_production_candidate_swarm_workflow_mode(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
workflow:
  execution_mode: production_candidate_swarm
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.workflow.execution_mode == "production_candidate_swarm"


def test_config_rejects_unknown_workflow_execution_mode(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
workflow:
  execution_mode: free_swarm
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="workflow.execution_mode"):
        load_config(path)


def test_config_rejects_unknown_shadow_worker_mode(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
shadow:
  worker_mode: free_swarm
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="shadow.worker_mode"):
        load_config(path)


def test_config_accepts_release_gate_thresholds(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
eval:
  release_gate:
    minimum_case_count: 20
    schema_valid_rate_threshold: 0.95
    required_badcase_severities:
      - high
      - critical
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.eval.release_gate.minimum_case_count == 20
    assert config.eval.release_gate.schema_valid_rate_threshold == 0.95
    assert config.eval.release_gate.required_badcase_severities == ["high", "critical"]


def test_config_accepts_financial_quality_thresholds(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        """
eval:
  financial_quality:
    evaluation_targets:
      - swarm_candidate_final
    minimum_scored_count: 12
    minimum_direction_hit_rate: 0.55
    maximum_brier_score: 0.22
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.eval.financial_quality.evaluation_targets == ["swarm_candidate_final"]
    assert config.eval.financial_quality.minimum_scored_count == 12
    assert config.eval.financial_quality.minimum_direction_hit_rate == 0.55
    assert config.eval.financial_quality.maximum_brier_score == 0.22


def test_config_rejects_invalid_release_gate_thresholds(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
eval:
  release_gate:
    minimum_case_count: 0
    schema_valid_rate_threshold: 1.5
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="release_gate"):
        load_config(path)


def test_config_rejects_invalid_financial_quality_thresholds(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
eval:
  financial_quality:
    evaluation_targets: []
    minimum_scored_count: 0
    minimum_direction_hit_rate: 1.5
    maximum_brier_score: -0.1
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="financial_quality"):
        load_config(path)


def test_config_rejects_unknown_release_gate_badcase_severity(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
eval:
  release_gate:
    required_badcase_severities:
      - urgent
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="required_badcase_severities"):
        load_config(path)


def _final_input_switch_review_json(
    *,
    artifact_ref: str = "eval:eval-run:final_input_mode_switch_review",
    eval_run_id: str = "eval-run",
    release_gate_hash: str = "sha256:release-gate",
    config_change_review_approval_hash: str = "sha256:config-approval",
    manual_release_decision_hash: str = "sha256:manual-release",
    config_change_review_request_hash: str = "sha256:config-request",
    candidate_input_hash: str = "sha256:decision",
    config_hash: str = "sha256:config",
    rollback_plan_hash: str = "sha256:rollback",
    rollback_plan_ref: str = "eval:eval-run:rollback_plan",
    fallback_behavior: str = "legacy_prompt_on_candidate_failure",
) -> str:
    artifact = {
        "schema_version": 1,
        "artifact_type": "final_input_mode_switch_review",
        "artifact_ref": artifact_ref,
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "allowed_to_change_production_final_input": True,
        "baseline_final_input_mode": "legacy_prompt",
        "target_final_input_mode": "decision_input",
        "release_gate_status": "ready",
        "release_gate_ref": "eval:eval-run:release_gate",
        "release_gate_hash": release_gate_hash,
        "promotion_review_status": "config_change_review_approved",
        "config_change_review_approval_ref": "eval:eval-run:config_change_review_approval:config-owner",
        "config_change_review_approval_hash": config_change_review_approval_hash,
        "manual_release_decision_ref": "eval:eval-run:manual_release_decision:release-owner",
        "manual_release_decision_hash": manual_release_decision_hash,
        "config_change_review_request_ref": "eval:eval-run:config_change_review_request:release-owner",
        "config_change_review_request_hash": config_change_review_request_hash,
        "candidate_input_ref": "trace:eval:decision_input_candidate",
        "candidate_input_hash": candidate_input_hash,
        "config_hash": config_hash,
        "rollback_plan_ref": rollback_plan_ref,
        "rollback_plan_hash": rollback_plan_hash,
        "rollback_target": "config:decision.final_input_mode=legacy_prompt",
        "rollback_steps": ["restore decision.final_input_mode=legacy_prompt", "rerun release gate smoke"],
        "fallback_behavior": fallback_behavior,
        "manual_execution_required": True,
        "auto_order_enabled": False,
    }
    return json.dumps(artifact)
