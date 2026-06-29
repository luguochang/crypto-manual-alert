from __future__ import annotations

from pathlib import Path


def test_shadow_swarm_does_not_own_pool_scheduling_internals():
    source = Path("src/crypto_manual_alert/agent_swarm/shadow_runner.py").read_text(encoding="utf-8")

    forbidden = {
        "ThreadPoolExecutor",
        "FutureTimeoutError",
        "validate_agent_run_request(",
    }

    for item in forbidden:
        assert item not in source


def test_shadow_runner_delegates_failure_envelopes_to_dedicated_module():
    runner_source = Path("src/crypto_manual_alert/agent_swarm/shadow_runner.py").read_text(encoding="utf-8")
    failure_module = Path("src/crypto_manual_alert/agent_swarm/shadow_worker_failures.py")

    assert failure_module.exists()
    assert "from crypto_manual_alert.agent_swarm.shadow_worker_failures import" in runner_source

    forbidden = {
        "class HarnessPreflightRejected",
        "def _failed_contribution(",
        "def _timeout_contribution(",
        "def _not_configured_contribution(",
        "def _hash_payload(",
        "hashlib",
        "json",
    }

    for item in forbidden:
        assert item not in runner_source
