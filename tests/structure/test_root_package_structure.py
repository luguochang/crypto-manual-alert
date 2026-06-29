from __future__ import annotations

import ast
from pathlib import Path


ROOT_PACKAGE = Path("src/crypto_manual_alert")

ROOT_IMPLEMENTATION_MODULES = {
    "__init__.py",
}

ROOT_INFRASTRUCTURE_PACKAGES = {
    "cli",
    "config",
    "domain",
}

INFRASTRUCTURE_PACKAGE_FILES = {
    "cli": {"__init__.py", "__main__.py", "main.py"},
    "config": {"__init__.py", "final_input_switch_review.py", "loader.py", "models.py"},
    "domain": {"__init__.py", "decision.py", "market.py", "notification.py", "risk.py"},
}


def test_root_package_does_not_contain_business_modules():
    root_modules = {path.name for path in ROOT_PACKAGE.glob("*.py")}

    assert root_modules == ROOT_IMPLEMENTATION_MODULES


def test_root_package_init_does_not_import_business_modules():
    tree = ast.parse((ROOT_PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]

    assert imports == []


def test_root_infrastructure_modules_are_packages():
    package_names = {
        path.name
        for path in ROOT_PACKAGE.iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    }

    assert ROOT_INFRASTRUCTURE_PACKAGES <= package_names


def test_root_infrastructure_package_files_are_explicitly_classified():
    for package_name, expected_files in INFRASTRUCTURE_PACKAGE_FILES.items():
        package_dir = ROOT_PACKAGE / package_name
        python_files = {path.name for path in package_dir.glob("*.py")}

        assert python_files == expected_files


def test_root_infrastructure_package_entries_are_lightweight():
    forbidden_nodes = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for package_name in ROOT_INFRASTRUCTURE_PACKAGES:
        init_path = ROOT_PACKAGE / package_name / "__init__.py"
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
        forbidden_defs = [
            node.name
            for node in tree.body
            if isinstance(node, forbidden_nodes)
        ]

        assert forbidden_defs == []


def test_cli_package_keeps_module_entrypoint():
    assert (ROOT_PACKAGE / "cli" / "__main__.py").exists()
