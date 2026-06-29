from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path("src/crypto_manual_alert")
SKILLS_RUNTIME = PACKAGE_ROOT / "skills" / "runtime.py"
SKILLS_PACKAGE = PACKAGE_ROOT / "skills"
SKILLS_INIT = SKILLS_PACKAGE / "__init__.py"
SKILLS_FACADE = SKILLS_PACKAGE / "facade.py"
SKILLS_CONTRACTS = SKILLS_PACKAGE / "contracts.py"
SKILLS_CONTRACT_POLICY = SKILLS_PACKAGE / "contract_policy.py"
SKILLS_CONTRACT_VALIDATION = SKILLS_PACKAGE / "contract_validation.py"
BUSINESS_SKILL_PACKAGES = {
    "realtime_search": "RealtimeSearchSkill",
    "root_cause": "RootCauseSearchSkill",
    "sentiment_crowding": "MarketSentimentSkill",
    "macro_event": "MacroEventSkill",
    "liquidity_order_book": "LiquidityOrderBookSkill",
}
LEGACY_FINAL_ENGINE_EXPORTS = {
    "CommandDecisionEngine",
    "DecisionEngine",
    "FixtureDecisionEngine",
    "OpenAICompatibleDecisionEngine",
}
SKILL_CONTEXT_EXPORTS = {"SkillContext", "SkillInfo", "SkillRuntime"}


def test_skills_runtime_is_compatibility_export_only():
    source = SKILLS_RUNTIME.read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

    assert {
        "CommandDecisionEngine",
        "DecisionEngine",
        "FixtureDecisionEngine",
        "OpenAICompatibleDecisionEngine",
        "SkillContext",
        "SkillInfo",
        "SkillRuntime",
    }.isdisjoint(class_names)
    import_targets = _import_targets(SKILLS_RUNTIME, tree)
    assert "crypto_manual_alert.skills.context_loader" in import_targets
    assert "crypto_manual_alert.decision.final_engine" in import_targets
    assert (
        _from_import_names(SKILLS_RUNTIME, tree, "crypto_manual_alert.decision.final_engine")
        == LEGACY_FINAL_ENGINE_EXPORTS
    )
    assert set(_literal_assignment(tree, "__all__")) == LEGACY_FINAL_ENGINE_EXPORTS | SKILL_CONTEXT_EXPORTS


def test_skills_package_final_engine_exports_are_legacy_allowlist_only():
    source = SKILLS_INIT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    export_modules = _literal_assignment(tree, "_EXPORT_MODULES")
    import_targets = _import_targets(SKILLS_INIT, tree)

    final_engine_exports = {
        name
        for name, module_name in export_modules.items()
        if module_name == "crypto_manual_alert.decision.final_engine"
    }
    facade_exports = {
        name for name, module_name in export_modules.items() if module_name == "crypto_manual_alert.skills.facade"
    }

    assert final_engine_exports == LEGACY_FINAL_ENGINE_EXPORTS
    assert not any(_matches_module(target, "crypto_manual_alert.decision.final_engine") for target in import_targets)
    assert {
        "EvidenceCandidate",
        "LiquidityOrderBookSkill",
        "MacroEventSkill",
        "MarketSentimentSkill",
        "RealtimeSearchSkill",
        "RootCauseSearchSkill",
        "SkillConstraints",
        "SkillTaskContext",
        "SkillToolResult",
    }.issubset(facade_exports)


def test_internal_code_uses_canonical_skill_and_decision_engine_modules():
    allowed_compatibility_files = {
        SKILLS_INIT.as_posix(),
        SKILLS_RUNTIME.as_posix(),
    }
    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        path_name = path.as_posix()
        if path_name in allowed_compatibility_files:
            continue
        source = path.read_text(encoding="utf-8")
        if "crypto_manual_alert.skills.runtime" in source:
            offenders.append(path_name)

    assert offenders == []


def test_skill_facade_does_not_import_agents_or_final_decision_runtime():
    forbidden_imports = {
        "crypto_manual_alert.market_agents",
        "crypto_manual_alert.agent_swarm",
        "crypto_manual_alert.decision.final_engine",
        "crypto_manual_alert.workflow",
    }
    offenders: list[tuple[str, str]] = []
    scanned_files: set[str] = set()
    for path in SKILLS_PACKAGE.rglob("*.py"):
        if path.name in {"runtime.py", "__init__.py"}:
            continue
        scanned_files.add(path.as_posix())
        source = path.read_text(encoding="utf-8")
        import_targets = _import_targets(path, ast.parse(source))
        for forbidden in forbidden_imports:
            if any(_matches_module(target, forbidden) for target in import_targets):
                offenders.append((path.as_posix(), forbidden))
        if "AgentContribution" in source:
            offenders.append((path.as_posix(), "AgentContribution"))

    assert (SKILLS_PACKAGE / "facade.py").as_posix() in scanned_files
    assert offenders == []


def test_skill_facade_delegates_result_contracts_to_contract_module():
    assert SKILLS_CONTRACTS.exists()
    facade_source = SKILLS_FACADE.read_text(encoding="utf-8")
    contracts_source = SKILLS_CONTRACTS.read_text(encoding="utf-8")

    assert "from .contracts import" in facade_source
    for class_name in ("SkillTaskContext", "EvidenceCandidate", "SkillConstraints", "SkillToolResult"):
        assert f"class {class_name}" not in facade_source
        assert f"class {class_name}" in contracts_source


def test_business_skills_are_packaged_by_capability():
    facade_source = SKILLS_FACADE.read_text(encoding="utf-8")

    for package_name, class_name in BUSINESS_SKILL_PACKAGES.items():
        skill_module = SKILLS_PACKAGE / package_name / "skill.py"
        assert skill_module.exists(), f"missing business skill module: {skill_module.as_posix()}"
        skill_source = skill_module.read_text(encoding="utf-8")
        assert f"class {class_name}" in skill_source
        assert f"class {class_name}" not in facade_source
        assert f"from .{package_name}.skill import {class_name}" in facade_source


