from __future__ import annotations

from pathlib import Path


AGENT_SWARM = Path("src/crypto_manual_alert/agent_swarm")
WORKERS = AGENT_SWARM / "workers.py"
REGISTRY = AGENT_SWARM / "registry.py"
LOCAL_WORKERS = AGENT_SWARM / "local_workers"
MARKET_AGENTS = Path("src/crypto_manual_alert/market_agents")


def test_market_agents_have_canonical_package_files_for_existing_shadow_workers():
    required = {
        "__init__.py",
        "common.py",
        "registry.py",
        "root_cause.py",
        "sentiment_crowding.py",
        "data_quality.py",
        "execution_risk.py",
    }

    for filename in required:
        assert (MARKET_AGENTS / filename).exists()


def test_local_workers_package_is_compatibility_export_only():
    forbidden_tokens = {
        "class RootCauseLocalWorker",
        "class MarketSentimentLocalWorker",
        "class DataQualityLocalWorker",
        "class ExecutionRiskLocalWorker",
        "def contribution(",
        "def claim(",
        "def mapping(",
        "def hash_payload(",
    }

    for path in LOCAL_WORKERS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in source, f"{path} still owns business logic: {token}"


def test_workers_module_is_compatibility_export_only():
    source = WORKERS.read_text(encoding="utf-8")

    assert "from .local_workers import" in source
    assert "class RootCauseLocalWorker" not in source
    assert "class MarketSentimentLocalWorker" not in source
    assert "class DataQualityLocalWorker" not in source
    assert "class ExecutionRiskLocalWorker" not in source
    assert "def _contribution(" not in source
    assert "def _hash_payload(" not in source


def test_worker_registry_uses_canonical_local_workers_path():
    source = REGISTRY.read_text(encoding="utf-8")

    assert "from crypto_manual_alert.market_agents.registry import" in source
    assert "from crypto_manual_alert.agent_swarm.local_workers import" not in source
    assert "from crypto_manual_alert.agent_swarm.workers import" not in source
