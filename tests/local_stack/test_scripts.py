from __future__ import annotations

import importlib.util
import json
import os
import signal
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LOCAL_STACK_TOOLS = ROOT / "tools" / "local_stack"


def _load_script(name: str):
    path = LOCAL_STACK_TOOLS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(LOCAL_STACK_TOOLS))
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def _future_macro_event_env() -> dict[str, str]:
    confirmed_at = datetime.now(timezone.utc).isoformat()
    valid_until = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    return {
        "MACRO_EVENT_PROVIDER": "no_active_event",
        "MACRO_EVENT_OPERATOR_REF": "ops:macro-desk",
        "MACRO_EVENT_CONFIRMED_AT": confirmed_at,
        "MACRO_EVENT_SOURCE_REF": "calendar:forexfactory:manual-no-high-impact",
        "MACRO_EVENT_ASSERTION_HORIZON": "6h",
        "MACRO_EVENT_VALID_UNTIL": valid_until,
    }


def _expired_macro_event_env() -> dict[str, str]:
    confirmed_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    valid_until = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return {
        "MACRO_EVENT_PROVIDER": "no_active_event",
        "MACRO_EVENT_OPERATOR_REF": "ops:macro-desk",
        "MACRO_EVENT_CONFIRMED_AT": confirmed_at,
        "MACRO_EVENT_SOURCE_REF": "calendar:forexfactory:expired-manual-assertion",
        "MACRO_EVENT_ASSERTION_HORIZON": "6h",
        "MACRO_EVENT_VALID_UNTIL": valid_until,
    }


def test_local_smoke_api_env_disables_notification_by_default(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=False,
        real_market_enabled=False,
        base_env={"BARK_DEVICE_KEY": "device-key", "NOTIFICATION_ENABLED": "true"},
    )

    assert env["NOTIFICATION_ENABLED"] == "false"
    assert env["DIAGNOSTIC_ROUTES_ENABLED"] == "true"
    assert env["PYTHONPATH"].endswith("src")
    assert env["TMP"] == str(tmp_path)


def test_local_smoke_api_env_can_disable_diagnostic_routes_without_prod_actionable(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=False,
        real_market_enabled=False,
        diagnostic_routes_enabled=False,
        base_env={"DIAGNOSTIC_ROUTES_ENABLED": "true"},
    )

    assert env["DIAGNOSTIC_ROUTES_ENABLED"] == "false"
    assert env["DECISION_ENGINE"] == "fixture"
    assert env["MARKET_DATA_PROVIDER"] == "fixture"


def test_run_local_checks_covers_all_shared_local_stack_ports():
    checks = _load_script("run_local_checks.py")

    assert set(checks.LOCAL_PORTS) == {8010, 3001, 8011, 8012, 8013}


def test_run_local_checks_default_matrix_covers_browser_and_no_secret_smoke_profiles():
    checks = _load_script("run_local_checks.py")

    command_specs = checks._build_checks("npm")
    rendered = [" ".join(str(part) for part in spec.command) for spec in command_specs]

    assert any("npm run e2e" in command for command in rendered)
    smoke_commands = [command for command in rendered if "tools/local_stack/smoke_local_stack.py" in command]
    assert smoke_commands == [
        f"{sys.executable} tools/local_stack/smoke_local_stack.py",
        f"{sys.executable} tools/local_stack/smoke_local_stack.py --with-mock-llm",
        f"{sys.executable} tools/local_stack/smoke_local_stack.py --with-actionable-staging",
        f"{sys.executable} tools/local_stack/smoke_local_stack.py --seed-mock-outcome",
        f"{sys.executable} tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture",
    ]
    assert not any("--prod-actionable" in command for command in rendered)


def test_local_smoke_api_env_uses_explicit_data_dir_when_provided(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        data_dir=tmp_path / "api-data",
        notification_enabled=False,
        real_llm_enabled=False,
        real_market_enabled=False,
        base_env={},
    )

    assert env["DATA_DIR"] == str(tmp_path / "api-data")


def test_local_smoke_api_env_requires_bark_key_when_enabled(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(RuntimeError, match="BARK_DEVICE_KEY"):
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=True,
            real_llm_enabled=False,
            real_market_enabled=False,
            base_env={},
        )


def test_local_smoke_api_env_enables_real_bark_when_key_is_present(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=True,
        real_llm_enabled=False,
        real_market_enabled=False,
        base_env={"BARK_DEVICE_KEY": "device-key"},
    )

    assert env["NOTIFICATION_ENABLED"] == "true"
    assert env["BARK_DEVICE_KEY"] == "device-key"




def test_local_smoke_api_env_requires_real_llm_settings(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(RuntimeError, match="OPENAI_BASE_URL"):
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=True,
            real_market_enabled=False,
            base_env={},
        )


def test_local_smoke_api_env_enables_real_llm_when_configured(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=True,
        real_market_enabled=False,
        base_env={
            "OPENAI_BASE_URL": "https://llm.example.test",
            "OPENAI_MODEL": "model-a",
            "OPENAI_API_KEY": "key-a",
        },
    )

    assert env["DECISION_ENGINE"] == "openai_compatible"
    assert env["MARKET_DATA_PROVIDER"] == "fixture"


def test_local_smoke_api_env_enables_mock_llm_without_real_credentials(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=False,
        mock_llm_enabled=True,
        real_market_enabled=False,
        base_env={},
    )

    assert env["DECISION_ENGINE"] == "openai_compatible"
    assert env["OPENAI_BASE_URL"] == smoke.MOCK_OPENAI_BASE
    assert env["OPENAI_MODEL"] == "mock-crypto-plan"
    assert env["OPENAI_API_KEY"] == "local-mock-openai-key"
    assert env["OPENAI_API_KEY_ENV"] == "OPENAI_API_KEY"
    assert env["MARKET_DATA_PROVIDER"] == "fixture"
    assert env["NOTIFICATION_ENABLED"] == "false"


def test_mock_openai_server_returns_strict_decision_plan():
    mock_openai = _load_script("mock_openai_server.py")

    payload = mock_openai.chat_completion_payload(
        {
            "model": "mock-crypto-plan",
            "messages": [
                {"role": "user", "content": '{"market_snapshot":{"symbol":"ETH-USDT-SWAP"}}'}
            ],
        }
    )

    content = payload["choices"][0]["message"]["content"]
    assert content.startswith("{")
    assert content.endswith("}")
    assert '"instrument":"ETH-USDT-SWAP"' in content
    assert '"manual_execution_required":true' in content
    assert payload["usage"]["total_tokens"] > 0


def test_mock_okx_server_returns_exchange_native_public_payloads():
    mock_okx = _load_script("mock_okx_server.py")

    mark = mock_okx.okx_public_payload("/api/v5/public/mark-price")
    index = mock_okx.okx_public_payload("/api/v5/market/index-tickers", {"instId": ["ETH-USDT"]})
    book = mock_okx.okx_public_payload("/api/v5/market/books")
    history = mock_okx.okx_public_payload("/api/v5/market/history-candles")

    assert mark["code"] == "0"
    assert mark["data"][0]["markPx"] == "3499"
    assert "idxPx" not in mark["data"][0]
    assert index["data"][0]["instId"] == "ETH-USDT"
    assert index["data"][0]["idxPx"] == "3498"
    assert book["code"] == "0"
    assert book["data"][0]["asks"]
    assert book["data"][0]["bids"]
    assert history["code"] == "0"
    assert len(history["data"]) >= 6
    assert all(len(row) >= 9 for row in history["data"])
    assert history["data"] == sorted(history["data"], key=lambda row: int(row[0]), reverse=True)


