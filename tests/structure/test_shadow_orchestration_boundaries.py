from __future__ import annotations

from pathlib import Path


AGENT_SWARM_PACKAGE = Path("src/crypto_manual_alert/agent_swarm")


def test_shadow_orchestration_uses_worker_registry_not_raw_worker_builder():
    source = Path("src/crypto_manual_alert/agent_swarm/shadow_orchestration.py").read_text(encoding="utf-8")

    assert "build_local_shadow_workers" not in source
    assert "build_shadow_worker_registry" not in source
    assert "crypto_manual_alert.orchestration.shadow_audit" in source


def test_agent_swarm_does_not_own_lead_planning_or_synthesis():
    imported_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in AGENT_SWARM_PACKAGE.glob("*.py")
    )

    assert "from crypto_manual_alert.lead.agent import LeadAgent" not in imported_source
    assert "LeadAgent(" not in imported_source
    assert ".synthesize(" not in imported_source
    assert "from crypto_manual_alert.lead_agent import" not in imported_source
    assert "from crypto_manual_alert.lead_synthesis import" not in imported_source


def test_shadow_orchestration_delegates_input_and_failure_payloads():
    source = Path("src/crypto_manual_alert/agent_swarm/shadow_orchestration.py").read_text(encoding="utf-8")

    assert "from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts" not in source
    assert "def _safe_worker_payload" not in source
    assert "def failed_shadow_swarm_audit" not in source


def test_orchestration_layer_owns_shadow_audit_entrypoint():
    source = Path("src/crypto_manual_alert/orchestration/shadow_audit.py").read_text(encoding="utf-8")

    assert "from crypto_manual_alert.lead.agent import LeadAgent" in source
    assert "build_shadow_worker_registry" in source
    assert "ShadowSwarmRunner" in source


def test_workflow_uses_orchestration_shadow_audit_not_agent_swarm_wrapper():
    source = Path("src/crypto_manual_alert/workflow/pre_final_orchestration.py").read_text(encoding="utf-8")

    assert "from crypto_manual_alert.orchestration.shadow_audit import run_shadow_swarm_audit" in source
    assert "from crypto_manual_alert.agent_swarm.shadow_orchestration import run_shadow_swarm_audit" not in source
