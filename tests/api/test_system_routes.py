from __future__ import annotations

import os
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app
from crypto_manual_alert.config import ConfigError


def future_no_active_event_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (now - timedelta(minutes=30)).isoformat(), (now + timedelta(hours=6)).isoformat()


def set_prod_actionable_ready_env(monkeypatch: pytest.MonkeyPatch) -> None:
    confirmed_at, valid_until = future_no_active_event_window()
    monkeypatch.setenv("DECISION_ENGINE", "openai_compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test")
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setenv("OPENAI_API_KEY", "key-a")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "okx_public")
    monkeypatch.setenv("NOTIFICATION_ENABLED", "true")
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("MACRO_EVENT_PROVIDER", "no_active_event")
    monkeypatch.setenv("MACRO_EVENT_OPERATOR_REF", "ops:macro-desk")
    monkeypatch.setenv("MACRO_EVENT_CONFIRMED_AT", confirmed_at)
    monkeypatch.setenv("MACRO_EVENT_SOURCE_REF", "calendar:forexfactory:2026-07-09:no-high-impact")
    monkeypatch.setenv("MACRO_EVENT_ASSERTION_HORIZON", "6h")
    monkeypatch.setenv("MACRO_EVENT_VALID_UNTIL", valid_until)
    monkeypatch.setenv("CANDIDATE_SIDECAR_MODE", "disabled")


def final_input_switch_review_json() -> str:
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
            "rollback_steps": ["restore decision.final_input_mode=legacy_prompt", "rerun release gate smoke"],
            "fallback_behavior": "legacy_prompt_on_candidate_failure",
            "manual_execution_required": True,
            "auto_order_enabled": False,
        }
    )


def test_config_endpoint_returns_redacted_snapshot(tmp_path):
    """配置界面只读端点：返回 safe_dict 脱敏快照，覆盖 13 段且不泄露 secret。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/system/config")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]

    expected_sections = {
        "app", "trading", "market_data", "decision", "notification",
        "scheduler", "research", "shadow", "workflow", "skill_providers",
        "macro_event", "eval", "diagnostic", "security", "readiness",
    }
    assert expected_sections <= set(data.keys())

    # 安全护栏必须保持
    assert data["trading"]["auto_order_enabled"] is False
    assert data["trading"]["manual_execution_required"] is True

    # 默认配置仍是安全保守态
    assert data["decision"]["engine"] == "fixture"
    assert data["decision"]["final_input_mode"] == "legacy_prompt"
    assert data["workflow"]["execution_mode"] == "legacy_baseline"
    assert data["shadow"]["worker_mode"] == "local_audit"
    assert data["diagnostic"]["routes_enabled"] is False

    # LLM key 也只能显示 set/unset，不能泄漏原文
    assert data["decision"]["openai_api_key_value"] in {"<redacted>", "<unset>"}
    assert data["decision"]["openai_api_key_env"] == "OPENAI_API_KEY"

    # bark key 必须脱敏，不返回原文
    assert data["notification"]["bark_device_key_value"] in {"<redacted>", "<unset>"}
    assert "secret_env_names" in data["security"]

    readiness = data["readiness"]
    assert readiness["overall"]["status"] == "fixture_only"
    assert readiness["overall"]["real_external_ready"] is False
    assert readiness["decision_engine"]["status"] == "fixture_only"
    assert readiness["decision_engine"]["engine"] == "fixture"
    assert readiness["openai_credentials"]["status"] == "missing_env"
    assert readiness["openai_credentials"]["api_key_value"] == "<unset>"
    assert readiness["market_data"]["status"] == "fixture_only"
    assert readiness["event_status"]["status"] == "disabled"
    assert readiness["event_status"]["provider"] == "disabled"
    assert readiness["prod_actionable"]["status"] == "missing_env"
    assert readiness["prod_actionable"]["prod_actionable_ready"] is False
    assert readiness["notification"]["status"] == "disabled"
    assert readiness["trading_safety"]["status"] == "ready"
    assert readiness["forbidden_env"]["status"] == "ready"


def test_app_uses_config_paths_environment_when_paths_are_omitted(tmp_path, monkeypatch):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        """
market_data:
  provider: okx_public