def test_mock_error_api_server_returns_unsafe_envelope_for_redaction_tests():
    mock_error = _load_script("mock_error_api_server.py")

    payload = mock_error.error_envelope("/api/eval/runs?limit=10")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "LOCAL_STACK_FORCED_ERROR"
    assert "SQLITE_ERROR" in payload["error"]["message"]
    assert "BARK_DEVICE_KEY" in payload["error"]["message"]
    assert "request_json" in payload["error"]["message"]


def test_mock_error_api_server_enables_diagnostic_routes_for_diagnostic_error_tests():
    mock_error = _load_script("mock_error_api_server.py")

    payload = mock_error.system_config_envelope()

    assert payload["ok"] is True
    assert payload["data"]["diagnostic"]["routes_enabled"] is True


def test_mock_error_api_server_returns_partial_run_detail_projection_fixture():
    mock_error = _load_script("mock_error_api_server.py")

    payload = mock_error.partial_run_detail_envelope()

    assert payload["ok"] is True
    data = payload["data"]
    assert data["trace"]["trace_id"] == "partial-detail-trace"
    assert data["trace"]["run_type"] == "manual"
    assert data["plan_run"]["parsed_plan"]["instrument"] == "ETH-USDT-SWAP"
    assert data["plan_run"]["verdict"]["allowed"] is False
    assert "SQLITE_ERROR" in data["plan_run"]["verdict"]["reasons"][0]
    assert data["plan_run"]["business_summary"] is None
    assert "SQLITE_ERROR" in data["plan_run"]["agent_audit_view"]["facts_gate"]["reasons"][0]
    assert "SQLITE_ERROR" in data["plan_run"]["agent_audit_view"]["gates"]["production_control_gate"]["reasons"][0]
    assert (
        "SQLITE_ERROR"
        in data["plan_run"]["agent_audit_view"]["candidate_final_comparison"]["candidate"]["diagnosis"][
            "blocking_reasons"
        ][0]
    )
    assert "result_review" not in data


def test_local_smoke_api_env_enables_real_market_without_trade_keys(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=False,
        real_market_enabled=True,
        base_env={},
    )

    assert env["MARKET_DATA_PROVIDER"] == "okx_public"
    assert env["DECISION_ENGINE"] == "fixture"


def test_local_smoke_api_env_enables_actionable_staging_with_local_okx_mock(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=False,
        mock_llm_enabled=False,
        real_market_enabled=True,
        actionable_staging_enabled=True,
        base_env={"MARKET_DATA_PROVIDER": "fixture"},
    )

    assert env["MARKET_DATA_PROVIDER"] == "okx_public"
    assert env["MARKET_DATA_OKX_BASE_URL"] == smoke.MOCK_OKX_BASE
    assert env["MACRO_EVENT_PROVIDER"] == "no_active_event"
    assert env["DECISION_ENGINE"] == "fixture"
    assert env["NOTIFICATION_ENABLED"] == "false"


def test_local_smoke_prod_actionable_reports_missing_readiness(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(smoke.SmokeSkipped) as skipped:
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=False,
            real_market_enabled=False,
            prod_actionable_enabled=True,
            base_env={},
        )

    payload = skipped.value.payload
    assert payload["ok"] is False
    assert payload["smoke_profile"] == "prod_actionable"
    assert payload["skip_reason"] == "missing_readiness"
    assert payload["missing"] == [
        "BARK_DEVICE_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
        "MACRO_EVENT_PROVIDER=no_active_event",
    ]
    assert payload["manual_execution_required"] is True
    assert payload["auto_order_enabled"] is False


def test_local_smoke_prod_actionable_rejects_unimplemented_event_provider(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(smoke.SmokeSkipped) as skipped:
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=False,
            real_market_enabled=False,
            prod_actionable_enabled=True,
            base_env={
                "BARK_DEVICE_KEY": "device-key",
                "OPENAI_BASE_URL": "https://llm.example.test",
                "OPENAI_MODEL": "model-a",
                "OPENAI_API_KEY": "key-a",
                "MACRO_EVENT_PROVIDER": "operator_assertion",
            },
        )

    assert skipped.value.payload["missing"] == ["MACRO_EVENT_PROVIDER=no_active_event"]


def test_local_smoke_prod_actionable_requires_event_assertion_metadata(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(smoke.SmokeSkipped) as skipped:
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=False,
            real_market_enabled=False,
            prod_actionable_enabled=True,
            base_env={
                "BARK_DEVICE_KEY": "device-key",
                "OPENAI_BASE_URL": "https://llm.example.test",
                "OPENAI_MODEL": "model-a",
                "OPENAI_API_KEY": "key-a",
                "MACRO_EVENT_PROVIDER": "no_active_event",
            },
        )

    payload = skipped.value.payload
    assert payload["skip_reason"] == "missing_readiness"
    assert payload["missing"] == [
        "MACRO_EVENT_OPERATOR_REF",
        "MACRO_EVENT_CONFIRMED_AT",
        "MACRO_EVENT_SOURCE_REF",
        "MACRO_EVENT_ASSERTION_HORIZON",
        "MACRO_EVENT_VALID_UNTIL",
    ]
    assert payload["proof_level"] == "local-prod-actionable-rehearsal"
    assert payload["production_success"] is False
    assert payload["hosted_proof_required"] is True
    assert payload["does_not_prove"] == "hosted_prod_actionable"


def test_local_smoke_prod_actionable_rejects_local_mock_endpoints(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(smoke.SmokeSkipped) as skipped:
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=False,
            real_market_enabled=False,
            prod_actionable_enabled=True,
            base_env={
                "BARK_DEVICE_KEY": "device-key",
                "OPENAI_BASE_URL": "http://127.0.0.1:8011",
                "OPENAI_MODEL": "model-a",
                "OPENAI_API_KEY": "key-a",
                "MARKET_DATA_OKX_BASE_URL": "http://127.0.0.1:8012",
                **_future_macro_event_env(),
            },
        )

    payload = skipped.value.payload
    assert payload["skip_reason"] == "unsafe_readiness"
    assert payload["unsafe"] == [
        "OPENAI_BASE_URL must be a public https endpoint for prod-actionable",
        "MARKET_DATA_OKX_BASE_URL must be unset or https://www.okx.com for prod-actionable",
    ]
    assert payload["proof_level"] == "local-prod-actionable-rehearsal"
    assert payload["production_success"] is False
    assert payload["hosted_proof_required"] is True
    assert payload["does_not_prove"] == "hosted_prod_actionable"


def test_local_smoke_prod_actionable_rejects_mock_model_name(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(smoke.SmokeSkipped) as skipped:
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=False,
            real_market_enabled=False,
            prod_actionable_enabled=True,
            base_env={
                "BARK_DEVICE_KEY": "device-key",
                "OPENAI_BASE_URL": "https://llm.example.test",
                "OPENAI_MODEL": "mock-crypto-plan",
                "OPENAI_API_KEY": "key-a",
                **_future_macro_event_env(),
            },
        )

    payload = skipped.value.payload
    assert payload["skip_reason"] == "unsafe_readiness"
    assert payload["unsafe"] == ["OPENAI_MODEL must not be a mock model for prod-actionable"]
    assert payload["proof_level"] == "local-prod-actionable-rehearsal"
    assert payload["production_success"] is False
    assert payload["hosted_proof_required"] is True
    assert payload["does_not_prove"] == "hosted_prod_actionable"


