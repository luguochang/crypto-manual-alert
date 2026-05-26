from __future__ import annotations

from typing import Any
import os
import time

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.telemetry.llm import extract_chat_completion_telemetry
from crypto_manual_alert.telemetry.observability import record_llm_interaction


def openai_settings(config: Config, component: str) -> tuple[str, str, str]:
    if not config.decision.openai_base_url:
        raise ValueError(f"decision.openai_base_url is required for {component}")
    if not config.decision.openai_model:
        raise ValueError(f"decision.openai_model is required for {component}")
    api_key = os.getenv(config.decision.openai_api_key_env, "")
    if not api_key:
        raise ValueError(f"{config.decision.openai_api_key_env} is required for {component}")
    return config.decision.openai_base_url.rstrip("/"), config.decision.openai_model, api_key


def duration_ms(started_perf: float, current_perf: float | None = None) -> int:
    return int(((current_perf if current_perf is not None else time.perf_counter()) - started_perf) * 1000)


def post_chat_completion(
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    payload: dict[str, Any],
    injected_client: httpx.Client | None,
    component: str,
) -> str:
    client = injected_client or httpx.Client(timeout=timeout_seconds)
    close_client = injected_client is None
    started_perf = time.perf_counter()
    try:
        response = client.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        telemetry = extract_chat_completion_telemetry(data)
        record_llm_interaction(
            component=component,
            provider="openai_compatible",
            model=str(payload.get("model") or ""),
            endpoint="/v1/chat/completions",
            request_payload=payload,
            response_payload=data,
            status="ok",
            duration_ms=duration_ms(started_perf),
            prompt_tokens=telemetry.prompt_tokens,
            completion_tokens=telemetry.completion_tokens,
            total_tokens=telemetry.total_tokens,
            cost_usd=telemetry.cost_usd,
            finish_reason=telemetry.finish_reason,
            retry_count=0,
        )
        return str(data["choices"][0]["message"]["content"])
    except Exception as exc:
        record_llm_interaction(
            component=component,
            provider="openai_compatible",
            model=str(payload.get("model") or ""),
            endpoint="/v1/chat/completions",
            request_payload=payload,
            response_payload=None,
            status="error",
            error=exc,
            duration_ms=duration_ms(started_perf),
            retry_count=0,
        )
        raise
    finally:
        if close_client:
            client.close()
