from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEAD_PACKAGE = ROOT / "src" / "crypto_manual_alert" / "lead"
ORCHESTRATION_PACKAGE = ROOT / "src" / "crypto_manual_alert" / "orchestration"
SRC_PACKAGE = ROOT / "src" / "crypto_manual_alert"

FORBIDDEN_LEAD_IMPORTS = {
    "crypto_manual_alert.agent_swarm.contracts",
    "crypto_manual_alert.agent_swarm.runtime",
    "crypto_manual_alert.agent_swarm.shadow_runner",
}


def test_lead_package_does_not_import_agent_swarm_contracts_or_runtime():
    imported_source = "\n".join(path.read_text(encoding="utf-8") for path in LEAD_PACKAGE.glob("*.py"))

    for forbidden in FORBIDDEN_LEAD_IMPORTS:
        assert forbidden not in imported_source


def test_orchestration_contracts_do_not_import_agent_swarm_runtime():
    imported_source = "\n".join(
        (ORCHESTRATION_PACKAGE / name).read_text(encoding="utf-8")
        for name in ("contracts.py", "runtime.py", "harness.py")
    )

    assert "crypto_manual_alert.agent_swarm" not in imported_source


def test_internal_source_does_not_depend_on_agent_swarm_compatibility_paths():
    forbidden = {
        "crypto_manual_alert.agent_swarm.contracts",
        "crypto_manual_alert.agent_swarm.harness",
        "crypto_manual_alert.agent_swarm.shadow_failure",
    }
    allowed = {
        SRC_PACKAGE / "agent_swarm" / "__init__.py",
        SRC_PACKAGE / "agent_swarm" / "contracts.py",
        SRC_PACKAGE / "agent_swarm" / "harness.py",
        SRC_PACKAGE / "agent_swarm" / "shadow_failure.py",
    }

    offenders: list[str] = []
    for path in SRC_PACKAGE.rglob("*.py"):
        if path in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        for import_path in forbidden:
            if import_path in source:
                offenders.append(f"{path.relative_to(ROOT)} imports {import_path}")

    assert offenders == []
