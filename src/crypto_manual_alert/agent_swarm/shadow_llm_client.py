from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from crypto_manual_alert.agent_swarm.llm_tool_worker import LlmShadowClient
from crypto_manual_alert.config import Config


@dataclass(frozen=True)
class FixtureLlmShadowClient:
    """Deterministic shadow LLM client for audit fixtures.

    It returns agent-specific JSON strings. It does not call networks, tools,
    journals, notifications, or the FinalDecisionAgent.
    """

    responses_by_agent: dict[str, dict[str, Any]]

    def complete(self, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> str:
        agent_name = str(payload.get("agent_name") or "")
        response = self.responses_by_agent.get(agent_name) or {"summary": "fixture shadow audit"}
        return json.dumps(response, ensure_ascii=False, separators=(",", ":"))


@dataclass
class OpenAICompatibleLlmShadowClient:
    """Explicit OpenAI-compatible client for shadow worker experiments.

    This client is never built from config implicitly. Callers must explicitly
    construct or inject a factory, so production runs do not gain network access
    by setting shadow.worker_mode alone.
    """

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    agent_name: str | None = None
    temperature: float = 0.1
    max_tokens: int = 1200
    http_client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("openai_base_url is required for llm_tool_shadow")
        if not self.api_key:
            raise ValueError("openai api key is required for llm_tool_shadow")
        if not self.model:
            raise ValueError("openai_model is required for llm_tool_shadow")
        self.base_url = self.base_url.rstrip("/")

    def complete(self, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> str:
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        request_timeout = _effective_timeout(self.timeout_seconds, timeout_seconds)
        client = self.http_client or httpx.Client(timeout=request_timeout)
        close_client = self.http_client is None
        try:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_payload,
                timeout=request_timeout,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        finally:
            if close_client:
                client.close()


def build_openai_compatible_shadow_client_factory(config: Config) -> Callable[[str], LlmShadowClient]:
    """Build an explicit shadow LLM client factory from config and environment."""

    api_key = os.getenv(config.decision.openai_api_key_env, "")
    base_url = config.decision.openai_base_url
    model = config.decision.openai_model
    timeout_seconds = config.decision.timeout_seconds
    temperature = config.decision.openai_temperature
    max_tokens = min(config.decision.openai_max_tokens, 1200)

    def factory(agent_name: str) -> LlmShadowClient:
        return OpenAICompatibleLlmShadowClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            agent_name=agent_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    _ = factory("__validate__")
    return factory


def build_fixture_shadow_client_factory() -> Callable[[str], LlmShadowClient]:
    """Build deterministic LLM/tool shadow workers for local main-flow smoke.

    The responses deliberately request business Skill names through the
    controlled SkillExecutor. This is still audit-only and has no production
    decision effect.
    """

    client = FixtureLlmShadowClient(
        responses_by_agent={
            "LiveFactAgent": {
                "summary": "fixture live-fact shadow worker requested realtime search skill",
                "claims": [{"claim": "fresh live facts require controlled realtime search", "direction": "neutral"}],
                "skill_requests": [
                    {"skill_name": "realtime_search", "arguments": {"query": "fixture live fact search"}}
                ],
            },
            "RootCauseAgent": {
                "summary": "fixture root-cause shadow worker requested root cause skill",
                "claims": [{"claim": "root cause requires recursive evidence audit", "direction": "neutral"}],
                "skill_requests": [
                    {"skill_name": "root_cause_search", "arguments": {"query": "fixture root cause search"}}
                ],
            },
            "MarketSentimentAgent": {
                "summary": "fixture sentiment shadow worker requested sentiment skill",
                "claims": [{"claim": "sentiment and crowding require separate audit", "direction": "neutral"}],
                "skill_requests": [
                    {"skill_name": "market_sentiment", "arguments": {"query": "fixture market sentiment"}}
                ],
            },
            "DataQualityAgent": {
                "summary": "fixture data-quality shadow worker did not request tools",
                "claims": [{"claim": "data quality remains audit only", "direction": "neutral"}],
            },
            "ExecutionRiskAgent": {
                "summary": "fixture execution-risk shadow worker requested liquidity skill",
                "claims": [{"claim": "execution facts require exchange-native source", "direction": "neutral"}],
                "skill_requests": [
                    {"skill_name": "liquidity_order_book", "arguments": {"query": "fixture order book"}}
                ],
            },
        }
    )

    def factory(agent_name: str) -> LlmShadowClient:
        return client

    return factory


def _system_prompt() -> str:
    return (
        "You are a controlled crypto shadow worker. "
        "Return one strict JSON object for audit only. "
        "decision_effect=none. Do not output final trade actions, order payloads, "
        "risk verdicts, journal writes, or notifications. "
        "Required key: summary. Optional keys: claims, constraints, conflicts, "
        "missing_facts, status, skill_requests."
    )


def _effective_timeout(config_timeout: int, request_timeout: float | None) -> float:
    timeout = float(config_timeout)
    if request_timeout is None:
        return timeout
    return max(0.001, min(timeout, float(request_timeout)))
