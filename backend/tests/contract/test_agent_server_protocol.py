from __future__ import annotations

import ast
import inspect
import json
import os
from importlib.metadata import version
from pathlib import Path
from typing import Any, get_args

import httpx
from langgraph_api.validation import openapi as locked_agent_openapi
from langgraph_sdk.client import LangGraphClient, RunsClient
from langgraph_sdk.schema import Durability
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CUSTOM_APP_SOURCE = REPOSITORY_ROOT / "backend/src/crypto_alert_v2/http/app.py"
LIVE_OPT_IN = "TASK8_LIVE_AGENT_PROTOCOL"
LIVE_BASE_URL = "TASK8_LIVE_AGENT_SERVER_URL"
LIVE_AUTHORIZATION = "TASK8_LIVE_AGENT_SERVER_AUTHORIZATION"


def _capability_gap(capability: str, detail: str) -> str:
    return f"CAPABILITY GAP [{capability}]: {detail}"


def _literal_route_arguments(source_path: Path) -> dict[str, set[str]]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    routes: dict[str, set[str]] = {"add_api_route": set(), "mount": set()}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        call_name = node.func.attr
        if call_name not in routes or not node.args:
            continue
        path_argument = node.args[0]
        if isinstance(path_argument, ast.Constant) and isinstance(
            path_argument.value, str
        ):
            routes[call_name].add(path_argument.value)
    return routes


def _request_json(request: httpx.Request) -> dict[str, Any]:
    decoded = json.loads(request.content)
    assert isinstance(decoded, dict)
    return decoded


async def _record_runs_create(
    **create_kwargs: Any,
) -> tuple[httpx.Request, dict[str, Any]]:
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "run_id": "run-contract",
                "thread_id": "thread-contract",
                "assistant_id": "assistant-contract",
                "status": "pending",
            },
        )

    async with httpx.AsyncClient(
        base_url="https://agent-server.invalid",
        transport=httpx.MockTransport(handle),
    ) as http_client:
        client = LangGraphClient(http_client)
        result = await client.runs.create(
            "thread-contract",
            "assistant-contract",
            **create_kwargs,
        )

    assert len(requests) == 1
    assert isinstance(result, dict)
    return requests[0], result


def _live_headers() -> dict[str, str]:
    authorization = os.environ.get(LIVE_AUTHORIZATION, "").strip()
    return {"authorization": authorization} if authorization else {}


def _live_base_url() -> str:
    if os.environ.get(LIVE_OPT_IN) != "1":
        pytest.skip(
            "UNPROVED LIVE CAPABILITY: set "
            f"{LIVE_OPT_IN}=1 and {LIVE_BASE_URL} to inspect the merged Agent Server."
        )
    base_url = os.environ.get(LIVE_BASE_URL, "").strip().rstrip("/")
    if not base_url:
        pytest.fail(
            "LIVE PROBE SETUP FAILURE: live protocol testing was opted in, but "
            f"{LIVE_BASE_URL} is unset. No capability assertion was evaluated."
        )
    return base_url