def test_skill_contracts_separate_policy_and_validation_helpers():
    assert SKILLS_CONTRACT_POLICY.exists()
    assert SKILLS_CONTRACT_VALIDATION.exists()
    contracts_source = SKILLS_CONTRACTS.read_text(encoding="utf-8")
    policy_source = SKILLS_CONTRACT_POLICY.read_text(encoding="utf-8")
    validation_source = SKILLS_CONTRACT_VALIDATION.read_text(encoding="utf-8")

    assert "from .contract_validation import" in contracts_source
    assert "from .contract_policy import" in contracts_source
    assert "_SKILL_CONTRACTS" not in contracts_source
    assert "_FORBIDDEN_PUBLIC_VALUE_TOKENS" not in contracts_source
    assert "_SKILL_CONTRACTS" in policy_source
    assert "_FORBIDDEN_PUBLIC_VALUE_TOKENS" in policy_source
    assert "def validate_skill_tool_result(" in validation_source


def test_skill_facade_does_not_use_dynamic_imports():
    offenders: list[tuple[str, str]] = []
    for path in SKILLS_PACKAGE.rglob("*.py"):
        if path.name in {"runtime.py", "__init__.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call_name in _dynamic_import_call_names(tree):
            offenders.append((path.as_posix(), call_name))

    assert offenders == []


def test_dynamic_import_guard_detects_importlib_aliases():
    tree = ast.parse(
        "\n".join(
            [
                "import importlib as il",
                "import builtins",
                "from importlib import import_module as im",
                "from importlib import *",
                "from builtins import __import__ as bi",
                "__import__('crypto_manual_alert.workflow')",
                "builtins.__import__('crypto_manual_alert.workflow')",
                "bi('crypto_manual_alert.workflow')",
                "il.import_module('crypto_manual_alert.workflow')",
                "im('crypto_manual_alert.workflow')",
                "import_module('crypto_manual_alert.workflow')",
                "getattr(importlib, 'import_module')('crypto_manual_alert.workflow')",
                "eval('__import__')('crypto_manual_alert.workflow')",
                "exec('import crypto_manual_alert.workflow')",
            ]
        )
    )

    assert _dynamic_import_call_names(tree) == {
        "__import__",
        "bi",
        "builtins.__import__",
        "il.import_module",
        "im",
        "import_module",
        "getattr(importlib, 'import_module')",
        "eval",
        "exec",
    }


def _import_targets(path: Path, tree: ast.AST) -> set[str]:
    module_name = _module_name(path)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from(module_name, node)
            if base:
                targets.add(base)
            for alias in node.names:
                targets.add(f"{base}.{alias.name}" if base else alias.name)
    return targets


def _from_import_names(path: Path, tree: ast.AST, module: str) -> set[str]:
    names: set[str] = set()
    current_module = _module_name(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if _resolve_import_from(current_module, node) == module:
            names.update(alias.name for alias in node.names)
    return names


def _module_name(path: Path) -> str:
    return ".".join(path.with_suffix("").relative_to("src").parts)


def _resolve_import_from(module_name: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""

    package_parts = module_name.split(".")[:-1]
    if node.level > len(package_parts) + 1:
        return node.module or ""

    keep_count = len(package_parts) - node.level + 1
    resolved_parts = package_parts[:keep_count]
    if node.module:
        resolved_parts.extend(node.module.split("."))
    return ".".join(resolved_parts)


def _matches_module(candidate: str, forbidden: str) -> bool:
    return candidate == forbidden or candidate.startswith(f"{forbidden}.")


def _dynamic_import_call_names(tree: ast.AST) -> set[str]:
    importlib_aliases = {"importlib"}
    builtins_aliases = {"builtins"}
    import_module_aliases: set[str] = set()
    builtin_import_aliases = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
                elif alias.name == "builtins":
                    builtins_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib" and node.level == 0:
                for alias in node.names:
                    if alias.name == "*":
                        import_module_aliases.add("import_module")
                    elif alias.name == "import_module":
                        import_module_aliases.add(alias.asname or alias.name)
            elif node.module == "builtins" and node.level == 0:
                for alias in node.names:
                    if alias.name == "*":
                        builtin_import_aliases.add("__import__")
                    elif alias.name == "__import__":
                        builtin_import_aliases.add(alias.asname or alias.name)

    call_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in builtin_import_aliases or func.id in import_module_aliases:
                call_names.add(func.id)
            elif func.id in {"eval", "exec"}:
                call_names.add(func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in importlib_aliases and func.attr == "import_module":
                call_names.add(f"{func.value.id}.{func.attr}")
            elif func.value.id in builtins_aliases and func.attr == "__import__":
                call_names.add(f"{func.value.id}.{func.attr}")
        elif isinstance(func, ast.Call) and _is_getattr_import_module_call(func, importlib_aliases):
            call_names.add(ast.unparse(func.func) + "(" + ", ".join(ast.unparse(arg) for arg in func.args) + ")")
    return call_names


def _is_getattr_import_module_call(node: ast.Call, importlib_aliases: set[str]) -> bool:
    if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
        return False
    if len(node.args) < 2:
        return False
    target, attr_name = node.args[0], node.args[1]
    return (
        isinstance(target, ast.Name)
        and target.id in importlib_aliases
        and isinstance(attr_name, ast.Constant)
        and attr_name.value == "import_module"
    )


def _literal_assignment(tree: ast.AST, name: str):
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing literal assignment: {name}")
