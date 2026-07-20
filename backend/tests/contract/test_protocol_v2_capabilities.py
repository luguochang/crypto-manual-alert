from __future__ import annotations

import ast
import json
from importlib.metadata import distribution, version
from pathlib import Path
import subprocess
import sys
from typing import Annotated, Literal, get_args, get_origin, get_type_hints

from langchain_protocol import (
    Channel,
    Command,
    InputRespondMany,
    InputRespondOne,
    RunStartParams,
    StateForkParams,
)
from langgraph.stream import CheckpointsTransformer
from langgraph_api.validation import openapi as locked_agent_openapi
from pydantic import TypeAdapter, ValidationError
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_PACKAGE = REPOSITORY_ROOT / "frontend/package.json"
FRONTEND_LOCK = REPOSITORY_ROOT / "frontend/package-lock.json"
PROTOCOL_COMMAND_ADAPTER = TypeAdapter(Command)
CANONICAL_FIXED_CHANNELS = {
    "values",
    "updates",
    "messages",
    "tools",
    "lifecycle",
    "input",
    "checkpoints",
    "tasks",
    "custom",
}
IMPLEMENTED_SERVER_COMMANDS = {
    "run.start",
    "input.respond",
    "agent.getTree",
    "subscription.subscribe",
    "subscription.unsubscribe",
    "subscription.reconnect",
}


def test_deployed_graph_modules_register_official_checkpoint_transformer() -> None:
    from crypto_alert_v2.graph import create_graph
    from crypto_alert_v2.testing.multi_interrupt_fixture import (
        create_graph as create_fixture_graph,
    )

    assert create_graph().stream_transformers == (CheckpointsTransformer,)
    assert create_fixture_graph().stream_transformers == (CheckpointsTransformer,)


def _capability_gap(capability: str, detail: str) -> str:
    return f"CAPABILITY GAP [{capability}]: {detail}"


def _protocol_command_methods() -> set[str]:
    methods: set[str] = set()
    for command_variant in get_args(Command):
        method_type = get_type_hints(command_variant, include_extras=True)["method"]
        methods.update(get_args(method_type))
    return methods


def _protocol_fixed_channels() -> tuple[set[str], object | None]:
    fixed: set[str] = set()
    custom: object | None = None
    for channel_type in get_args(Channel):
        if get_origin(channel_type) is Literal:
            fixed.update(get_args(channel_type))
        elif get_origin(channel_type) is Annotated:
            custom = channel_type
    return fixed, custom


def _distribution_source(relative_path: str) -> Path:
    source_path = Path(distribution("langgraph-api").locate_file(relative_path))
    assert source_path.is_file(), _capability_gap(
        "agent-server-installation",
        f"locked langgraph-api source file is missing: {relative_path}.",
    )
    return source_path


def _assigned_string_set(source_path: Path, name: str) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if not isinstance(target, ast.Name) or target.id != name or value is None:
            continue
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "frozenset"
            and len(value.args) == 1
        ):
            value = value.args[0]
        resolved = ast.literal_eval(value)
        assert isinstance(resolved, (set, frozenset)), _capability_gap(
            "agent-server-source-contract", f"{name} is no longer a static set."
        )
        assert all(isinstance(item, str) for item in resolved)
        return set(resolved)
    raise AssertionError(
        _capability_gap(
            "agent-server-source-contract", f"could not locate {name} in {source_path}."
        )
    )


def _server_known_commands() -> set[str]:
    source = _distribution_source("langgraph_api/event_streaming/service.py")
    return _assigned_string_set(source, "_KNOWN_COMMANDS")


def _server_supported_channels() -> set[str]:
    source = _distribution_source("langgraph_api/event_streaming/constants.py")
    return _assigned_string_set(source, "SUPPORTED_CHANNELS")


