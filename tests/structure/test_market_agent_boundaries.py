from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "crypto_manual_alert"
MARKET_AGENTS = PACKAGE_ROOT / "market_agents"
AGENT_SWARM = PACKAGE_ROOT / "agent_swarm"
LEAD = PACKAGE_ROOT / "lead"
DECISION = PACKAGE_ROOT / "decision"
ORCHESTRATION = PACKAGE_ROOT / "orchestration"
SKILLS = PACKAGE_ROOT / "skills"


def _python_files(package: Path) -> list[Path]:
    return sorted(path for path in package.rglob("*.py") if path.is_file())


def _source(package: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8-sig") for path in _python_files(package))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_market_agents_package_exists_as_business_worker_owner():
    required = {
        "__init__.py",
        "registry.py",
    }

    for filename in required:
        assert (MARKET_AGENTS / filename).exists()


def test_market_agents_do_not_import_workflow_side_effect_or_final_engine():
    forbidden_imports = {
        "crypto_manual_alert.workflow",
        "crypto_manual_alert.notification",
        "crypto_manual_alert.storage.journal",
        "crypto_manual_alert.decision.final_engine",
        "crypto_manual_alert.decision.final_decision_step",
    }

    offenders: list[str] = []
    for path in _python_files(MARKET_AGENTS):
        imports = _imports(path)
        for forbidden in forbidden_imports:
            if any(item == forbidden or item.startswith(f"{forbidden}.") for item in imports):
                offenders.append(f"{path.relative_to(ROOT)} imports {forbidden}")

    assert offenders == []


def test_agent_swarm_runtime_imports_only_market_agent_registry_entrypoint():
    allowed_market_import = "crypto_manual_alert.market_agents.registry"
    offenders: list[str] = []

    for path in _python_files(AGENT_SWARM):
        if "local_workers" in path.parts:
            continue
        imports = _imports(path)
        for item in imports:
            if not item.startswith("crypto_manual_alert.market_agents"):
                continue
            if item != allowed_market_import:
                offenders.append(f"{path.relative_to(ROOT)} imports {item}")

    assert offenders == []


def test_agent_swarm_registry_no_longer_imports_concrete_business_workers():
    source = (AGENT_SWARM / "registry.py").read_text(encoding="utf-8")

    assert "from crypto_manual_alert.market_agents.registry import" in source
    assert "crypto_manual_alert.agent_swarm.local_workers" not in source
    assert "RootCauseLocalWorker" not in source
    assert "MarketSentimentLocalWorker" not in source
    assert "DataQualityLocalWorker" not in source
    assert "ExecutionRiskLocalWorker" not in source


def test_lead_decision_and_orchestration_do_not_import_concrete_market_agents():
    checked_packages = (LEAD, DECISION, ORCHESTRATION)
    offenders: list[str] = []
    for package in checked_packages:
        for path in _python_files(package):
            imports = _imports(path)
            for item in imports:
                if item.startswith("crypto_manual_alert.market_agents.") and item != "crypto_manual_alert.market_agents.registry":
                    offenders.append(f"{path.relative_to(ROOT)} imports {item}")

    assert offenders == []


def test_decision_package_does_not_import_worker_runtime_or_skills():
    forbidden = {
        "crypto_manual_alert.agent_swarm",
        "crypto_manual_alert.market_agents",
        "crypto_manual_alert.skills",
    }
    offenders: list[str] = []

    for path in _python_files(DECISION):
        imports = _imports(path)
        for item in imports:
            for forbidden_prefix in forbidden:
                if item == forbidden_prefix or item.startswith(f"{forbidden_prefix}."):
                    offenders.append(f"{path.relative_to(ROOT)} imports {item}")

    assert offenders == []


def test_skills_do_not_return_agent_contributions_or_lead_synthesis():
    source = _source(SKILLS)

    forbidden_tokens = {
        "AgentContribution",
        "LeadSynthesis",
        "LeadAgent",
        "build_lead_synthesis",
    }
    for token in forbidden_tokens:
        assert token not in source