def test_local_smoke_prod_actionable_default_skip_returns_zero(monkeypatch, capsys):
    smoke = _load_script("smoke_local_stack.py")

    monkeypatch.setattr(
        smoke,
        "_ensure_port_free",
        lambda port: None,
    )
    monkeypatch.setattr(
        smoke,
        "_start_api",
        lambda **kwargs: (_ for _ in ()).throw(
            smoke.SmokeSkipped(
                {
                    "ok": False,
                    "smoke_profile": "prod_actionable",
                    "skip_reason": "missing_readiness",
                    "missing": ["BARK_DEVICE_KEY"],
                    "manual_execution_required": True,
                    "auto_order_enabled": False,
                }
            )
        ),
    )

    assert smoke.main(["--prod-actionable"]) == 0
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert '"proof_level": "local-prod-actionable-rehearsal"' in output
    assert '"production_success": false' in output
    assert '"hosted_proof_required": true' in output
    assert '"does_not_prove": "hosted_prod_actionable"' in output


def test_local_smoke_prod_actionable_fail_on_skip_returns_nonzero(monkeypatch, capsys):
    smoke = _load_script("smoke_local_stack.py")

    monkeypatch.setattr(
        smoke,
        "_ensure_port_free",
        lambda port: None,
    )
    monkeypatch.setattr(
        smoke,
        "_start_api",
        lambda **kwargs: (_ for _ in ()).throw(
            smoke.SmokeSkipped(
                {
                    "ok": False,
                    "smoke_profile": "prod_actionable",
                    "skip_reason": "missing_readiness",
                    "missing": ["BARK_DEVICE_KEY"],
                    "manual_execution_required": True,
                    "auto_order_enabled": False,
                }
            )
        ),
    )

    assert smoke.main(["--prod-actionable", "--fail-on-skip"]) == 2
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert '"skip_reason": "missing_readiness"' in output
    assert '"proof_level": "local-prod-actionable-rehearsal"' in output
    assert '"production_success": false' in output
    assert '"hosted_proof_required": true' in output
    assert '"does_not_prove": "hosted_prod_actionable"' in output


def test_local_smoke_api_env_enables_prod_actionable_when_ready(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        real_llm_enabled=False,
        real_market_enabled=False,
        prod_actionable_enabled=True,
        base_env={
            "BARK_DEVICE_KEY": "device-key",
            "OPENAI_BASE_URL": "https://llm.example.test",
            "OPENAI_MODEL": "model-a",
            "OPENAI_API_KEY": "key-a",
            **_future_macro_event_env(),
        },
    )

    assert env["NOTIFICATION_ENABLED"] == "true"
    assert env["DECISION_ENGINE"] == "openai_compatible"
    assert env["CANDIDATE_SIDECAR_MODE"] == "disabled"
    assert env["MARKET_DATA_PROVIDER"] == "okx_public"
    assert env["MACRO_EVENT_PROVIDER"] == "no_active_event"
    assert env["MACRO_EVENT_OPERATOR_REF"] == "ops:macro-desk"
    assert env["DIAGNOSTIC_ROUTES_ENABLED"] == "false"


def test_local_smoke_prod_actionable_rejects_expired_event_assertion(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(smoke.SmokeSkipped) as skipped:
        smoke._build_api_env(
            tmp_dir=tmp_path,
            notification_enabled=False,
            real_llm_enabled=False,
            real_market_enabled=False,
            prod_actionable_enabled=True,
            base_env={
                "BARK_DEVICE_KEY": "device-key",
                "OPENAI_BASE_URL": "https://llm.example.test",
                "OPENAI_MODEL": "model-a",
                "OPENAI_API_KEY": "key-a",
                **_expired_macro_event_env(),
            },
        )

    payload = skipped.value.payload
    assert payload["skip_reason"] == "unsafe_readiness"
    assert payload["unsafe"] == ["MACRO_EVENT_VALID_UNTIL must be in the future for prod-actionable"]


def test_local_smoke_prod_actionable_requires_bark_delivery_assertion(monkeypatch, capsys):
    smoke = _load_script("smoke_local_stack.py")
    notification_checks: list[str] = []

    class DoneProcess:
        pid = 12345

        def poll(self):
            return 0

    def fake_wait_for_json(url, name):
        if url.endswith("/api/system/config"):
            return {
                "data": {
                    "decision": {"engine": "openai_compatible", "openai_model": "model-a"},
                    "market_data": {"provider": "okx_public"},
                    "macro_event": {"provider": "no_active_event"},
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                }
            }
        return {"ok": True}

    monkeypatch.setattr(smoke, "_ensure_port_free", lambda port: None)
    monkeypatch.setattr(smoke, "_start_api", lambda **kwargs: DoneProcess())
    monkeypatch.setattr(smoke, "_start_frontend", lambda: DoneProcess())
    monkeypatch.setattr(smoke, "_wait_for_json", fake_wait_for_json)
    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: "__next Crypto")
    monkeypatch.setattr(smoke, "_assert_cors_preflight", lambda: None)
    monkeypatch.setattr(smoke, "_assert_frontend_page", lambda path: None)
    monkeypatch.setattr(smoke, "_assert_manual_run", lambda: "trace-1")
    monkeypatch.setattr(smoke, "_assert_run_list_contains", lambda trace_id: None)
    monkeypatch.setattr(
        smoke,
        "_assert_run_detail",
        lambda trace_id: {"data": {"trace": {"allowed": True, "final_plan_id": "plan-1"}}},
    )
    monkeypatch.setattr(smoke, "_assert_real_llm_detail", lambda detail: None)
    monkeypatch.setattr(smoke, "_assert_llm_payload_redaction", lambda trace_id: None)
    monkeypatch.setattr(smoke, "_assert_real_market_detail", lambda detail: None)
    monkeypatch.setattr(smoke, "_assert_actionable_staging_detail", lambda detail: None)
    monkeypatch.setattr(smoke, "_assert_frontend_summary_page", lambda trace_id, allowed=False: None)
    monkeypatch.setattr(smoke, "_assert_frontend_agent_audit_page", lambda trace_id: None)

    def fake_notification_check(trace_id):
        notification_checks.append(trace_id)
        return {"enabled": True, "ok": True, "status": "sent", "status_code": 200, "plan_id": "plan-1"}

    monkeypatch.setattr(smoke, "_assert_notification_sent", fake_notification_check)

    assert smoke.main(["--prod-actionable"]) == 0
    output = capsys.readouterr().out
    assert notification_checks == ["trace-1"]
    assert '"notification_enabled": true' in output
    assert '"status": "sent"' in output
    assert '"ok": true' in output


def test_local_smoke_notification_assertion_returns_sent_status(monkeypatch, tmp_path):
    smoke = _load_script("smoke_local_stack.py")
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "crypto-alert.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE notifications (id INTEGER PRIMARY KEY, plan_id TEXT, ok INTEGER, status_code INTEGER, error TEXT)")
        conn.execute(
            "INSERT INTO notifications (plan_id, ok, status_code, error) VALUES (?, ?, ?, ?)",
            ("plan-1", 1, 200, None),
        )

    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(
        smoke,
        "_wait_for_json",
        lambda url, name: {"data": {"trace": {"final_plan_id": "plan-1"}}},
    )

    result = smoke._assert_notification_sent("trace-1")

    assert result == {
        "enabled": True,
        "ok": True,
        "status": "sent",
        "status_code": 200,
        "plan_id": "plan-1",
    }


def test_local_smoke_profile_names_actionable_staging():
    smoke = _load_script("smoke_local_stack.py")

    assert (
        smoke._smoke_profile(
            real_llm_enabled=False,
            mock_llm_enabled=False,
            real_market_enabled=False,
            actionable_staging_enabled=True,
        )
        == "actionable_staging"
    )


