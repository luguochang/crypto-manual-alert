from __future__ import annotations

import sys

from crypto_manual_alert.agent_swarm import ControlledAgentPoolRunner, ShadowSwarmRunner
from crypto_manual_alert.agent_swarm.shadow_orchestration import run_shadow_swarm_audit
from crypto_manual_alert.orchestration.harness import (
    HarnessPolicy,
    load_harness_policy,
    validate_agent_contributions,
)
from crypto_manual_alert.agent_swarm.contracts import SubTask as CompatSubTask
from crypto_manual_alert.agent_swarm.harness import HarnessPolicy as CompatHarnessPolicy
from crypto_manual_alert.agent_swarm.llm_tool_worker import LlmToolShadowWorker
from crypto_manual_alert.agent_swarm.registry import WorkerImplementationRegistry
from crypto_manual_alert.agent_swarm.shadow_llm_client import FixtureLlmShadowClient
from crypto_manual_alert.agent_swarm.shadow_runner import build_default_lead_plan
from crypto_manual_alert.agent_swarm.tool_executor import FixtureShadowToolExecutor
from crypto_manual_alert.agent_swarm.local_workers import RootCauseLocalWorker
from crypto_manual_alert.agent_swarm.workers import RootCauseLocalWorker as CompatRootCauseLocalWorker
from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.agent_swarm.shadow_runner import ShadowSwarmRunner as PackageShadowSwarmRunner


def test_agent_swarm_package_import_does_not_eagerly_import_implementation_modules():
    implementation_modules = [
        "crypto_manual_alert.agent_swarm.contracts",
        "crypto_manual_alert.agent_swarm.pool_runner",
        "crypto_manual_alert.agent_swarm.runtime",
        "crypto_manual_alert.agent_swarm.shadow_runner",
    ]
    previous_modules = {name: sys.modules.pop(name, None) for name in implementation_modules}
    sys.modules.pop("crypto_manual_alert.agent_swarm", None)
    try:
        __import__("crypto_manual_alert.agent_swarm")

        for name in implementation_modules:
            assert name not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.agent_swarm", None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module


def test_controlled_swarm_contracts_preserve_canonical_import_and_no_side_effect_request():
    subtask = SubTask(
        task_id="shadow:RootCauseAgent",
        agent_name="RootCauseAgent",
        role="root_cause_analysis",
        input_ref="trace:trace-1:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:RootCauseAgent",
        requested_tools=("web_search",),
    )

    request = subtask.to_agent_run_request(run_id="shadow:trace-1")

    assert ShadowSwarmRunner is PackageShadowSwarmRunner
    assert ShadowSwarmRunner is PackageShadowSwarmRunner
    assert ControlledAgentPoolRunner.__name__ == "ControlledAgentPoolRunner"
    assert RootCauseLocalWorker.__name__ == "RootCauseLocalWorker"
    assert FixtureLlmShadowClient.__name__ == "FixtureLlmShadowClient"
    assert FixtureShadowToolExecutor.__name__ == "FixtureShadowToolExecutor"
    assert WorkerImplementationRegistry.__name__ == "WorkerImplementationRegistry"
    assert LlmToolShadowWorker.__name__ == "LlmToolShadowWorker"
    assert build_default_lead_plan.__name__ == "build_default_lead_plan"
    assert CompatRootCauseLocalWorker is RootCauseLocalWorker
    assert request.decision_effect == "none"
    assert request.requested_tools == ("web_search",)
    assert request.input_view == {"symbol": "ETH-USDT-SWAP"}


def test_agent_swarm_compatibility_wrappers_reexport_canonical_objects():
    assert CompatSubTask is SubTask
    assert CompatHarnessPolicy is HarnessPolicy


def test_agent_swarm_harness_uses_canonical_imports():
    assert HarnessPolicy.__name__ == "HarnessPolicy"
    assert load_harness_policy.__name__ == "load_harness_policy"
    assert validate_agent_contributions.__name__ == "validate_agent_contributions"


def test_agent_swarm_shadow_orchestration_uses_canonical_imports():
    assert run_shadow_swarm_audit.__name__ == "run_shadow_swarm_audit"
