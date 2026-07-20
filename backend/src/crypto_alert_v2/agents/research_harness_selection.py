from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from deepagents import (
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import StateBackend
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from crypto_alert_v2.agents.retry import MODEL_TRANSPORT_RETRY_ERRORS
from crypto_alert_v2.agents.security import secret_redaction_middleware
from crypto_alert_v2.domain.deep_research import (
    CitedResearchFinding,
    DeepResearchReport,
    ResearchHarnessMode,
    ResearchSection,
)


DEEP_RESEARCH_PROFILE_KEY = "openai"
VERIFIED_SEARCH_TOOL_NAME = "verified_web_search"
SUBAGENT_MODEL_CALL_LIMIT = 6
MAIN_MODEL_CALL_LIMIT = 8
FALLBACK_MODEL_CALL_LIMIT = 8
SEARCH_TOOL_CALL_LIMIT = 1
SUBAGENT_DELEGATION_LIMIT = 1
STRUCTURED_OUTPUT_REPAIR_MESSAGE = (
    "The structured result did not satisfy the required schema. Correct only the "
    "typed fields using the already collected verified source indexes, then return "
    "the structured result again. Do not call another task or search tool."
)

_FILESYSTEM_AND_EXECUTION_TOOLS = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
    }
)
_DENY_FILESYSTEM = [
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/**"],
        mode="deny",
    )
]
_TASK_TOOL_DESCRIPTION = """Delegate the complete bounded research request exactly
once to the single approved subagent. Put every research angle into that one task and
wait for its typed result before producing the report. Never launch a second task.
Available subagents:\n{available_agents}
"""


_COORDINATOR_PROMPT = """You are the coordinator for a bounded cryptocurrency deep
research task. Call the task tool exactly once and delegate the complete request only
to the verified-source-researcher subagent. The single task must cover macro,
regulatory, and market-structure evidence together; never create one task per angle.
Use only facts returned by that subagent. Every factual finding must carry the exact
positive source indexes supplied by the verified search tool. Never invent a URL,
provider result, market price, citation, or unavailable fact. Keep uncertainty and
evidence gaps explicit. Return the typed DeepResearchReport and no free-form JSON.
"""

_SOURCE_RESEARCHER_PROMPT = """Use only the provided verified search tool. Call it
exactly once with one to three queries in the same tool call. Include macro,
regulatory, and market-structure angles in that bounded query list whenever they are
relevant. The tool output assigns stable positive indexes to provider-verified sources
and includes application-owned query coverage metadata. Every finding must cite the
exact returned source indexes. Do not copy raw provider payloads, invent URLs, write
files, execute code, access a database, or send a notification. Return one typed
ResearchSection and no free-form JSON.
"""

_FALLBACK_PROMPT = """Perform bounded cryptocurrency research using only the supplied
verified search tool. Call it exactly once with one to three queries in the same tool
call. Every factual finding must cite the exact positive source indexes returned by the
tool. Never invent a URL or fact, and return only the typed DeepResearchReport.
"""


class DisableParallelToolCallsMiddleware(AgentMiddleware):
    """Apply the provider-supported sequential tool-call setting to every model turn."""

    @staticmethod
    def _sequential_request(request: ModelRequest) -> ModelRequest:
        return request.override(
            model_settings={
                **request.model_settings,
                "parallel_tool_calls": False,
            }
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return handler(self._sequential_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        return await handler(self._sequential_request(request))


def _register_restricted_profile() -> None:
    register_harness_profile(
        DEEP_RESEARCH_PROFILE_KEY,
        HarnessProfile(
            excluded_tools=_FILESYSTEM_AND_EXECUTION_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            tool_description_overrides={"task": _TASK_TOOL_DESCRIPTION},
        ),
    )


def create_research_harness(
    *,
    model: BaseChatModel | Any,
    verified_search_tool: BaseTool | Callable[..., Any] | Any,
    mode: ResearchHarnessMode,
) -> Any:
    """Select exactly one official research harness for the current deployment."""

    if mode == "deepagents":
        _register_restricted_profile()
        return create_deep_agent(
            model=model,
            tools=[],
            system_prompt=_COORDINATOR_PROMPT,
            middleware=[
                DisableParallelToolCallsMiddleware(),
                ModelCallLimitMiddleware(
                    run_limit=MAIN_MODEL_CALL_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name="task",
                    run_limit=SUBAGENT_DELEGATION_LIMIT,
                    exit_behavior="error",
                ),
                *secret_redaction_middleware(),
            ],
            subagents=[
                {
                    "name": "verified-source-researcher",
                    "description": (
                        "Collect and synthesize provider-verified public sources for "
                        "one bounded cryptocurrency research section."
                    ),
                    "system_prompt": _SOURCE_RESEARCHER_PROMPT,
                    "tools": [verified_search_tool],
                    "model": model,
                    "middleware": [
                        DisableParallelToolCallsMiddleware(),
                        ModelCallLimitMiddleware(
                            run_limit=SUBAGENT_MODEL_CALL_LIMIT,
                            exit_behavior="error",
                        ),
                        ToolCallLimitMiddleware(
                            tool_name=VERIFIED_SEARCH_TOOL_NAME,
                            run_limit=SEARCH_TOOL_CALL_LIMIT,
                            exit_behavior="error",
                        ),
                        *secret_redaction_middleware(),
                    ],
                    "permissions": _DENY_FILESYSTEM,
                    "response_format": ToolStrategy(
                        ResearchSection,
                        handle_errors=STRUCTURED_OUTPUT_REPAIR_MESSAGE,
                    ),
                }
            ],
            permissions=_DENY_FILESYSTEM,
            backend=StateBackend(),
            response_format=ToolStrategy(
                DeepResearchReport,
                handle_errors=STRUCTURED_OUTPUT_REPAIR_MESSAGE,
            ),
            name="deep-research-coordinator",
        ).with_retry(
            retry_if_exception_type=MODEL_TRANSPORT_RETRY_ERRORS,
            stop_after_attempt=2,
        )

    if mode == "langchain":
        return create_agent(
            model=model,
            tools=[verified_search_tool],
            middleware=[
                DisableParallelToolCallsMiddleware(),
                ModelCallLimitMiddleware(
                    run_limit=FALLBACK_MODEL_CALL_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name=VERIFIED_SEARCH_TOOL_NAME,
                    run_limit=SEARCH_TOOL_CALL_LIMIT,
                    exit_behavior="error",
                ),
                *secret_redaction_middleware(),
            ],
            system_prompt=_FALLBACK_PROMPT,
            response_format=ToolStrategy(
                DeepResearchReport,
                handle_errors=STRUCTURED_OUTPUT_REPAIR_MESSAGE,
            ),
            name="deep-research-langchain-fallback",
        ).with_retry(
            retry_if_exception_type=MODEL_TRANSPORT_RETRY_ERRORS,
            stop_after_attempt=2,
        )

    raise ValueError(f"unsupported research harness mode: {mode!r}")


__all__ = [
    "CitedResearchFinding",
    "DeepResearchReport",
    "DisableParallelToolCallsMiddleware",
    "ResearchHarnessMode",
    "ResearchSection",
    "create_research_harness",
]
