from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app


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
        "macro_event", "eval", "security",
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

    # bark key 必须脱敏，不返回原文
    assert data["notification"]["bark_device_key_value"] in {"<redacted>", "<unset>"}
    assert "secret_env_names" in data["security"]
