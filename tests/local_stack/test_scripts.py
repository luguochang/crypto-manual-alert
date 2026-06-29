from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LOCAL_STACK_TOOLS = ROOT / "tools" / "local_stack"


def _load_script(name: str):
    path = LOCAL_STACK_TOOLS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_smoke_api_env_disables_notification_by_default(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=False,
        base_env={"BARK_DEVICE_KEY": "device-key", "NOTIFICATION_ENABLED": "true"},
    )

    assert env["NOTIFICATION_ENABLED"] == "false"
    assert env["PYTHONPATH"].endswith("src")
    assert env["TMP"] == str(tmp_path)


def test_local_smoke_api_env_requires_bark_key_when_enabled(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(RuntimeError, match="BARK_DEVICE_KEY"):
        smoke._build_api_env(tmp_dir=tmp_path, notification_enabled=True, base_env={})


def test_local_smoke_api_env_enables_real_bark_when_key_is_present(tmp_path):
    smoke = _load_script("smoke_local_stack.py")

    env = smoke._build_api_env(
        tmp_dir=tmp_path,
        notification_enabled=True,
        base_env={"BARK_DEVICE_KEY": "device-key"},
    )

    assert env["NOTIFICATION_ENABLED"] == "true"
    assert env["BARK_DEVICE_KEY"] == "device-key"


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
                            {"name": "manual_api"},
                            {"name": "legacy_baseline"},
                            {"name": "shadow_swarm_audit"},
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


def test_local_smoke_rejects_missing_agent_audit_view():
    smoke = _load_script("smoke_local_stack.py")

    with pytest.raises(AssertionError, match="agent_audit_view"):
        smoke._assert_agent_audit_view({"data": {"plan_run": {}}})


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
