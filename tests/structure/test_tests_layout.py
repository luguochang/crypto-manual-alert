from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = ROOT / "tests"
LOCAL_STACK_TOOLS = ROOT / "tools" / "local_stack"

ALLOWED_TESTS_ROOT_ENTRIES = {
    "README.md",
    "__pycache__",
    "agent_swarm",
    "api",
    "artifacts",
    "cli",
    "config",
    "context",
    "decision",
    "deployment",
    "eval",
    "fixtures",
    "lead",
    "local_stack",
    "market",
    "market_agents",
    "notification",
    "research_pipeline",
    "skills",
    "storage",
    "structure",
    "telemetry",
    "workflow",
}

LOCAL_STACK_SCRIPT_NAMES = {
    "run_local_checks.py",
    "smoke_local_stack.py",
    "start_local_stack.py",
    "stop_local_stack.py",
}

ROOT_SCRIPT_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".sh"}


def test_tests_root_contains_only_grouping_directories_and_readme():
    entries = {path.name for path in TESTS_ROOT.iterdir()}

    assert entries <= ALLOWED_TESTS_ROOT_ENTRIES


def test_tests_root_does_not_contain_python_files():
    root_python_files = sorted(path.name for path in TESTS_ROOT.glob("*.py"))

    assert root_python_files == []


def test_project_root_does_not_contain_loose_scripts():
    loose_scripts = sorted(
        path.name
        for path in ROOT.iterdir()
        if path.is_file() and path.suffix.lower() in ROOT_SCRIPT_SUFFIXES
    )

    assert loose_scripts == []


def test_local_stack_scripts_live_under_tools():
    script_names = {path.name for path in LOCAL_STACK_TOOLS.glob("*.py")}

    assert LOCAL_STACK_SCRIPT_NAMES <= script_names
    assert not any((TESTS_ROOT / name).exists() for name in LOCAL_STACK_SCRIPT_NAMES)
