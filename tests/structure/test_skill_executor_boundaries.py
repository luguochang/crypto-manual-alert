from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_llm_tool_worker_accepts_only_skill_requests_in_main_path():
    source = (ROOT / "src/crypto_manual_alert/agent_swarm/llm_tool_worker.py").read_text(encoding="utf-8")

    assert '"skill_requests"' in source
    assert '"tool_requests"' not in source
    assert "tool_name" not in source
    assert "tool_audit_results" not in source
    assert "ShadowToolExecutor" not in source


def test_replay_manifest_does_not_project_legacy_tool_audit_results():
    source = (ROOT / "src/crypto_manual_alert/decision/replay_worker_refs.py").read_text(encoding="utf-8")

    assert "tool_call_artifact_refs" in source
    assert "tool_audit_result_refs" not in source
    assert "tool_audit_results" not in source
    assert "error_message" not in source


def test_agent_audit_projection_does_not_project_legacy_tool_audit_results():
    source = (ROOT / "src/crypto_manual_alert/storage/agent_audit_view.py").read_text(encoding="utf-8")

    assert "tool_call_artifact_refs" in source
    assert "tool_audit_results" not in source