def _openapi_fixed_channels() -> set[str]:
    schemas = locked_agent_openapi["components"]["schemas"]
    channel_schema = schemas["ProtocolChannel"]
    for variant in channel_schema.get("anyOf", []):
        values = variant.get("enum")
        if isinstance(values, list):
            return {item for item in values if isinstance(item, str)}
    raise AssertionError(
        _capability_gap(
            "agent-openapi-channels", "ProtocolChannel has no fixed-channel enum."
        )
    )


def _run_state_fork_dispatch_probe() -> dict[str, object]:
    script = """
import asyncio
import json
from langgraph_api.event_streaming.service import ThreadRunManager

async def main():
    manager = ThreadRunManager(
        thread_id="00000000-0000-4000-8000-000000000001",
        runs=object(),
        threads=object(),
    )
    response = await manager.handle_command(
        {
            "id": 73,
            "method": "state.fork",
            "params": {"checkpoint_id": "checkpoint-contract"},
        }
    )
    print(json.dumps(response, separators=(",", ":")))

asyncio.run(main())
"""
    environment = {
        "POSTGRES_URI": "postgresql://contract:contract@127.0.0.1:1/contract",
        "REDIS_URI": "redis://127.0.0.1:1/0",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT / "backend",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, _capability_gap(
        "state-fork-probe-runtime",
        "isolated Agent Server dispatch probe could not start: "
        f"{completed.stderr.strip()[:500]}",
    )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return payload


def test_protocol_v2_compatibility_group_is_locked_across_python_and_frontend() -> None:
    package_json = json.loads(FRONTEND_PACKAGE.read_text(encoding="utf-8"))
    package_lock = json.loads(FRONTEND_LOCK.read_text(encoding="utf-8"))
    expected_frontend = {
        "@langchain/langgraph-sdk": "1.9.25",
        "@langchain/protocol": "0.0.18",
        "@langchain/react": "1.0.26",
    }

    assert version("langchain-protocol") == "0.0.18", _capability_gap(
        "python-protocol-version",
        "generated Python protocol bindings drifted from 0.0.18.",
    )
    assert version("langgraph-api") == "0.11.1", _capability_gap(
        "agent-server-version", "Protocol contracts require langgraph-api==0.11.1."
    )
    assert version("langgraph-sdk") == "0.4.2", _capability_gap(
        "python-sdk-version", "Protocol contracts require langgraph-sdk==0.4.2."
    )
    for package_name, expected_version in expected_frontend.items():
        assert package_json["dependencies"][package_name] == expected_version, (
            _capability_gap(
                "frontend-protocol-version",
                f"package.json does not pin {package_name}=={expected_version}.",
            )
        )
        installed = package_lock["packages"][f"node_modules/{package_name}"]["version"]
        assert installed == expected_version, _capability_gap(
            "frontend-lock-version",
            f"package-lock resolves {package_name} to {installed}, expected "
            f"{expected_version}.",
        )


def test_canonical_protocol_declares_expected_commands_and_channels() -> None:
    expected_commands = IMPLEMENTED_SERVER_COMMANDS | {
        "input.inject",
        "state.get",
        "state.listCheckpoints",
        "state.fork",
    }
    assert _protocol_command_methods() == expected_commands, _capability_gap(
        "canonical-command-schema",
        "langchain-protocol 0.0.18 command methods changed.",
    )
    fixed_channels, custom_channel = _protocol_fixed_channels()
    assert fixed_channels == CANONICAL_FIXED_CHANNELS, _capability_gap(
        "canonical-channel-schema",
        f"fixed channels changed to {sorted(fixed_channels)}.",
    )
    assert custom_channel is not None, _capability_gap(
        "canonical-custom-channel", "custom:<name> channel support disappeared."
    )
    assert get_args(custom_channel) == (str, "custom:.+"), _capability_gap(
        "canonical-custom-channel",
        "custom channel pattern no longer matches the locked protocol schema.",
    )


@pytest.mark.parametrize(
    "command",
    [
        {
            "id": 1,
            "method": "run.start",
            "params": {
                "assistant_id": "crypto_analysis",
                "input": {"request": {"symbol": "BTC-USDT-SWAP"}},
                "metadata": {"task_id": "task-contract"},
            },
        },
        {
            "id": 2,
            "method": "input.respond",
            "params": {
                "namespace": [],
                "interrupt_id": "interrupt-review",
                "response": {"action": "approve"},
                "update": {"reviewed": True},
            },
        },
        {
            "id": 3,
            "method": "input.respond",
            "params": {
                "responses": [
                    {
                        "namespace": [],
                        "interrupt_id": "interrupt-root",
                        "response": {"action": "approve"},
                    },
                    {
                        "namespace": ["research"],
                        "interrupt_id": "interrupt-child",
                        "response": {"action": "reject"},
                    },
                ]
            },
        },
    ],
)
def test_supported_protocol_command_shapes_validate_against_official_bindings(
    command: dict[str, object],
) -> None:
    validated = PROTOCOL_COMMAND_ADAPTER.validate_python(command)
    assert validated["method"] == command["method"]


@pytest.mark.parametrize(
    "command",
    [
        {"id": 11, "method": "run.start", "params": {"assistant_id": "agent"}},
        {
            "id": 12,
            "method": "input.respond",
            "params": {"namespace": [], "response": "missing interrupt id"},
        },
        {"id": 13, "method": "run.cancel", "params": {}},
    ],
)
def test_malformed_or_non_protocol_commands_fail_schema_validation(
    command: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PROTOCOL_COMMAND_ADAPTER.validate_python(command)


def test_protocol_run_start_cannot_express_per_run_durability() -> None:
    run_start_fields = get_type_hints(RunStartParams, include_extras=True)
    assert set(run_start_fields) == {
        "assistant_id",
        "input",
        "config",
        "metadata",
    }, _capability_gap(
        "protocol-run-start-fields",
        "run.start field set drifted; re-evaluate durability admission semantics.",
    )
    assert "durability" not in run_start_fields


def test_agent_server_known_command_and_channel_implementation_is_explicit() -> None:
    assert _server_known_commands() == IMPLEMENTED_SERVER_COMMANDS, _capability_gap(
        "agent-server-command-support",
        "langgraph-api command implementation changed; update the compatibility ADR.",
    )
    assert _server_supported_channels() == CANONICAL_FIXED_CHANNELS, _capability_gap(
        "agent-server-channel-support",
        "runtime channel support no longer matches canonical fixed channels.",
    )


def test_checkpoint_channel_openapi_lag_remains_an_explicit_exception() -> None:
    runtime_channels = _server_supported_channels()
    openapi_channels = _openapi_fixed_channels()
    assert "checkpoints" in runtime_channels
    assert "checkpoints" in _protocol_fixed_channels()[0]
    assert openapi_channels == CANONICAL_FIXED_CHANNELS - {"checkpoints"}, (
        _capability_gap(
            "protocol-channel-openapi-exception",
            "the pinned OpenAPI channel enum changed; remove or revise the explicit "
            "checkpoints compatibility exception instead of silently drifting.",
        )
    )


def test_state_fork_is_declared_but_returns_the_known_unknown_command_exception() -> (
    None
):
    state_fork_fields = get_type_hints(StateForkParams, include_extras=True)
    assert "state.fork" in _protocol_command_methods()
    assert "checkpoint_id" in state_fork_fields
    assert "state.fork" not in _server_known_commands()

    response = _run_state_fork_dispatch_probe()

    assert response == {
        "type": "error",
        "id": 73,
        "error": "unknown_command",
        "message": "Unknown protocol command: state.fork",
    }, _capability_gap(
        "state-fork-compatibility-exception",
        "langgraph-api no longer returns the recorded unknown_command response; "
        "re-evaluate Product fork admission before changing this contract.",
    )


def test_single_and_batch_interrupt_shapes_remain_distinct() -> None:
    single_fields = get_type_hints(InputRespondOne, include_extras=True)
    batch_fields = get_type_hints(InputRespondMany, include_extras=True)
    assert {"namespace", "interrupt_id", "response"} <= set(single_fields)
    assert "responses" in batch_fields
    assert "interrupt_id" not in batch_fields
