from __future__ import annotations

import sys

import crypto_manual_alert.workflow as workflow
from crypto_manual_alert.workflow.executor import RunExecutor
from crypto_manual_alert.workflow.legacy_decision_workflow import LegacyDecisionWorkflow
from crypto_manual_alert.workflow.market_context_step import load_market_context_step
from crypto_manual_alert.workflow.persistence_payload import build_plan_payload, run_context_for_audit
from crypto_manual_alert.workflow.pre_final_orchestration import run_pre_final_orchestration
from crypto_manual_alert.workflow.run_persistence_step import persist_run_result
from crypto_manual_alert.workflow.scheduler import JobLock, run_scheduler


def test_workflow_package_exports_legacy_chain_canonical_objects():
    assert LegacyDecisionWorkflow
    assert load_market_context_step
    assert run_pre_final_orchestration
    assert persist_run_result
    assert build_plan_payload
    assert run_context_for_audit
    assert JobLock
    assert run_scheduler
    assert workflow.RunExecutor is RunExecutor


def test_workflow_package_import_does_not_eagerly_import_scheduler_module():
    previous_scheduler = sys.modules.pop("crypto_manual_alert.workflow.scheduler", None)
    sys.modules.pop("crypto_manual_alert.workflow", None)
    try:
        __import__("crypto_manual_alert.workflow")

        assert "crypto_manual_alert.workflow.scheduler" not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.workflow", None)
        if previous_scheduler is not None:
            sys.modules["crypto_manual_alert.workflow.scheduler"] = previous_scheduler
