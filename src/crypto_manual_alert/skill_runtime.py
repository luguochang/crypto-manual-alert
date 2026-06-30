from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Config
from .domain import ALLOWED_ACTIONS, MarketSnapshot
from .llm_telemetry import extract_chat_completion_telemetry
from .observability import record_llm_interaction


@dataclass(frozen=True)
class SkillInfo:
    path: Path
    sha256: str
    name: str


@dataclass(frozen=True)
class SkillContext:
    path: Path
    sha256: str
    name: str
    skill_md: str
    references: dict[str, str]
    okx_snapshot_script: Path

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "sha256": self.sha256,
            "required_references": list(self.references),
            "okx_snapshot_script": str(self.okx_snapshot_script),
            "references": self.references,
        }


REQUIRED_REFERENCES = (
    "data-sources.md",
    "exchange-derivatives.md",
    "templates.md",
)
EXPECTED_SKILL_NAME = "crypto-macro-decision"


class SkillRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.path = Path(config.decision.skill_path)

    def info(self) -> SkillInfo:
        skill_file = self.path / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_file}")
        content = skill_file.read_bytes()
        return SkillInfo(path=self.path, sha256=hashlib.sha256(content).hexdigest(), name=EXPECTED_SKILL_NAME)

    def load_context(self) -> SkillContext:
        skill_file = self.path / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_file}")
        skill_md = skill_file.read_text(encoding="utf-8")
        name = _skill_name(skill_md)
        if name != EXPECTED_SKILL_NAME:
            raise ValueError(f"Skill name must be {EXPECTED_SKILL_NAME}, got {name or '<missing>'}")

        references: dict[str, str] = {}
        for name in REQUIRED_REFERENCES:
            reference_file = self.path / "references" / name
            if not reference_file.exists():
                raise FileNotFoundError(f"Required skill reference not found: {reference_file}")
            references[name] = reference_file.read_text(encoding="utf-8")

        okx_snapshot_script = self.path / "scripts" / "okx_snapshot.py"
        if not okx_snapshot_script.exists():
            raise FileNotFoundError(f"Required skill script not found: {okx_snapshot_script}")

        digest = hashlib.sha256()
        digest.update(skill_file.read_bytes())
        for name in REQUIRED_REFERENCES:
            digest.update(name.encode("utf-8"))
            digest.update(references[name].encode("utf-8"))
        digest.update(okx_snapshot_script.read_bytes())

        return SkillContext(
            path=self.path,
            sha256=digest.hexdigest(),
            name=EXPECTED_SKILL_NAME,
            skill_md=skill_md,
            references=references,
            okx_snapshot_script=okx_snapshot_script,
        )

    def build_prompt_packet(self, snapshot: MarketSnapshot, context: SkillContext | None = None) -> dict[str, object]:
        context = context or self.load_context()
        return {
            "skill": {
                "name": context.name,
                "path": str(context.path),
                "sha256": context.sha256,
                "required_references": list(context.references),
                "okx_snapshot_script": str(context.okx_snapshot_script),
            },
            "boundary": "manual-alert-only; do not place orders; user must manually operate in OKX",
            "required_output": "strict JSON DecisionPlan",
            # 完整 skill 已加载并计入 hash；prompt 使用有上限的摘录，避免每次模型调用过慢过贵。
            "skill_context": _compact_prompt_context(context),
            "market_snapshot": snapshot.to_public_dict(),
        }


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
        raise ValueError("CommandDecisionEngine is disabled in manual-alert v1; use fixture or openai_compatible")

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
        system = (
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
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
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


def _skill_name(skill_md: str) -> str | None:
    for line in skill_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return None


def _compact_prompt_context(context: SkillContext) -> dict[str, object]:
    return {
        "mode": "compact",
        "name": context.name,
        "sha256": context.sha256,
        "skill_md_excerpt": _compact_text(context.skill_md, 12000),
        "reference_excerpts": {name: _compact_text(text, 2500) for name, text in context.references.items()},
        "rules_reminder": [
            "manual-alert-only; never place orders",
            "one main_action only, from the canonical action enum",
            "separate known facts, inference, scenario, confidence cap, and invalidation",
            "use mark/index/order_book as exchange-native execution facts",
            "search-derived data can supplement context but cannot replace exchange-native execution facts",
            "include why_not_opposite, invalidation, unavailable_data, trigger/entry, stop, targets, probability, and next review time when available",
            "all user-facing explanatory text must be Simplified Chinese; keep JSON keys and action enum values canonical",
        ],
    }


def _compact_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head - 80
    return f"{text[:head]}\n\n...[compact excerpt; middle omitted for runtime cost]...\n\n{text[-tail:]}"


def _duration_ms(started_perf: float) -> int:
    return int((time.perf_counter() - started_perf) * 1000)
