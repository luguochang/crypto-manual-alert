import ast
import json
from pathlib import Path
import tomllib


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = BACKEND_ROOT / "src" / "crypto_alert_v2"
LANGGRAPH_CONFIG = BACKEND_ROOT / "langgraph.json"


def _canonical_source_files() -> list[Path]:
    return [
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if "graph/nodes" not in path.relative_to(SOURCE_ROOT).as_posix()
    ]


def test_agent_server_registers_only_graph_factory() -> None:
    config = json.loads(LANGGRAPH_CONFIG.read_text())
    assert config["graphs"] == {
        "crypto_analysis": "./src/crypto_alert_v2/graph/__init__.py:graph_factory"
    }


def test_production_graph_has_no_import_time_compiled_export() -> None:
    graph_source = (SOURCE_ROOT / "graph" / "graph.py").read_text()
    graph_package = (SOURCE_ROOT / "graph" / "__init__.py").read_text()

    assert "graph = create_graph()" not in graph_source
    assert "import graph" not in graph_package
    assert '__all__ = ["create_graph", "graph_factory"]' in graph_package


def test_unified_worker_is_the_only_executable_worker_surface() -> None:
    assert not (SOURCE_ROOT / "commands" / "worker.py").exists()
    worker_source = (SOURCE_ROOT / "workers" / "__main__.py").read_text()
    assert "create_agent_server_authorization_provider" in worker_source


def test_create_agent_is_owned_by_canonical_factories() -> None:
    owners: set[str] = set()
    for path in _canonical_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "langchain.agents":
                if any(alias.name == "create_agent" for alias in node.names):
                    owners.add(path.relative_to(SOURCE_ROOT).as_posix())

    assert owners == {
        "agents/market_analysis.py",
        "agents/research.py",
        "agents/research_harness_selection.py",
    }


def test_canonical_runtime_does_not_import_quarantined_legacy_nodes() -> None:
    forbidden = "crypto_alert_v2.graph.nodes"
    violations = [
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in _canonical_source_files()
        if forbidden in path.read_text()
    ]
    assert violations == []


def test_legacy_manual_json_graph_runtime_is_removed() -> None:
    assert not (SOURCE_ROOT / "graph" / "nodes").exists()


def test_canonical_agent_factories_do_not_parse_model_json_text() -> None:
    for relative_path in (
        "agents/market_analysis.py",
        "agents/research.py",
        "agents/research_harness_selection.py",
    ):
        source = (SOURCE_ROOT / relative_path).read_text()
        assert "json.loads" not in source
        assert "response_format=ToolStrategy" in source


def test_deep_agents_is_owned_only_by_the_explicit_task13_selector() -> None:
    active_deep_agent_imports = []
    for path in _canonical_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "deepagents":
                if any(alias.name == "create_deep_agent" for alias in node.names):
                    active_deep_agent_imports.append(
                        path.relative_to(SOURCE_ROOT).as_posix()
                    )

    assert active_deep_agent_imports == [
        "agents/research_harness_selection.py",
    ]


def test_task13_deep_agents_runtime_is_an_exact_release_dependency() -> None:
    project = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]

    assert [item for item in dependencies if item.startswith("deepagents")] == [
        "deepagents==0.6.12"
    ]