macro_event:
  provider: no_active_event
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATHS", os.pathsep.join(["config/default.yaml", str(overlay)]))

    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/api/system/config")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["market_data"]["provider"] == "okx_public"
    assert data["macro_event"]["provider"] == "no_active_event"


def test_app_fails_fast_when_config_paths_environment_references_missing_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing-prod-overlay.yaml"
    monkeypatch.setenv("CONFIG_PATHS", os.pathsep.join(["config/default.yaml", str(missing)]))

    with pytest.raises(ConfigError, match="Config file does not exist"):
        create_app(data_dir=tmp_path)


def test_config_readiness_reports_prod_actionable_ready_when_event_and_external_env_are_ready(tmp_path, monkeypatch):
    """配置页 readiness 必须和 prod-actionable smoke 的发布门槛一致。"""

    set_prod_actionable_ready_env(monkeypatch)
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/system/config")

    assert response.status_code == 200
    readiness = response.json()["data"]["readiness"]
    assert readiness["overall"]["real_external_ready"] is True
    assert readiness["event_status"]["status"] == "ready"
    assert readiness["event_status"]["provider"] == "no_active_event"
    assert readiness["event_status"]["assertion_metadata_complete"] is True
    assert readiness["event_status"]["missing_assertion_metadata"] == []
    assert readiness["prod_actionable"]["status"] == "ready"
    assert readiness["prod_actionable"]["prod_actionable_ready"] is True
    assert readiness["prod_actionable"]["candidate_sidecar_disabled"] is True
    assert readiness["prod_actionable"]["production_main_path_ready"] is True
    assert readiness["prod_actionable"]["main_path_blockers"] == []


def test_config_readiness_requires_legacy_workflow_for_prod_actionable(tmp_path, monkeypatch):
    set_prod_actionable_ready_env(monkeypatch)
    monkeypatch.setenv("WORKFLOW_EXECUTION_MODE", "controlled_shadow")

    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))
    response = client.get("/api/system/config")

    assert response.status_code == 200
    readiness = response.json()["data"]["readiness"]
    assert readiness["overall"]["real_external_ready"] is True
    assert readiness["event_status"]["status"] == "ready"
    assert readiness["prod_actionable"]["prod_actionable_ready"] is False
    assert readiness["prod_actionable"]["production_main_path_ready"] is False
    assert readiness["prod_actionable"]["status"] == "missing_env"
    assert readiness["prod_actionable"]["main_path_blockers"] == [
        "workflow.execution_mode must be legacy_baseline for prod-actionable"
    ]


