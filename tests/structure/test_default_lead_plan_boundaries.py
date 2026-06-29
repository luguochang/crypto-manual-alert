from __future__ import annotations

from pathlib import Path


AGENT_SWARM = Path("src/crypto_manual_alert/agent_swarm")
LEAD = Path("src/crypto_manual_alert/lead")
SHADOW_RUNNER = AGENT_SWARM / "shadow_runner.py"
COMPAT_DEFAULT_LEAD_PLAN = AGENT_SWARM / "default_lead_plan.py"
DEFAULT_LEAD_PLAN = LEAD / "default_plan.py"


def test_default_lead_plan_has_canonical_module():
    assert DEFAULT_LEAD_PLAN.exists()
    assert COMPAT_DEFAULT_LEAD_PLAN.exists()


def test_shadow_runner_delegates_default_lead_plan_builder():
    source = SHADOW_RUNNER.read_text(encoding="utf-8")

    assert "from crypto_manual_alert.lead.default_plan import build_default_lead_plan" in source
    assert "def build_default_lead_plan(" not in source
    assert "def _role_for_agent(" not in source


def test_canonical_default_lead_plan_module_delegates_planning_to_lead_agent():
    source = DEFAULT_LEAD_PLAN.read_text(encoding="utf-8")

    assert "def build_default_lead_plan(" in source
    assert "from crypto_manual_alert.lead.agent import LeadAgent" in source
    assert "LeadAgent(" in source
    assert "LeadPlan(" not in source
    assert "SubTask(" not in source
    assert "def _role_for_agent(" not in source
    assert "SHADOW_WORKER_AGENTS" not in source
    assert "ShadowSwarmRunner" not in source
    assert "ControlledAgentPoolRunner" not in source


def test_agent_swarm_default_lead_plan_is_compatibility_reexport_only():
    source = COMPAT_DEFAULT_LEAD_PLAN.read_text(encoding="utf-8")

    assert "from crypto_manual_alert.lead.default_plan import build_default_lead_plan" in source
    assert "def build_default_lead_plan(" not in source
    assert "LeadAgent" not in source
    assert "LeadPlan(" not in source
    assert "SubTask(" not in source
    assert "def _role_for_agent(" not in source
