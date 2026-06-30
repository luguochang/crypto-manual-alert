from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from crypto_manual_alert.eval.schema import EvalCase, EvalScore
from crypto_manual_alert.llm_telemetry import extract_chat_completion_telemetry

from .common import make_score


JUDGE_RUBRICS = {
    "llm.evidence_grounding": "判断结论是否被冻结输入、回放输出和证据引用支撑，不能凭空新增事实。",
    "llm.opposing_thesis": "判断是否充分说明反向观点，以及为什么当前方案不选反向。",
    "llm.data_gap_honesty": "判断是否诚实暴露数据缺口，并在缺口明显时降低可执行性。",
    "llm.execution_clarity": "判断操作计划是否清楚给出方向、价格、止损、失效条件和人工执行边界。",
    "llm.overconfidence": "判断胜率、语气和执行建议是否过度自信。",
}


@dataclass(frozen=True)
class JudgeCallResult:
    content: str
    duration_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


class OpenAICompatibleLLMJudge:
    """真实 OpenAI-compatible LLMJudge。只服务 eval sidecar，不写生产 LLM 观测表。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 120,
        temperature: float = 0.0,
        max_tokens: int = 900,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ValueError("judge openai base_url is required")
        if not api_key:
            raise ValueError("judge openai api key is required")
        if not model:
            raise ValueError("judge openai model is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = client

    @classmethod
    def from_config(cls, config) -> "OpenAICompatibleLLMJudge":
        api_key = os.getenv(config.decision.openai_api_key_env, "")
        return cls(
            base_url=config.decision.openai_base_url,
            api_key=api_key,
            model=config.decision.openai_model,
            timeout_seconds=config.decision.timeout_seconds,
            temperature=0.0,
        )

    def evaluate(
        self,
        eval_run_id: str,
        case: EvalCase,
        replay_output: dict[str, Any] | None = None,
    ) -> list[EvalScore]:
        return [
            self._evaluate_one(eval_run_id, case, judge_name, rubric, replay_output or {})
            for judge_name, rubric in JUDGE_RUBRICS.items()
        ]

    def _evaluate_one(
        self,
        eval_run_id: str,
        case: EvalCase,
        judge_name: str,
        rubric: str,
        replay_output: dict[str, Any],
    ) -> EvalScore:
        try:
            call = self._call(case, judge_name, rubric, replay_output)
            parsed = _parse_judge_json(call.content)
            return make_score(
                eval_run_id=eval_run_id,
                case=case,
                judge_name=judge_name,
                judge_type="llm",
                passed=bool(parsed["passed"]),
                severity=str(parsed["severity"]),
                failure_category=str(parsed["failure_category"]),
                reason_summary=str(parsed["reason_summary"]),
                evidence_refs=[str(item) for item in parsed["evidence_refs"]],
                score=float(parsed["score"]),
                needs_human_review=bool(parsed["needs_human_review"]),
                metadata={
                    "provider": "openai_compatible",
                    "model": self.model,
                    "endpoint": "/v1/chat/completions",
                    "duration_ms": call.duration_ms,
                    "prompt_tokens": call.prompt_tokens,
                    "completion_tokens": call.completion_tokens,
                    "total_tokens": call.total_tokens,
                    "finish_reason": call.finish_reason,
                    "rubric": rubric,
                },
            )
        except Exception as exc:  # noqa: BLE001 - judge 失败不能中断整轮 eval。
            return make_score(
                eval_run_id=eval_run_id,
                case=case,
                judge_name=judge_name,
                judge_type="llm",
                passed=False,
                severity="high",
                failure_category="llm_judge_invalid_response",
                reason_summary=f"LLMJudge 返回不可解析或调用失败：{type(exc).__name__}: {exc}",
                evidence_refs=["llm_judge.response"],
                score=0.0,
                needs_human_review=True,
                metadata={"provider": "openai_compatible", "model": self.model, "error_type": type(exc).__name__},
            )

    def _call(self, case: EvalCase, judge_name: str, rubric: str, replay_output: dict[str, Any]) -> JudgeCallResult:
        request_payload = _judge_request_payload(self.model, case, judge_name, rubric, replay_output, self.temperature, self.max_tokens)
        client = self.client or httpx.Client(timeout=self.timeout_seconds)
        close_client = self.client is None
        started = time.perf_counter()
        try:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_payload,
            )
            response.raise_for_status()
            data = response.json()
            telemetry = extract_chat_completion_telemetry(data)
            content = data["choices"][0]["message"]["content"]
            return JudgeCallResult(
                content=str(content),
                duration_ms=int((time.perf_counter() - started) * 1000),
                prompt_tokens=telemetry.prompt_tokens,
                completion_tokens=telemetry.completion_tokens,
                total_tokens=telemetry.total_tokens,
                finish_reason=telemetry.finish_reason,
            )
        finally:
            if close_client:
                client.close()


def _judge_request_payload(
    model: str,
    case: EvalCase,
    judge_name: str,
    rubric: str,
    replay_output: dict[str, Any],
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    system = (
        "你是加密货币人工操作计划的 Eval Judge。只根据用户消息里的脱敏 case、"
        "frozen_input_hash、input_summary 和 replay_result 评分。必须返回严格 JSON。"
    )
    user_payload = {
        "judge_name": judge_name,
        "rubric": rubric,
        "expected_json_schema": {
            "passed": "boolean",
            "score": "number between 0 and 1",
            "severity": "low|medium|high|critical",
            "failure_category": "string",
            "reason_summary": "string",
            "evidence_refs": ["string"],
            "needs_human_review": "boolean",
        },
        "case": {
            "case_id": case.case_id,
            "source_trace_id": case.source_trace_id,
            "source_badcase_id": case.source_badcase_id,
            "symbol": case.symbol,
            "failure_category": case.failure_category,
            "severity": case.severity,
            "expected_behavior": case.expected_behavior,
            "actual_behavior": case.actual_behavior,
            "frozen_input_hash": case.frozen_input_hash,
            "input_summary": case.input_summary,
            "metadata": case.metadata,
        },
        "replay_result": replay_output,
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True, default=str)},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _parse_judge_json(content: str) -> dict[str, Any]:
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("judge response must be a JSON object")
    required = {
        "passed",
        "score",
        "severity",
        "failure_category",
        "reason_summary",
        "evidence_refs",
        "needs_human_review",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"judge response missing fields: {', '.join(missing)}")
    if not isinstance(data["evidence_refs"], list):
        raise ValueError("judge evidence_refs must be a list")
    return data