def test_local_smoke_profile_names_collect_outcomes_fixture():
    smoke = _load_script("smoke_local_stack.py")

    assert (
        smoke._smoke_profile(
            real_llm_enabled=False,
            mock_llm_enabled=False,
            real_market_enabled=False,
            collect_outcomes_fixture_enabled=True,
        )
        == "collect_outcomes_fixture"
    )


def test_local_smoke_profile_names_prod_actionable():
    smoke = _load_script("smoke_local_stack.py")

    assert (
        smoke._smoke_profile(
            real_llm_enabled=False,
            mock_llm_enabled=False,
            real_market_enabled=False,
            actionable_staging_enabled=False,
            prod_actionable_enabled=True,
        )
        == "prod_actionable"
    )


def test_local_smoke_prod_actionable_success_boundary_is_not_production_success():
    smoke = _load_script("smoke_local_stack.py")

    boundary = smoke._local_proof_boundary(prod_actionable_enabled=True)

    assert boundary["proof_level"] == "local-prod-actionable-rehearsal"
    assert boundary["production_success"] is False
    assert boundary["hosted_proof_required"] is True
    assert boundary["does_not_prove"] == "hosted_prod_actionable"


def test_local_smoke_asserts_agent_audit_view_contract():
    smoke = _load_script("smoke_local_stack.py")

    smoke._assert_agent_audit_view(
        {
            "data": {
                "plan_run": {
                    "agent_audit_view": {
                        "available": True,
                        "lead_plan": {"tasks": [{"agent_name": f"Agent{i}"} for i in range(7)]},
                        "workers": [
                            {"agent_name": "ExecutionRiskAgent"},
                            *({"agent_name": f"Agent{i}"} for i in range(6)),
                        ],
                        "decision_input": {"mode": "pre_final_candidate"},
                        "query_semantics": {"mode": "audit_note", "drives_final_input": False},
                        "gates": {"production_control_gate": {"allowed": False}},
                        "runtime_flow": [
                            {"name": "market.fetch", "source": "span_tree_refs"},
                            {"name": "decision_input.pre_final", "source": "span_tree_refs"},
                            {"name": "shadow_swarm.worker", "source": "span_tree_refs"},
                            {"name": "decision.final", "source": "span_tree_refs"},
                            {"name": "parser.strict_json", "source": "span_tree_refs"},
                        ],
                        "tool_calls": [],
                        "evidence_sources": [],
                        "source_freshness": [],
                        "conflict_edges": [],
                        "root_cause_graph": {"nodes": [], "edges": []},
                        "input_lineage": {"production_final_input_mode": "legacy_prompt"},
                        "release_eval_gate": {
                            "financial_quality_gate": {"status": "not_configured"}
                        },
                    }
                }
            }
        }
    )


def test_local_smoke_asserts_actionable_staging_detail_contract():
    smoke = _load_script("smoke_local_stack.py")

    smoke._assert_actionable_staging_detail(
        {
            "data": {
                "trace": {"allowed": True},
                "plan_run": {
                    "verdict": {"allowed": True},
                    "parsed_plan": {"manual_execution_required": True},
                    "business_summary": {"decision_label": "可人工复核"},
                    "agent_audit_view": {
                        "facts_gate": {
                            "missing_execution_facts": [],
                            "missing_event_facts": [],
                        },
                        "gates": {"production_control_gate": {"allowed": True}},
                    },
                },
            }
        }
    )

    with pytest.raises(AssertionError, match="allowed trace"):
        smoke._assert_actionable_staging_detail(
            {
                "data": {
                    "trace": {"allowed": False},
                    "plan_run": {},
                }
            }
        )


def test_local_smoke_rejects_missing_agent_audit_view():
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(AssertionError, match="agent_audit_view"):
        smoke._assert_agent_audit_view({"data": {"plan_run": {}}})


def test_local_smoke_checks_eval_quality_tab(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")
    seen: list[str] = []

    def fake_wait_for_text(url, name):
        seen.append(url)
        if url.endswith("/eval") or url.endswith("/eval?tab=quality"):
            return "__next 质量复盘 金融质量"
        return "__next 质量复盘"

    monkeypatch.setattr(smoke, "_wait_for_text", fake_wait_for_text)

    smoke._assert_frontend_page("/eval")
    smoke._assert_frontend_page("/eval?tab=quality")

    assert seen[-2].endswith("/eval")
    assert seen[-1].endswith("/eval?tab=quality")


def test_local_smoke_assert_eval_quality_outcome_visible_requires_mocked_outcome(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")

    def good_outcomes(url, name, *args, **kwargs):
        assert url.endswith("/api/eval/outcomes")
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "decision_ref": "mocked-outcome-seed",
                        "evaluation_target": "legacy_final",
                        "symbol": "ETH-USDT-SWAP",
                        "action": "trigger long",
                        "can_score": False,
                        "unscored_reason": "price_source_not_exchange_native",
                        "window": {
                            "source_type": "mocked_outcome",
                            "unscored_reason": "price_source_not_exchange_native",
                        },
                    }
                ]
            },
        }

    html = "__next 金融质量 样本 1 本地展示样本 价格不是交易所原生样本 最终建议链路 ETH-USDT-SWAP 不可评分"
    monkeypatch.setattr(smoke, "_wait_for_json", good_outcomes)
    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: html)

    smoke._assert_eval_quality_outcome_visible()

    def wrong_source(url, name, *args, **kwargs):
        payload = good_outcomes(url, name)
        payload["data"]["items"][0]["window"]["source_type"] = "exchange_native"
        payload["data"]["items"][0]["can_score"] = True
        payload["data"]["items"][0]["unscored_reason"] = None
        return payload

    monkeypatch.setattr(smoke, "_wait_for_json", wrong_source)
    with pytest.raises(AssertionError, match="mocked_outcome"):
        smoke._assert_eval_quality_outcome_visible()


