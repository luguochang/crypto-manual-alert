from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib
from typing import Any

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import Field
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "crypto_alert_v2.agents.research_harness_selection"


def _load_harness_module() -> Any:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name != MODULE_NAME:
            raise
        raise AssertionError(
            "CAPABILITY GAP [task-13-research-harness]: the restricted official "
            "Deep Agents harness module does not exist"
        ) from exc


def test_deepagents_stable_release_is_an_exact_runtime_dependency() -> None:
    project = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]

    assert "deepagents==0.6.12" in dependencies, (
        "CAPABILITY GAP [task-13-deepagents-dependency]: stable deepagents 0.6.12 "
        "is not locked as a production dependency"
    )
    try:
        installed = version("deepagents")
    except PackageNotFoundError as exc:
        raise AssertionError(
            "CAPABILITY GAP [task-13-deepagents-dependency]: deepagents is not "
            "installed in the locked backend environment"
        ) from exc
    assert installed == "0.6.12"


def test_deep_research_factory_uses_one_restricted_official_harness(
    monkeypatch: Any,
) -> None:
    harness = _load_harness_module()
    captured: dict[str, Any] = {}
    calls = {"deepagents": 0, "langchain": 0}

    class Sentinel:
        def with_retry(self, **kwargs: Any) -> "Sentinel":
            captured["retry"] = kwargs
            return self

    sentinel = Sentinel()

    def fake_register(key: str, profile: Any) -> None:
        captured["profile_key"] = key
        captured["profile"] = profile

    def fake_create_deep_agent(**kwargs: Any) -> Sentinel:
        calls["deepagents"] += 1
        captured["deep_kwargs"] = kwargs
        return sentinel

    def forbidden_create_agent(**_: Any) -> None:
        calls["langchain"] += 1
        raise AssertionError("fallback harness was activated with Deep Agents")

    monkeypatch.setattr(harness, "register_harness_profile", fake_register)
    monkeypatch.setattr(harness, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(harness, "create_agent", forbidden_create_agent)

    search_tool = object()
    model = object()
    result = harness.create_research_harness(
        model=model,
        verified_search_tool=search_tool,
        mode="deepagents",
    )

    assert result is sentinel
    assert calls == {"deepagents": 1, "langchain": 0}
    assert captured["profile_key"] == harness.DEEP_RESEARCH_PROFILE_KEY

    profile = captured["profile"]
    assert profile.general_purpose_subagent.enabled is False
    assert {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
    } <= set(profile.excluded_tools)
    task_description = profile.tool_description_overrides["task"]
    assert "exactly" in task_description
    assert "Never launch a second task" in task_description
    assert "concurrent" not in task_description
    assert "{available_agents}" in task_description

    kwargs = captured["deep_kwargs"]
    assert kwargs["model"] is model
    assert kwargs["tools"] == []
    assert type(kwargs["backend"]).__name__ == "StateBackend"
    assert isinstance(kwargs["response_format"], ToolStrategy)
    assert kwargs["response_format"].schema is harness.DeepResearchReport
    assert (
        kwargs["response_format"].handle_errors
        == harness.STRUCTURED_OUTPUT_REPAIR_MESSAGE
    )
    assert len(kwargs["subagents"]) == 1

    researcher = kwargs["subagents"][0]
    assert researcher["name"] == "verified-source-researcher"
    assert researcher["tools"] == [search_tool]
    assert researcher["model"] is model
    assert isinstance(researcher["response_format"], ToolStrategy)
    assert researcher["response_format"].schema is harness.ResearchSection
    assert (
        researcher["response_format"].handle_errors
        == harness.STRUCTURED_OUTPUT_REPAIR_MESSAGE
    )
    assert any(
        isinstance(item, ModelCallLimitMiddleware)
        and item.run_limit == harness.SUBAGENT_MODEL_CALL_LIMIT
        and item.exit_behavior == "error"
        for item in researcher["middleware"]
    )
    assert any(
        isinstance(item, ToolCallLimitMiddleware)
        and item.tool_name == harness.VERIFIED_SEARCH_TOOL_NAME
        and item.run_limit == harness.SEARCH_TOOL_CALL_LIMIT
        and item.exit_behavior == "error"
        for item in researcher["middleware"]
    )
    assert any(
        isinstance(item, ToolCallLimitMiddleware)
        and item.tool_name == "task"
        and item.run_limit == harness.SUBAGENT_DELEGATION_LIMIT
        and item.exit_behavior == "error"
        for item in kwargs["middleware"]
    )
    assert harness.SUBAGENT_DELEGATION_LIMIT == 1
    assert any(
        isinstance(item, harness.DisableParallelToolCallsMiddleware)
        for item in kwargs["middleware"]
    )
    assert any(
        isinstance(item, harness.DisableParallelToolCallsMiddleware)
        for item in researcher["middleware"]
    )
    assert "Call the task tool exactly once" in kwargs["system_prompt"]
    assert "exactly once with one to three queries" in researcher["system_prompt"]
    assert captured["retry"]["stop_after_attempt"] == 2

    permission_shapes = {
        (tuple(rule.operations), tuple(rule.paths), rule.mode)
        for rule in kwargs["permissions"]
    }
    assert (("read", "write"), ("/**",), "deny") in permission_shapes


def test_langchain_fallback_is_explicit_and_never_dual_active(
    monkeypatch: Any,
) -> None:
    harness = _load_harness_module()
    calls = {"deepagents": 0, "langchain": 0}
    captured: dict[str, Any] = {}

    class Sentinel:
        def with_retry(self, **kwargs: Any) -> "Sentinel":
            captured["retry"] = kwargs
            return self

    sentinel = Sentinel()

    def forbidden_deep_agent(**_: Any) -> None:
        calls["deepagents"] += 1
        raise AssertionError("Deep Agents was activated with fallback mode")

    def fake_create_agent(**kwargs: Any) -> Sentinel:
        calls["langchain"] += 1
        captured["fallback_kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(harness, "create_deep_agent", forbidden_deep_agent)
    monkeypatch.setattr(harness, "create_agent", fake_create_agent)

    search_tool = object()
    model = object()
    result = harness.create_research_harness(
        model=model,
        verified_search_tool=search_tool,
        mode="langchain",
    )

    assert result is sentinel
    assert calls == {"deepagents": 0, "langchain": 1}
    kwargs = captured["fallback_kwargs"]
    assert kwargs["model"] is model
    assert kwargs["tools"] == [search_tool]
    assert isinstance(kwargs["response_format"], ToolStrategy)
    assert kwargs["response_format"].schema is harness.DeepResearchReport
    assert (
        kwargs["response_format"].handle_errors
        == harness.STRUCTURED_OUTPUT_REPAIR_MESSAGE
    )
    assert any(
        isinstance(item, ModelCallLimitMiddleware)
        and item.run_limit == harness.FALLBACK_MODEL_CALL_LIMIT
        and item.exit_behavior == "error"
        for item in kwargs["middleware"]
    )
    assert any(
        isinstance(item, ToolCallLimitMiddleware)
        and item.tool_name == harness.VERIFIED_SEARCH_TOOL_NAME
        and item.run_limit == harness.SEARCH_TOOL_CALL_LIMIT
        and item.exit_behavior == "error"
        for item in kwargs["middleware"]
    )
    assert any(
        isinstance(item, harness.DisableParallelToolCallsMiddleware)
        for item in kwargs["middleware"]
    )
    assert captured["retry"]["stop_after_attempt"] == 2


def test_unknown_research_harness_mode_fails_closed() -> None:
    harness = _load_harness_module()

    try:
        harness.create_research_harness(
            model=object(),
            verified_search_tool=object(),
            mode="automatic",
        )
    except ValueError as exc:
        assert "unsupported research harness mode" in str(exc)
    else:
        raise AssertionError("an unknown research harness mode did not fail closed")


class _ToolCallingFakeModel(FakeMessagesListChatModel):
    bound_tool_names: list[tuple[str, ...]] = Field(default_factory=list)
    bound_model_settings: list[dict[str, Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ToolCallingFakeModel":
        self.bound_tool_names.append(
            tuple(
                name
                for tool in tools
                if (name := getattr(tool, "name", None)) is not None
            )
        )
        self.bound_model_settings.append(dict(kwargs))
        return self

    def _get_ls_params(self, **_: Any) -> dict[str, str]:
        return {"ls_provider": "openai", "ls_model_name": "controlled-test-model"}


@pytest.mark.asyncio
async def test_real_deep_agent_delegates_only_to_the_verified_researcher() -> None:
    harness = _load_harness_module()
    search_calls: list[list[str]] = []

    async def verified_web_search(queries: list[str]) -> str:
        search_calls.append(queries)
        return '[{"index":1,"title":"Verified source","excerpt":"Evidence"}]'

    search_tool = StructuredTool.from_function(
        coroutine=verified_web_search,
        name=harness.VERIFIED_SEARCH_TOOL_NAME,
        description="Return one verified indexed source.",
    )
    model = _ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Research one verified BTC source.",
                            "subagent_type": "verified-source-researcher",
                        },
                        "id": "task-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": harness.VERIFIED_SEARCH_TOOL_NAME,
                        "args": {"queries": ["BTC institutional adoption"]},
                        "id": "search-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ResearchSection",
                        "args": {
                            "title": "Institutional adoption",
                            "summary": "The verified source supports the finding.",
                            "findings": [
                                {
                                    "claim": "Institutional adoption continues.",
                                    "source_indexes": [1],
                                }
                            ],
                        },
                        "id": "section-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "DeepResearchReport",
                        "args": {
                            "executive_summary": "This first report needs repair.",
                            "sections": [],
                            "risk_notes": [],
                            "evidence_gaps": [],
                        },
                        "id": "invalid-report-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "DeepResearchReport",
                        "args": {
                            "executive_summary": "Adoption continues with uncertainty.",
                            "sections": [
                                {
                                    "title": "Institutional adoption",
                                    "summary": "The verified source supports the finding.",
                                    "findings": [
                                        {
                                            "claim": "Institutional adoption continues.",
                                            "source_indexes": [1],
                                        }
                                    ],
                                }
                            ],
                            "risk_notes": [],
                            "evidence_gaps": [],
                        },
                        "id": "report-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    )
    agent = harness.create_research_harness(
        model=model,
        verified_search_tool=search_tool,
        mode="deepagents",
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="Research BTC adoption.")]}
    )

    assert isinstance(result["structured_response"], harness.DeepResearchReport)
    assert search_calls == [["BTC institutional adoption"]]
    assert any("task" in tools for tools in model.bound_tool_names)
    assert any(
        harness.VERIFIED_SEARCH_TOOL_NAME in tools for tools in model.bound_tool_names
    )
    assert all("write_file" not in tools for tools in model.bound_tool_names)
    assert all("execute" not in tools for tools in model.bound_tool_names)
    assert model.bound_model_settings
    assert all(
        settings.get("parallel_tool_calls") is False
        for settings in model.bound_model_settings
    )