async def _get_live_json(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    try:
        response = await client.get(path, headers=_live_headers())
    except httpx.TransportError as exc:
        pytest.fail(
            "LIVE CONNECTIVITY FAILURE: the opted-in Agent Server could not be "
            f"reached for {path} ({type(exc).__name__}). No capability assertion "
            "was evaluated."
        )
    if response.status_code != 200:
        pytest.fail(
            "LIVE PROBE SETUP FAILURE: Agent Server returned HTTP "
            f"{response.status_code} for {path}. Check probe authorization and "
            "server readiness; no capability assertion was evaluated."
        )
    payload = response.json()
    if not isinstance(payload, dict):
        pytest.fail(
            f"LIVE PROTOCOL SHAPE FAILURE: {path} did not return a JSON object."
        )
    return payload


def test_locked_python_agent_server_compatibility_versions() -> None:
    assert version("langgraph-api") == "0.11.1", _capability_gap(
        "agent-server-version",
        "Task 8 contracts were written for langgraph-api==0.11.1.",
    )
    assert version("langgraph-sdk") == "0.4.2", _capability_gap(
        "python-sdk-version",
        "Task 8 contracts were written for langgraph-sdk==0.4.2.",
    )


def test_locked_agent_openapi_exposes_official_routes_and_protocol_v2() -> None:
    paths = locked_agent_openapi.get("paths")
    assert isinstance(paths, dict), _capability_gap(
        "agent-openapi", "the locked langgraph-api package has no paths object."
    )
    required_operations = {
        ("/assistants", "post"),
        ("/threads", "post"),
        ("/runs", "post"),
        ("/threads/{thread_id}/runs", "post"),
        ("/threads/{thread_id}/commands", "post"),
        ("/threads/{thread_id}/stream/events", "post"),
    }
    missing = sorted(
        f"{method.upper()} {path}"
        for path, method in required_operations
        if not isinstance(paths.get(path), dict) or method not in paths[path]
    )
    assert not missing, _capability_gap(
        "official-agent-routes", f"locked OpenAPI is missing {missing}."
    )


def test_product_custom_app_is_namespaced_away_from_official_routes() -> None:
    routes = _literal_route_arguments(CUSTOM_APP_SOURCE)
    assert routes["mount"] == {"/app"}, _capability_gap(
        "product-route-isolation",
        "the Product FastAPI app must be mounted exactly once at /app.",
    )
    assert routes["add_api_route"] == {"/app/system/readiness"}, _capability_gap(
        "product-route-isolation",
        "custom outer routes must remain under /app and outside Agent routes.",
    )
    reserved_roots = ("/assistants", "/threads", "/runs")
    collisions = sorted(
        path
        for path in routes["mount"] | routes["add_api_route"]
        if path.startswith(reserved_roots)
    )
    assert not collisions, _capability_gap(
        "product-route-shadowing",
        f"custom app declarations collide with official roots: {collisions}.",
    )


def test_python_runs_create_exposes_checkpoint_command_and_durability_boundaries() -> (
    None
):
    parameters = inspect.signature(RunsClient.create).parameters
    for parameter_name in ("command", "checkpoint_id", "durability"):
        assert parameter_name in parameters, _capability_gap(
            "python-runs-create",
            f"langgraph-sdk RunsClient.create lacks {parameter_name}=.",
        )
        assert parameters[parameter_name].kind is inspect.Parameter.KEYWORD_ONLY, (
            _capability_gap(
                "python-runs-create",
                f"{parameter_name}= is no longer a keyword-only Runs API boundary.",
            )
        )
    assert set(get_args(Durability)) == {"sync", "async", "exit"}, _capability_gap(
        "runs-durability",
        "official Python SDK durability literals drifted from sync/async/exit.",
    )


@pytest.mark.parametrize("durability", ["sync", "exit"])
@pytest.mark.asyncio
async def test_python_sdk_serializes_explicit_runs_api_durability(
    durability: str,
) -> None:
    request, _ = await _record_runs_create(
        input={"request": {"symbol": "BTC-USDT-SWAP"}},
        durability=durability,
    )

    assert request.method == "POST"
    assert request.url.path == "/threads/thread-contract/runs"
    body = _request_json(request)
    assert body["durability"] == durability, _capability_gap(
        "runs-durability",
        f"official SDK did not serialize durability={durability!r} at top level.",
    )


@pytest.mark.asyncio
async def test_python_sdk_serializes_resume_as_an_official_command() -> None:
    command = {
        "resume": {"interrupt-review": {"action": "approve"}},
        "update": {"reviewed": True},
        "goto": "finalize",
    }
    request, _ = await _record_runs_create(
        command=command,
        durability="sync",
        multitask_strategy="reject",
    )

    body = _request_json(request)
    assert body["command"] == command, _capability_gap(
        "runs-resume-command",
        "resume/update/goto were not preserved in the official command field.",
    )
    assert "input" not in body
    assert body["durability"] == "sync"


@pytest.mark.asyncio
async def test_python_sdk_lifts_a_fork_checkpoint_to_top_level_json() -> None:
    checkpoint_id = "checkpoint-fork-contract"
    request, _ = await _record_runs_create(
        input={"request": {"symbol": "BTC-USDT-SWAP"}},
        checkpoint_id=checkpoint_id,
        config={"configurable": {"checkpoint_id": checkpoint_id}},
        durability="sync",
    )

    body = _request_json(request)
    assert body["checkpoint_id"] == checkpoint_id, _capability_gap(
        "runs-fork-checkpoint",
        "fork checkpoint was not serialized as top-level checkpoint_id.",
    )
    assert body["config"]["configurable"]["checkpoint_id"] == checkpoint_id
    assert "forkFrom" not in body


@pytest.mark.asyncio
async def test_live_merged_openapi_keeps_product_and_official_route_spaces() -> None:
    base_url = _live_base_url()
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(8.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        merged = await _get_live_json(client, "/openapi.json")
        try:
            product_readiness = await client.get(
                "/app/api/v2/readiness", headers=_live_headers()
            )
        except httpx.TransportError as exc:
            pytest.fail(
                "LIVE CONNECTIVITY FAILURE: the mounted Product readiness route "
                f"could not be reached ({type(exc).__name__}). No capability "
                "assertion was evaluated."
            )

    merged_paths = merged.get("paths")
    assert isinstance(merged_paths, dict), _capability_gap(
        "live-merged-openapi", "merged server schema has no paths object."
    )
    required_merged_paths = {
        "/assistants",
        "/threads",
        "/runs",
        "/threads/{thread_id}/commands",
        "/threads/{thread_id}/stream/events",
        "/app/system/readiness",
    }
    missing = sorted(required_merged_paths - set(merged_paths))
    assert not missing, _capability_gap(
        "live-route-coexistence", f"merged Agent Server is missing {missing}."
    )
    assert product_readiness.status_code in {200, 401, 403, 503}, _capability_gap(
        "live-product-mount",
        "GET /app/api/v2/readiness did not resolve to the mounted Product app; "
        f"received HTTP {product_readiness.status_code}.",
    )
