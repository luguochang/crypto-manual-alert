from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


class ConfigError(ValueError):
    """Raised when configuration is unsafe or invalid."""


@dataclass(frozen=True)
class AppConfig:
    mode: str = "SHADOW"
    timezone: str = "Asia/Shanghai"
    data_dir: str = "data"
    log_level: str = "INFO"


@dataclass(frozen=True)
class TradingConfig:
    auto_order_enabled: bool = False
    manual_execution_required: bool = True
    allowed_symbols: list[str] = field(default_factory=lambda: ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"])
    max_risk_per_trade_pct: float = 0.25
    max_leverage: int = 2
    daily_loss_stop_pct: float = 1.0
    stop_after_consecutive_losses: int = 2
    plan_ttl_seconds: int = 90


@dataclass(frozen=True)
class MarketDataConfig:
    provider: str = "okx_public"
    okx_base_url: str = "https://www.okx.com"
    request_timeout_seconds: int = 8
    aggregate_timeout_seconds: int = 25
    stale_market_data_seconds: int = 120
    order_book_depth: int = 20
    candle_bar: str = "1H"
    candle_limit: int = 60


@dataclass(frozen=True)
class DecisionConfig:
    engine: str = "fixture"
    final_input_mode: str = "legacy_prompt"
    final_input_mode_switch_review_path: str = ""
    skill_path: str = "third_party/skills/crypto-macro-decision"
    command: str = ""
    timeout_seconds: int = 900
    fixture_plan_path: str = "tests/fixtures/decision_plan_valid.json"
    openai_base_url: str = ""
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_model: str = ""
    openai_temperature: float = 0.1
    openai_max_tokens: int = 1800


@dataclass(frozen=True)
class NotificationConfig:
    provider: str = "bark"
    enabled: bool = False
    bark_base_url: str = "https://api.day.app"
    bark_device_key_env: str = "BARK_DEVICE_KEY"
    timeout_seconds: int = 8
    retry_count: int = 1
    max_body_chars: int = 900
    send_failure_alerts: bool = True


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = False
    interval_seconds: int = 1800
    run_on_start: bool = True
    lock_ttl_seconds: int = 1800
    max_iterations: int = 0
    job_timeout_seconds: int = 300


@dataclass(frozen=True)
class ResearchConfig:
    enabled: bool = False
    planner: str = "static"
    leader_mode: str = "static"
    search_provider: str = "disabled"
    max_queries: int = 6
    max_workers: int = 4
    max_results_per_query: int = 3
    request_timeout_seconds: int = 8


@dataclass(frozen=True)
class ShadowConfig:
    worker_mode: str = "local_audit"


@dataclass(frozen=True)
class WorkflowConfig:
    execution_mode: str = "legacy_baseline"


@dataclass(frozen=True)
class MacroEventConfig:
    """Macro event status source for the facts_gate active_event_status requirement.

    provider:
    - disabled (default): no active_event_status point is added. Opening/trigger/flip
      actions stay blocked by facts_gate. This is the safe default.
    - no_active_event: operator-asserted "no scheduled macro event affects this
      symbol's horizon window". Adds an active_event_status point (source=event_pool,
      fresh) so the gate can allow opening actions. Only enable when the operator has
      confirmed there is no active event; the assertion is recorded in the audit trail.
    """

    provider: str = "disabled"


@dataclass(frozen=True)
class SkillProvidersConfig:
    realtime_search: str = "disabled"
    root_cause: str = "disabled"
    liquidity_order_book: str = "fixture"


@dataclass(frozen=True)
class EvalReleaseGateConfig:
    minimum_case_count: int = 20
    schema_valid_rate_threshold: float = 0.95
    required_badcase_severities: list[str] = field(default_factory=lambda: ["high", "critical"])


@dataclass(frozen=True)
class EvalFinancialQualityConfig:
    evaluation_targets: list[str] = field(default_factory=lambda: ["legacy_final", "swarm_candidate_final"])
    minimum_scored_count: int = 30
    minimum_direction_hit_rate: float = 0.52
    maximum_brier_score: float = 0.25


@dataclass(frozen=True)
class EvalConfig:
    release_gate: EvalReleaseGateConfig = field(default_factory=EvalReleaseGateConfig)
    financial_quality: EvalFinancialQualityConfig = field(default_factory=EvalFinancialQualityConfig)


@dataclass(frozen=True)
class SecurityConfig:
    forbid_trade_keys: bool = True
    secret_env_names: list[str] = field(default_factory=list)
    forbidden_env_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    app: AppConfig
    trading: TradingConfig
    market_data: MarketDataConfig
    decision: DecisionConfig
    notification: NotificationConfig
    scheduler: SchedulerConfig
    research: ResearchConfig
    security: SecurityConfig
    shadow: ShadowConfig = field(default_factory=ShadowConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    skill_providers: SkillProvidersConfig = field(default_factory=SkillProvidersConfig)
    macro_event: MacroEventConfig = field(default_factory=MacroEventConfig)
    eval: EvalConfig = field(default_factory=EvalConfig)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "app": self.app.__dict__,
            "trading": self.trading.__dict__,
            "market_data": self.market_data.__dict__,
            "decision": self.decision.__dict__,
            "notification": {
                **self.notification.__dict__,
                "bark_device_key_env": self.notification.bark_device_key_env,
                "bark_device_key_value": "<redacted>" if os.getenv(self.notification.bark_device_key_env) else "<unset>",
            },
            "scheduler": self.scheduler.__dict__,
            "research": self.research.__dict__,
            "eval": {
                "release_gate": self.eval.release_gate.__dict__,
                "financial_quality": self.eval.financial_quality.__dict__,
            },
            "shadow": self.shadow.__dict__,
            "workflow": self.workflow.__dict__,
            "skill_providers": self.skill_providers.__dict__,
            "macro_event": self.macro_event.__dict__,
            "security": {
                "forbid_trade_keys": self.security.forbid_trade_keys,
                "secret_env_names": list(self.security.secret_env_names),
                "forbidden_env_names": list(self.security.forbidden_env_names),
            },
        }