def test_config_readiness_requires_legacy_final_input_for_prod_actionable(tmp_path, monkeypatch):
    set_prod_actionable_ready_env(monkeypatch)
    review_path = tmp_path / "switch-review.json"
    review_path.write_text(final_input_switch_review_json(), encoding="utf-8")
    overlay = tmp_path / "decision-input.yaml"
    overlay.write_text(
        f"""
decision:
  final_input_mode: decision_input
  final_input_mode_switch_review_path: "{review_path.as_posix()}"
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(config_paths=["config/default.yaml", overlay], data_dir=tmp_path))
    response = client.get("/api/system/config")

    assert response.status_code == 200
    readiness = response.json()["data"]["readiness"]
    assert readiness["overall"]["real_external_ready"] is True
    assert readiness["event_status"]["status"] == "ready"
    assert readiness["prod_actionable"]["prod_actionable_ready"] is False
    assert readiness["prod_actionable"]["production_main_path_ready"] is False
    assert readiness["prod_actionable"]["status"] == "missing_env"
    assert readiness["prod_actionable"]["main_path_blockers"] == [
        "decision.final_input_mode must be legacy_prompt for prod-actionable"
    ]


def test_config_readiness_requires_no_active_event_assertion_metadata(tmp_path, monkeypatch):
    """A prod-actionable event assertion needs audit metadata, not just a provider switch."""

    monkeypatch.setenv("DECISION_ENGINE", "openai_compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test")
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setenv("OPENAI_API_KEY", "key-a")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "okx_public")
    monkeypatch.setenv("NOTIFICATION_ENABLED", "true")
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("MACRO_EVENT_PROVIDER", "no_active_event")
    monkeypatch.setenv("CANDIDATE_SIDECAR_MODE", "disabled")
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/system/config")

    assert response.status_code == 200
    readiness = response.json()["data"]["readiness"]
    assert readiness["overall"]["real_external_ready"] is True
    assert readiness["event_status"]["status"] == "missing_env"
    assert readiness["event_status"]["provider"] == "no_active_event"
    assert readiness["event_status"]["provider_ready"] is True
    assert readiness["event_status"]["assertion_metadata_complete"] is False
    assert readiness["event_status"]["missing_assertion_metadata"] == [
        "MACRO_EVENT_OPERATOR_REF",
        "MACRO_EVENT_CONFIRMED_AT",
        "MACRO_EVENT_SOURCE_REF",
        "MACRO_EVENT_ASSERTION_HORIZON",
        "MACRO_EVENT_VALID_UNTIL",
    ]
    assert readiness["prod_actionable"]["status"] == "missing_env"
    assert readiness["prod_actionable"]["event_ready"] is False
    assert readiness["prod_actionable"]["prod_actionable_ready"] is False


def test_config_readiness_requires_candidate_sidecar_disabled_for_prod_actionable(tmp_path, monkeypatch):
    """Env-only production setup must not be marked prod-actionable while sidecar can reuse the production LLM."""

    confirmed_at, valid_until = future_no_active_event_window()
    monkeypatch.setenv("DECISION_ENGINE", "openai_compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test")
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setenv("OPENAI_API_KEY", "key-a")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "okx_public")
    monkeypatch.setenv("NOTIFICATION_ENABLED", "true")
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("MACRO_EVENT_PROVIDER", "no_active_event")
    monkeypatch.setenv("MACRO_EVENT_OPERATOR_REF", "ops:macro-desk")
    monkeypatch.setenv("MACRO_EVENT_CONFIRMED_AT", confirmed_at)
    monkeypatch.setenv("MACRO_EVENT_SOURCE_REF", "calendar:forexfactory:2026-07-09:no-high-impact")
    monkeypatch.setenv("MACRO_EVENT_ASSERTION_HORIZON", "6h")
    monkeypatch.setenv("MACRO_EVENT_VALID_UNTIL", valid_until)
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/system/config")

    assert response.status_code == 200
    readiness = response.json()["data"]["readiness"]
    assert readiness["overall"]["real_external_ready"] is True
    assert readiness["event_status"]["status"] == "ready"
    assert readiness["prod_actionable"]["candidate_sidecar_disabled"] is False
    assert readiness["prod_actionable"]["status"] == "missing_env"
    assert readiness["prod_actionable"]["prod_actionable_ready"] is False


def test_config_readiness_rejects_local_endpoints_for_prod_actionable(tmp_path, monkeypatch):
    """Config readiness must match the strict prod-actionable gate for local/mock endpoints."""

    confirmed_at, valid_until = future_no_active_event_window()
    monkeypatch.setenv("DECISION_ENGINE", "openai_compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8011")
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setenv("OPENAI_API_KEY", "key-a")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "okx_public")
    monkeypatch.setenv("MARKET_DATA_OKX_BASE_URL", "http://127.0.0.1:8012")
    monkeypatch.setenv("NOTIFICATION_ENABLED", "true")
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("MACRO_EVENT_PROVIDER", "no_active_event")
    monkeypatch.setenv("MACRO_EVENT_OPERATOR_REF", "ops:macro-desk")
    monkeypatch.setenv("MACRO_EVENT_CONFIRMED_AT", confirmed_at)
    monkeypatch.setenv("MACRO_EVENT_SOURCE_REF", "calendar:forexfactory:2026-07-09:no-high-impact")
    monkeypatch.setenv("MACRO_EVENT_ASSERTION_HORIZON", "6h")
    monkeypatch.setenv("MACRO_EVENT_VALID_UNTIL", valid_until)
    monkeypatch.setenv("CANDIDATE_SIDECAR_MODE", "disabled")
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/system/config")

    assert response.status_code == 200
    readiness = response.json()["data"]["readiness"]
    assert readiness["overall"]["real_external_ready"] is False
    assert readiness["overall"]["status"] == "unsafe"
    assert readiness["decision_engine"]["status"] == "unsafe"
    assert readiness["market_data"]["status"] == "unsafe"
    assert readiness["prod_actionable"]["status"] == "unsafe"
    assert readiness["prod_actionable"]["prod_actionable_ready"] is False
    assert readiness["prod_actionable"]["unsafe"]