def test_local_smoke_rejects_mock_outcome_without_unscored_product_explanation(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")

    monkeypatch.setattr(
        smoke,
        "_wait_for_json",
        lambda url, name: {
            "ok": True,
            "data": {
                "items": [
                    {
                        "decision_ref": "mocked-outcome-seed",
                        "evaluation_target": "legacy_final",
                        "symbol": "ETH-USDT-SWAP",
                        "action": "trigger long",
                        "can_score": False,
                        "unscored_reason": "price_source_not_exchange_native",
                        "window": {
                            "source_type": "mocked_outcome",
                            "unscored_reason": "price_source_not_exchange_native",
                        },
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        smoke,
        "_wait_for_text",
        lambda url, name: "__next 金融质量 样本 1 最终建议链路 ETH-USDT-SWAP",
    )

    with pytest.raises(AssertionError, match="unscored"):
        smoke._assert_eval_quality_outcome_visible()


def test_local_smoke_rejects_quality_page_internal_outcome_codes(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")

    monkeypatch.setattr(
        smoke,
        "_wait_for_json",
        lambda url, name: {
            "ok": True,
            "data": {
                "items": [
                    {
                        "decision_ref": "mocked-outcome-seed",
                        "evaluation_target": "legacy_final",
                        "symbol": "ETH-USDT-SWAP",
                        "action": "trigger long",
                        "can_score": False,
                        "unscored_reason": "price_source_not_exchange_native",
                        "window": {
                            "source_type": "mocked_outcome",
                            "unscored_reason": "price_source_not_exchange_native",
                        },
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        smoke,
        "_wait_for_text",
        lambda url, name: (
            "__next 金融质量 样本 1 mocked-outcome-seed 本地展示样本 mocked_outcome "
            "价格不是交易所原生样本 price_source_not_exchange_native 最终建议链路 legacy_final ETH-USDT-SWAP 不可评分"
        ),
    )

    with pytest.raises(AssertionError, match="internal outcome code"):
        smoke._assert_eval_quality_outcome_visible()


def test_local_smoke_rejects_raw_json_frontend_page(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")

    monkeypatch.setattr(
        smoke,
        "_wait_for_text",
        lambda url, name: '{"ok": true, "data": {"trace_id": "trace-1"}}',
    )

    with pytest.raises(AssertionError, match="raw JSON"):
        smoke._assert_frontend_page("/manual-run")


def test_local_smoke_requires_main_business_page_anchors(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")

    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: "__next Crypto")

    with pytest.raises(AssertionError, match="missing"):
        smoke._assert_frontend_page("/runs")


def test_local_smoke_asserts_frontend_agent_audit_text():
    smoke = _load_script("smoke_local_stack.py")

    full_body = (
        "Agent Swarm Audit LeadPlan Worker Matrix Skill Tool Calls "
        "Source Freshness Root Cause Graph Conflict Matrix Candidate Comparison "
        "Input Lineage Release And Gates ExecutionRiskAgent DecisionInput "
        "production_control_gate audit_note"
    )

    smoke._assert_frontend_agent_audit_html(full_body)

    with pytest.raises(AssertionError, match="ExecutionRiskAgent"):
        smoke._assert_frontend_agent_audit_html(full_body.replace("ExecutionRiskAgent", ""))

    with pytest.raises(AssertionError, match="audit_note"):
        smoke._assert_frontend_agent_audit_html(full_body.replace("audit_note", ""))


def test_local_smoke_checks_agent_audit_on_matrix_tab(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")
    seen: dict[str, str] = {}

    def fake_wait_for_text(url, name):
        seen["url"] = url
        seen["name"] = name
        return (
            "__next Agent Swarm Audit LeadPlan Worker Matrix Skill Tool Calls "
            "Source Freshness Root Cause Graph Conflict Matrix Candidate Comparison "
            "Input Lineage Release And Gates ExecutionRiskAgent DecisionInput "
            "production_control_gate audit_note"
        )

    monkeypatch.setattr(smoke, "_wait_for_text", fake_wait_for_text)

    smoke._assert_frontend_agent_audit_page("trace-1")

    assert seen["url"].endswith("/runs/trace-1?tab=matrix&columns=observability")


def test_local_smoke_frontend_summary_accepts_actionable_manual_review(monkeypatch):
    smoke = _load_script("smoke_local_stack.py")

    body = (
        "<html><body>__next 提醒详情 建议摘要 当前持仓 风险模式 "
        "事实检查 复核门槛 通知 可人工复核"
        "<script>window.__next_f.push('Trace LLM legacy_prompt')</script></body></html>"
    )
    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: body)

    smoke._assert_frontend_summary_page("trace-allowed", allowed=True)

    with pytest.raises(AssertionError, match="已阻断"):
        smoke._assert_frontend_summary_page("trace-allowed", allowed=False)

    visible_leak = body.replace("</body>", " Trace</body>")
    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: visible_leak)
    with pytest.raises(AssertionError, match="leaked Trace"):
        smoke._assert_frontend_summary_page("trace-visible-leak", allowed=True)


def test_start_local_stack_detaches_posix_process_group(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []

    class Process:
        pid = 12345

    def fake_popen(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    monkeypatch.setattr(start.subprocess, "Popen", fake_popen)

    process = start._popen_detached(
        ["python3", "-m", "uvicorn"],
        cwd=tmp_path,
        env={},
        stdout=tmp_path / "out.log",
        stderr=tmp_path / "err.log",
    )

    assert process.pid == 12345
    if os.name == "nt":
        assert calls[0]["creationflags"] != 0
    else:
        assert calls[0]["start_new_session"] is True


def test_start_local_stack_frontend_production_mode_uses_next_start(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []
    build_calls: list[str] = []

    class Process:
        pid = 12345

    def fake_popen_detached(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    monkeypatch.setattr(start, "_popen_detached", fake_popen_detached)
    monkeypatch.setattr(
        start,
        "_run_frontend_build",
        lambda env: build_calls.append(f"{env['NEXT_PUBLIC_API_BASE_URL']}|{env['API_INTERNAL_BASE_URL']}"),
    )
    monkeypatch.setattr(start, "ROOT", tmp_path)
    build_dir = tmp_path / "frontend" / ".next"
    build_dir.mkdir(parents=True)
    (build_dir / "BUILD_ID").write_text("build-1", encoding="utf-8")

    process = start._start_frontend_detached(mode="production")

    assert process.pid == 12345
    assert build_calls == [f"{start.smoke.API_BASE}|{start.smoke.API_BASE}"]
    command = calls[0]["command"]
    assert command[:3] == ["npm", "exec", "next"]
    assert "start" in command
    assert calls[0]["env"]["NEXT_PUBLIC_API_BASE_URL"] == start.smoke.API_BASE
    assert calls[0]["env"]["API_INTERNAL_BASE_URL"] == start.smoke.API_BASE


def test_start_local_stack_frontend_production_mode_builds_when_build_id_missing(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []
    build_calls: list[str] = []

    class Process:
        pid = 12345

    def fake_popen_detached(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    def fake_run_frontend_build(env):
        build_calls.append(f"{env['NEXT_PUBLIC_API_BASE_URL']}|{env['API_INTERNAL_BASE_URL']}")

    monkeypatch.setattr(start, "_popen_detached", fake_popen_detached)
    monkeypatch.setattr(start, "_run_frontend_build", fake_run_frontend_build)
    monkeypatch.setattr(start, "ROOT", tmp_path)
    (tmp_path / "frontend").mkdir()

    process = start._start_frontend_detached(mode="production")

    assert process.pid == 12345
    assert build_calls == [f"{start.smoke.API_BASE}|{start.smoke.API_BASE}"]
    assert calls[0]["command"][:3] == ["npm", "exec", "next"]


def test_start_local_stack_frontend_production_mode_rebuilds_even_when_build_id_exists(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    build_calls: list[str] = []

    class Process:
        pid = 12345

    monkeypatch.setattr(start, "_popen_detached", lambda command, **kwargs: Process())
    monkeypatch.setattr(
        start,
        "_run_frontend_build",
        lambda env: build_calls.append(f"{env['NEXT_PUBLIC_API_BASE_URL']}|{env['API_INTERNAL_BASE_URL']}"),
    )
    monkeypatch.setattr(start, "ROOT", tmp_path)
    build_dir = tmp_path / "frontend" / ".next"
    build_dir.mkdir(parents=True)
    (build_dir / "BUILD_ID").write_text("build-1", encoding="utf-8")

    start._start_frontend_detached(mode="production")

    assert build_calls == [f"{start.smoke.API_BASE}|{start.smoke.API_BASE}"]


def test_start_local_stack_frontend_can_override_server_internal_api(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []
    build_calls: list[str] = []

    class Process:
        pid = 12345

    def fake_popen_detached(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    monkeypatch.setattr(start, "_popen_detached", fake_popen_detached)
    monkeypatch.setattr(
        start,
        "_run_frontend_build",
        lambda env: build_calls.append(f"{env['NEXT_PUBLIC_API_BASE_URL']}|{env['API_INTERNAL_BASE_URL']}"),
    )
    monkeypatch.setattr(start, "ROOT", tmp_path)
    (tmp_path / "frontend").mkdir()

    process = start._start_frontend_detached(
        mode="production",
        internal_api_base_url="http://127.0.0.1:8013",
    )

    assert process.pid == 12345
    assert build_calls == [f"{start.smoke.API_BASE}|http://127.0.0.1:8013"]
    assert calls[0]["env"]["NEXT_PUBLIC_API_BASE_URL"] == start.smoke.API_BASE
    assert calls[0]["env"]["API_INTERNAL_BASE_URL"] == "http://127.0.0.1:8013"


def test_start_local_stack_api_uses_isolated_data_dir(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []

    class Process:
        pid = 12345

    def fake_popen_detached(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    monkeypatch.setattr(start, "_popen_detached", fake_popen_detached)

    process = start._start_api_detached(notification_enabled=False, data_dir=tmp_path / "stack-data")

    assert process.pid == 12345
    assert calls[0]["env"]["DATA_DIR"] == str(tmp_path / "stack-data")


def test_local_smoke_seed_mock_eval_outcome_writes_eval_sidecar_only(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    outcome = smoke._seed_mock_eval_outcome(tmp_path)

    from crypto_manual_alert.eval.outcome_store import OutcomeStore
    from crypto_manual_alert.eval.runner import outcome_store_path

    outcomes = OutcomeStore(outcome_store_path(tmp_path)).list_outcomes()
    assert outcome["decision_ref"] == "mocked-outcome-seed"
    assert len(outcomes) == 1
    assert outcomes[0].decision_ref == "mocked-outcome-seed"
    assert outcomes[0].evaluation_target == "legacy_final"
    assert outcomes[0].symbol == "ETH-USDT-SWAP"
    assert outcomes[0].window.source_type == "mocked_outcome"
    assert outcomes[0].can_score is False
    assert outcomes[0].unscored_reason == "price_source_not_exchange_native"
    assert not (tmp_path / "crypto-alert.db").exists()


def test_start_local_stack_can_seed_mock_eval_outcome(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    seeded: list[str] = []
    config_requests: list[str] = []

    monkeypatch.setattr(start.smoke, "_ensure_port_free", lambda port: None)
    monkeypatch.setattr(start, "_start_api_detached", lambda **kwargs: type("Process", (), {"pid": 1})())
    monkeypatch.setattr(start, "_start_frontend_detached", lambda **kwargs: type("Process", (), {"pid": 2})())
    monkeypatch.setattr(start, "_start_mock_openai_detached", lambda: type("Process", (), {"pid": 3})())

    def fake_wait_for_json(url, name, *args, **kwargs):
        if url.endswith("/api/system/config"):
            config_requests.append(url)
            return {
                "data": {
                    "decision": {"engine": "openai_compatible"},
                    "market_data": {"provider": "fixture"},
                    "macro_event": {"provider": "disabled"},
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                }
            }
        return {"ok": True}

    monkeypatch.setattr(start.smoke, "_wait_for_json", fake_wait_for_json)
    monkeypatch.setattr(start.smoke, "_wait_for_text", lambda *args, **kwargs: "__next Crypto")
    monkeypatch.setattr(start.smoke, "_assert_cors_preflight", lambda: None)
    monkeypatch.setattr(start.smoke, "_assert_frontend_page", lambda path: None)
    monkeypatch.setattr(start.shutil, "rmtree", lambda *args, **kwargs: None)
    monkeypatch.setattr(start, "PID_FILE", tmp_path / "pids.json")
    monkeypatch.setattr(start, "LOG_DIR", tmp_path)
    monkeypatch.setattr(start.smoke, "_seed_mock_eval_outcome", lambda data_dir: seeded.append(str(data_dir)) or {"decision_ref": "mocked-outcome-seed"})

    assert start.main(
        [
            "--data-dir",
            str(tmp_path / "stack-data"),
            "--frontend-mode",
            "production",
            "--with-bark",
            "--with-mock-llm",
            "--seed-mock-outcome",
        ]
    ) == 0

    assert seeded == [str(tmp_path / "stack-data")]
    payload = (tmp_path / "pids.json").read_text(encoding="utf-8")
    data = json.loads(payload)
    assert config_requests == [start.smoke.API_BASE + "/api/system/config"]
    assert data["frontend_mode"] == "production"
    assert data["frontend_api_base_url"] == start.smoke.API_BASE
    assert data["api_base_embedded_in_frontend"] == start.smoke.API_BASE
    assert data["frontend_internal_api_base_url"] == start.smoke.API_BASE
    assert data["notification_enabled"] is True
    assert data["real_llm_enabled"] is False
    assert data["mock_llm_enabled"] is True
    assert data["real_market_enabled"] is False
    assert data["actionable_staging_enabled"] is False
    assert data["market_provider"] == "fixture"
    assert data["macro_event_provider"] == "disabled"
    assert data["manual_execution_required"] is True
    assert data["auto_order_enabled"] is False
    assert data["mock_outcome_seeded"] is True
    assert data["mock_outcome_quality_scope"] == "visibility_only_not_financial_quality"


def test_start_local_stack_can_start_actionable_staging_with_mock_okx(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    freed_ports: list[int] = []
    started_api: list[dict[str, object]] = []
    started_okx: list[str] = []
    health_checks: list[str] = []

    class Process:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_wait_for_json(url, name, *args, **kwargs):
        health_checks.append(url)
        if url.endswith("/api/system/config"):
            return {
                "data": {
                    "decision": {"engine": "fixture"},
                    "market_data": {"provider": "okx_public"},
                    "macro_event": {"provider": "no_active_event"},
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                }
            }
        return {"ok": True}

    monkeypatch.setattr(start.smoke, "_ensure_port_free", lambda port: freed_ports.append(port))
    monkeypatch.setattr(start, "_start_mock_okx_detached", lambda: started_okx.append("okx") or Process(3), raising=False)
    monkeypatch.setattr(start, "_start_api_detached", lambda **kwargs: started_api.append(kwargs) or Process(1))
    monkeypatch.setattr(start, "_start_frontend_detached", lambda **kwargs: Process(2))
    monkeypatch.setattr(start.smoke, "_wait_for_json", fake_wait_for_json)
    monkeypatch.setattr(start.smoke, "_wait_for_text", lambda *args, **kwargs: "__next Crypto")
    monkeypatch.setattr(start.smoke, "_assert_cors_preflight", lambda: None)
    monkeypatch.setattr(start.smoke, "_assert_frontend_page", lambda path: None)
    monkeypatch.setattr(start.shutil, "rmtree", lambda *args, **kwargs: None)
    monkeypatch.setattr(start, "PID_FILE", tmp_path / "pids.json")
    monkeypatch.setattr(start, "LOG_DIR", tmp_path)

    assert start.main(["--data-dir", str(tmp_path / "stack-data"), "--with-actionable-staging"]) == 0

    assert start.smoke.MOCK_OKX_PORT in freed_ports
    assert started_okx == ["okx"]
    assert started_api[0]["data_dir"] == tmp_path / "stack-data"
    assert started_api[0]["actionable_staging_enabled"] is True
    assert f"{start.smoke.MOCK_OKX_BASE}/health" in health_checks
    data = json.loads((tmp_path / "pids.json").read_text(encoding="utf-8"))
    assert data["mock_okx_pid"] == 3
    assert data["mock_okx"] == start.smoke.MOCK_OKX_BASE
    assert data["market_provider"] == "okx_public"
    assert data["macro_event_provider"] == "no_active_event"
    assert data["real_market_enabled"] is False
    assert data["actionable_staging_enabled"] is True
    assert data["manual_execution_required"] is True
    assert data["auto_order_enabled"] is False


def test_start_local_stack_can_start_error_internal_api_for_frontend(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    freed_ports: list[int] = []
    health_checks: list[str] = []
    frontend_calls: list[dict[str, object]] = []
    started_error_api: list[str] = []

    class Process:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_wait_for_json(url, name, *args, **kwargs):
        health_checks.append(url)
        if url.endswith("/api/system/config"):
            return {
                "data": {
                    "decision": {"engine": "fixture"},
                    "market_data": {"provider": "fixture"},
                    "macro_event": {"provider": "disabled"},
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                }
            }
        return {"ok": True}

    monkeypatch.setattr(start.smoke, "_ensure_port_free", lambda port: freed_ports.append(port))
    monkeypatch.setattr(start, "_start_mock_error_api_detached", lambda: started_error_api.append("error-api") or Process(4), raising=False)
    monkeypatch.setattr(start, "_start_api_detached", lambda **kwargs: Process(1))
    monkeypatch.setattr(start, "_start_frontend_detached", lambda **kwargs: frontend_calls.append(kwargs) or Process(2))
    monkeypatch.setattr(start.smoke, "_wait_for_json", fake_wait_for_json)
    monkeypatch.setattr(start.smoke, "_wait_for_text", lambda *args, **kwargs: "__next Crypto")
    monkeypatch.setattr(start.smoke, "_assert_cors_preflight", lambda: None)
    monkeypatch.setattr(start.smoke, "_assert_frontend_page", lambda path: None)
    monkeypatch.setattr(start.shutil, "rmtree", lambda *args, **kwargs: None)
    monkeypatch.setattr(start, "PID_FILE", tmp_path / "pids.json")
    monkeypatch.setattr(start, "LOG_DIR", tmp_path)

    assert start.main(["--data-dir", str(tmp_path / "stack-data"), "--with-error-internal-api"]) == 0

    assert start.smoke.MOCK_ERROR_API_PORT in freed_ports
    assert started_error_api == ["error-api"]
    assert f"{start.smoke.MOCK_ERROR_API_BASE}/health" in health_checks
    assert frontend_calls[0]["internal_api_base_url"] == start.smoke.MOCK_ERROR_API_BASE
    data = json.loads((tmp_path / "pids.json").read_text(encoding="utf-8"))
    assert data["mock_error_api_pid"] == 4
    assert data["mock_error_api"] == start.smoke.MOCK_ERROR_API_BASE
    assert data["frontend_api_base_url"] == start.smoke.API_BASE
    assert data["api_base_embedded_in_frontend"] == start.smoke.API_BASE
    assert data["frontend_internal_api_base_url"] == start.smoke.MOCK_ERROR_API_BASE


def test_local_smoke_seed_mock_outcome_flag_runs_quality_assertions_and_reports_scope(
    monkeypatch,
    tmp_path,
    capsys,
):
    smoke = _load_script("smoke_local_stack.py")
    started_api: list[dict[str, object]] = []
    seeded: list[str] = []
    quality_checks: list[str] = []

    class Process:
        pid = 12345

        def poll(self):
            return None

    def fake_start_api(**kwargs):
        started_api.append(kwargs)
        return Process()

    def fake_wait_for_json(url, name, *args, **kwargs):
        if url.endswith("/api/system/config"):
            return {
                "data": {
                    "decision": {"engine": "fixture", "openai_model": ""},
                    "market_data": {"provider": "fixture"},
                    "macro_event": {"provider": "disabled"},
                    "trading": {
                        "manual_execution_required": True,
                        "auto_order_enabled": False,
                    },
                }
            }
        return {"ok": True}

    monkeypatch.setattr(smoke, "TMP_DIR", tmp_path)
    monkeypatch.setattr(smoke, "_ensure_port_free", lambda port: None)
    monkeypatch.setattr(smoke, "_start_api", fake_start_api)
    monkeypatch.setattr(smoke, "_start_frontend", lambda: Process())
    monkeypatch.setattr(smoke, "_wait_for_json", fake_wait_for_json)
    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: "__next Crypto 金融质量")
    monkeypatch.setattr(smoke, "_assert_cors_preflight", lambda: None)
    monkeypatch.setattr(smoke, "_assert_frontend_page", lambda path: None)
    monkeypatch.setattr(smoke, "_assert_manual_run", lambda: "trace-1")
    monkeypatch.setattr(smoke, "_assert_run_list_contains", lambda trace_id: None)
    monkeypatch.setattr(
        smoke,
        "_assert_run_detail",
        lambda trace_id: {"data": {"trace": {"allowed": False}}},
    )
    monkeypatch.setattr(smoke, "_assert_frontend_summary_page", lambda trace_id, allowed=False: None)
    monkeypatch.setattr(smoke, "_assert_frontend_agent_audit_page", lambda trace_id: None)
    monkeypatch.setattr(smoke, "_stop_process", lambda process: None)
    monkeypatch.setattr(
        smoke,
        "_seed_mock_eval_outcome",
        lambda data_dir: seeded.append(str(data_dir)) or {"decision_ref": "mocked-outcome-seed"},
    )
    monkeypatch.setattr(
        smoke,
        "_assert_eval_quality_outcome_visible",
        lambda: quality_checks.append("checked"),
    )

    assert smoke.main(["--seed-mock-outcome"]) == 0

    assert started_api[0]["data_dir"] == tmp_path / "data"
    assert seeded == [str(tmp_path / "data")]
    assert quality_checks == ["checked"]
    output = capsys.readouterr().out
    assert '"mock_outcome_seeded": true' in output
    assert '"mock_outcome_decision_ref": "mocked-outcome-seed"' in output
    assert '"mock_outcome_quality_scope": "visibility_only_not_financial_quality"' in output


def test_local_smoke_collect_outcomes_fixture_runs_collector_and_reports_scope(
    monkeypatch,
    tmp_path,
    capsys,
):
    smoke = _load_script("smoke_local_stack.py")
    started_api: list[dict[str, object]] = []
    collected: list[str] = []
    quality_checks: list[str] = []
    okx_started: list[str] = []

    class Process:
        pid = 12345

        def poll(self):
            return None

    def fake_start_api(**kwargs):
        started_api.append(kwargs)
        return Process()

    def fake_wait_for_json(url, name, *args, **kwargs):
        if url.endswith("/api/system/config"):
            return {
                "data": {
                    "decision": {"engine": "fixture", "openai_model": ""},
                    "market_data": {"provider": "okx_public"},
                    "macro_event": {"provider": "no_active_event"},
                    "trading": {
                        "manual_execution_required": True,
                        "auto_order_enabled": False,
                    },
                }
            }
        return {"ok": True}

    monkeypatch.setattr(smoke, "TMP_DIR", tmp_path)
    monkeypatch.setattr(smoke, "_ensure_port_free", lambda port: None)
    monkeypatch.setattr(smoke, "_start_mock_okx", lambda: okx_started.append("okx") or Process())
    monkeypatch.setattr(smoke, "_start_api", fake_start_api)
    monkeypatch.setattr(smoke, "_start_frontend", lambda: Process())
    monkeypatch.setattr(smoke, "_wait_for_json", fake_wait_for_json)
    monkeypatch.setattr(smoke, "_wait_for_text", lambda url, name: "__next Crypto 金融质量")
    monkeypatch.setattr(smoke, "_assert_cors_preflight", lambda: None)
    monkeypatch.setattr(smoke, "_assert_frontend_page", lambda path: None)
    monkeypatch.setattr(smoke, "_assert_manual_run", lambda: "trace-1")
    monkeypatch.setattr(smoke, "_assert_run_list_contains", lambda trace_id: None)
    monkeypatch.setattr(
        smoke,
        "_assert_run_detail",
        lambda trace_id: {"data": {"trace": {"allowed": True}}},
    )
    monkeypatch.setattr(smoke, "_assert_actionable_staging_detail", lambda detail: None)
    monkeypatch.setattr(smoke, "_assert_frontend_summary_page", lambda trace_id, allowed=False: None)
    monkeypatch.setattr(smoke, "_assert_frontend_agent_audit_page", lambda trace_id: None)
    monkeypatch.setattr(smoke, "_stop_process", lambda process: None)
    monkeypatch.setattr(
        smoke,
        "_collect_exchange_native_outcome_fixture",
        lambda data_dir: collected.append(str(data_dir)) or {"collected": 3, "skipped": 0, "limit": 5},
    )
    monkeypatch.setattr(
        smoke,
        "_assert_collected_exchange_outcome_visible",
        lambda: quality_checks.append("checked"),
    )

    assert smoke.main(["--collect-outcomes-fixture"]) == 0

    assert okx_started == ["okx"]
    assert started_api[0]["data_dir"] == tmp_path / "data"
    assert started_api[0]["real_market_enabled"] is True
    assert started_api[0]["actionable_staging_enabled"] is True
    assert collected == [str(tmp_path / "data")]
    assert quality_checks == ["checked"]
    output = capsys.readouterr().out
    assert '"outcome_collection_profile": "local_mock_okx_collector_wiring_only"' in output
    assert '"collected_exchange_native_outcomes": 3' in output
    assert '"real_financial_quality_proven": false' in output


def test_local_smoke_collect_outcomes_fixture_requires_exact_collected_refs():
    smoke = _load_script("smoke_local_stack.py")
    collected_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "collected": 3,
        "skipped": 0,
        "limit": 5,
        "collected_refs": [
            {
                "decision_ref": "smoke-collected-outcome-plan:legacy_final",
                "evaluation_target": "legacy_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": collected_at,
            },
            {
                "decision_ref": "smoke-collected-outcome-plan:swarm_candidate_final",
                "evaluation_target": "swarm_candidate_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": collected_at,
            },
            {
                "decision_ref": "smoke-collected-outcome-plan:hold_no_trade",
                "evaluation_target": "hold_no_trade",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": collected_at,
            },
        ],
    }

    smoke._assert_collect_outcomes_fixture_payload(payload, plan_id="smoke-collected-outcome-plan")

    stale_contract = {**payload, "collected_refs": payload["collected_refs"][:2]}
    with pytest.raises(AssertionError, match="collected_refs mismatch"):
        smoke._assert_collect_outcomes_fixture_payload(stale_contract, plan_id="smoke-collected-outcome-plan")


def test_start_local_stack_can_start_mock_openai_server(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []

    class Process:
        pid = 23456

    def fake_popen_detached(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    monkeypatch.setattr(start, "_popen_detached", fake_popen_detached)

    process = start._start_mock_openai_detached()

    assert process.pid == 23456
    command = calls[0]["command"]
    assert command[:2] == [sys.executable, str(start.ROOT / "tools" / "local_stack" / "mock_openai_server.py")]
    assert "--port" in command
    assert str(start.smoke.MOCK_OPENAI_PORT) in command


def test_start_local_stack_can_start_mock_error_api_server(monkeypatch, tmp_path):
    start = _load_script("start_local_stack.py")
    calls: list[dict[str, object]] = []

    class Process:
        pid = 34567

    def fake_popen_detached(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Process()

    monkeypatch.setattr(start, "_popen_detached", fake_popen_detached)

    process = start._start_mock_error_api_detached()

    assert process.pid == 34567
    command = calls[0]["command"]
    assert command[:2] == [sys.executable, str(start.ROOT / "tools" / "local_stack" / "mock_error_api_server.py")]
    assert "--port" in command
    assert str(start.smoke.MOCK_ERROR_API_PORT) in command


def test_stop_local_stack_discovers_listening_port_pids(monkeypatch):
    stop = _load_script("stop_local_stack.py")

    class Result:
        stdout = "123\nnot-a-pid\n456\n"

    def fake_run(command, **kwargs):
        return Result()

    monkeypatch.setattr(stop.subprocess, "run", fake_run)

    assert stop._pids_listening_on_port(8010) == [123, 456]


def test_stop_local_stack_covers_mock_okx_port():
    stop = _load_script("stop_local_stack.py")

    assert 8012 in stop.PORTS


def test_stop_local_stack_covers_mock_error_api_port():
    stop = _load_script("stop_local_stack.py")

    assert 8013 in stop.PORTS


def test_stop_local_stack_kills_dependency_pids_from_pid_file(monkeypatch, tmp_path):
    stop = _load_script("stop_local_stack.py")
    killed: list[int] = []
    pid_file = tmp_path / "pids.json"
    pid_file.write_text(
        '{"api_pid": 123, "frontend_pid": 456, "mock_openai_pid": 789, "mock_okx_pid": 901, "mock_error_api_pid": 902}',
        encoding="utf-8",
    )

    monkeypatch.setattr(stop, "PID_FILE", pid_file)
    monkeypatch.setattr(stop, "_kill_tree", lambda pid: killed.append(pid))
    monkeypatch.setattr(sys, "argv", ["stop_local_stack.py"])

    assert stop.main() == 0

    assert killed == [456, 123, 789, 901, 902]
    assert not pid_file.exists()


def test_stop_local_stack_kills_posix_process_group(monkeypatch):
    stop = _load_script("stop_local_stack.py")
    calls: list[tuple[str, int, int]] = []

    def fake_getpgid(pid):
        calls.append(("getpgid", pid, 0))
        return 555

    def fake_killpg(pgid, sig):
        calls.append(("killpg", pgid, sig))

    def fake_run(command, **kwargs):
        calls.append(("run", int(command[-1]), 0))

    monkeypatch.setattr(stop.os, "name", "posix")
    monkeypatch.setattr(stop.os, "getpgid", fake_getpgid, raising=False)
    monkeypatch.setattr(stop.os, "killpg", fake_killpg, raising=False)
    monkeypatch.setattr(stop.subprocess, "run", fake_run)

    stop._kill_tree(12345)

    if os.name == "nt":
        assert ("run", 12345, 0) in calls
    else:
        assert ("getpgid", 12345, 0) in calls
        assert ("killpg", 555, signal.SIGTERM) in calls


def test_stop_local_stack_force_ports_does_not_kill_unowned_listener_by_default(monkeypatch, tmp_path):
    stop = _load_script("stop_local_stack.py")
    killed: list[int] = []

    monkeypatch.setattr(stop, "PID_FILE", tmp_path / "missing-pids.json")
    monkeypatch.setattr(stop, "_pids_listening_on_port", lambda port: [123])
    monkeypatch.setattr(stop, "_kill_tree", lambda pid: killed.append(pid))
    monkeypatch.setattr(sys, "argv", ["stop_local_stack.py", "--force-ports"])

    assert stop.main() == 0

    assert killed == []


def test_stop_local_stack_kill_any_listener_requires_explicit_flag(monkeypatch, tmp_path):
    stop = _load_script("stop_local_stack.py")
    killed: list[int] = []

    monkeypatch.setattr(stop, "PID_FILE", tmp_path / "missing-pids.json")
    monkeypatch.setattr(stop, "_pids_listening_on_port", lambda port: [123])
    monkeypatch.setattr(stop, "_kill_tree", lambda pid: killed.append(pid))
    monkeypatch.setattr(stop, "_wait_port_closed", lambda port, timeout=5.0: True)
    monkeypatch.setattr(sys, "argv", ["stop_local_stack.py", "--force-ports", "--kill-any-listener"])

    assert stop.main() == 0

    assert killed == [123] * len(stop.PORTS)
