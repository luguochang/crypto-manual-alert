from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import ALLOWED_ACTIONS
from crypto_manual_alert.telemetry.llm import extract_chat_completion_telemetry
from crypto_manual_alert.telemetry.observability import record_llm_interaction


class DecisionEngine:
    def run(self, prompt_packet: dict[str, object]) -> str:
        raise NotImplementedError


class FixtureDecisionEngine(DecisionEngine):
    def __init__(self, fixture_path: str):
        self.fixture_path = Path(fixture_path)

    def run(self, prompt_packet: dict[str, object]) -> str:
        return self.fixture_path.read_text(encoding="utf-8")


class CommandDecisionEngine(DecisionEngine):
    def __init__(self, command: str, timeout_seconds: int):
        raise ValueError("CommandDecisionEngine is disabled for manual-alert mode; use fixture or openai_compatible")

    def run(self, prompt_packet: dict[str, object]) -> str:
        raise RuntimeError("CommandDecisionEngine is disabled")


class OpenAICompatibleDecisionEngine(DecisionEngine):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        temperature: float = 0.1,
        max_tokens: int = 1800,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ValueError("openai_base_url is required")
        if not api_key:
            raise ValueError("openai api key is required")
        if not model:
            raise ValueError("openai_model is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = client

    @classmethod
    def from_config(cls, config: Config) -> "OpenAICompatibleDecisionEngine":
        api_key = os.getenv(config.decision.openai_api_key_env, "")
        return cls(
            base_url=config.decision.openai_base_url,
            api_key=api_key,
            model=config.decision.openai_model,
            timeout_seconds=config.decision.timeout_seconds,
            temperature=config.decision.openai_temperature,
            max_tokens=config.decision.openai_max_tokens,
        )

    def run(self, prompt_packet: dict[str, object]) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _final_decision_system_prompt()},
                {"role": "user", "content": json.dumps(prompt_packet, ensure_ascii=False, default=str)},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        client = self.client or httpx.Client(timeout=self.timeout_seconds)
        close_client = self.client is None
        started_perf = time.perf_counter()
        try:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            telemetry = extract_chat_completion_telemetry(data)
            record_llm_interaction(
                component="decision.final",
                provider="openai_compatible",
                model=self.model,
                endpoint="/v1/chat/completions",
                request_payload=payload,
                response_payload=data,
                status="ok",
                duration_ms=_duration_ms(started_perf),
                prompt_tokens=telemetry.prompt_tokens,
                completion_tokens=telemetry.completion_tokens,
                total_tokens=telemetry.total_tokens,
                cost_usd=telemetry.cost_usd,
                finish_reason=telemetry.finish_reason,
                retry_count=0,
            )
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            record_llm_interaction(
                component="decision.final",
                provider="openai_compatible",
                model=self.model,
                endpoint="/v1/chat/completions",
                request_payload=payload,
                response_payload=None,
                status="error",
                error=exc,
                duration_ms=_duration_ms(started_perf),
                retry_count=0,
            )
            raise
        finally:
            if close_client:
                client.close()


def _final_decision_system_prompt() -> str:
    return (
        "You are a crypto manual-operation planning engine. "
        "Use the provided crypto-macro-decision skill_context as the strategy rule source. "
        "Return strict JSON only. Do not place orders. "
        "The user must manually operate in OKX. "
        "All user-facing explanatory text must be Simplified Chinese (简体中文), including "
        "why_not_opposite, invalidation, unavailable_data descriptions, and notes. "
        "Keep JSON keys, main_action enum values, URLs, source names, and numeric fields in "
        "their required canonical format. "
        "Required fields: instrument, main_action, horizon, reference_price, entry_trigger, "
        "stop_price, target_1, target_2, probability, position_size_class, max_leverage, "
        "risk_pct, expires_in_seconds, why_not_opposite, invalidation, unavailable_data, "
        "manual_execution_required. "
        "Type rules: reference_price, entry_trigger, stop_price, target_1, target_2, "
        "probability, risk_pct must be JSON numbers or null; max_leverage and "
        "expires_in_seconds must be JSON integers. Put conditional text only in notes "
        "or invalidation, never in numeric fields. main_action must be one of: "
        f"{', '.join(sorted(ALLOWED_ACTIONS))}. "
        "Output example shape: {\"instrument\":\"ETH-USDT-SWAP\",\"main_action\":\"trigger long\","
        "\"horizon\":\"6h\",\"reference_price\":3500,\"entry_trigger\":3510,"
        "\"stop_price\":3435,\"target_1\":3580,\"target_2\":3660,\"probability\":0.61,"
        "\"position_size_class\":\"light\",\"max_leverage\":2,\"risk_pct\":0.25,"
        "\"expires_in_seconds\":90,\"why_not_opposite\":\"空头没有得到 BTC 结构和资金费率确认\","
        "\"invalidation\":\"跌破 3435 后多头计划失效\","
        "\"unavailable_data\":[\"精确 CVD 缺失\"],\"manual_execution_required\":true,"
        "\"notes\":\"仅提醒手动核对，系统不会自动下单。\"}"
    )


def _duration_ms(started_perf: float) -> int:
    return int((time.perf_counter() - started_perf) * 1000)
