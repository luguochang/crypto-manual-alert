from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


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
    http_trust_env: bool = False
    http_proxy: str = ""
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
    candidate_sidecar_mode: str = "same_engine"
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
    no_active_event_operator_ref: str = ""
    no_active_event_confirmed_at: str = ""
    no_active_event_source_ref: str = ""
    no_active_event_horizon: str = ""
    no_active_event_valid_until: str = ""

    def missing_no_active_event_metadata_envs(self) -> list[str]:
        if self.provider != "no_active_event":
            return []
        required = [
            ("no_active_event_operator_ref", "MACRO_EVENT_OPERATOR_REF"),
            ("no_active_event_confirmed_at", "MACRO_EVENT_CONFIRMED_AT"),
            ("no_active_event_source_ref", "MACRO_EVENT_SOURCE_REF"),
            ("no_active_event_horizon", "MACRO_EVENT_ASSERTION_HORIZON"),
            ("no_active_event_valid_until", "MACRO_EVENT_VALID_UNTIL"),
        ]
        return [env_name for field_name, env_name in required if not str(getattr(self, field_name)).strip()]


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
class DiagnosticConfig:
    routes_enabled: bool = False


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
    diagnostic: DiagnosticConfig = field(default_factory=DiagnosticConfig)

    def safe_dict(self) -> dict[str, Any]:
        readiness = self._readiness()
        safe_market_data = {
            **self.market_data.__dict__,
            "http_proxy": "<redacted>" if self.market_data.http_proxy else "<unset>",
            "http_proxy_set": bool(self.market_data.http_proxy),
        }
        return {
            "app": self.app.__dict__,
            "trading": self.trading.__dict__,
            "market_data": safe_market_data,
            "decision": {
                **self.decision.__dict__,
                "openai_api_key_env": self.decision.openai_api_key_env,
                "openai_api_key_value": "<redacted>" if os.getenv(self.decision.openai_api_key_env) else "<unset>",
            },
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
            "diagnostic": self.diagnostic.__dict__,
            "shadow": self.shadow.__dict__,
            "workflow": self.workflow.__dict__,
            "skill_providers": self.skill_providers.__dict__,
            "macro_event": self.macro_event.__dict__,
            "security": {
                "forbid_trade_keys": self.security.forbid_trade_keys,
                "secret_env_names": list(self.security.secret_env_names),
                "forbidden_env_names": list(self.security.forbidden_env_names),
            },
            "readiness": readiness,
        }

    def _readiness(self) -> dict[str, Any]:
        openai_key_value = "<redacted>" if os.getenv(self.decision.openai_api_key_env) else "<unset>"
        bark_key_value = "<redacted>" if os.getenv(self.notification.bark_device_key_env) else "<unset>"
        forbidden_set = [name for name in self.security.forbidden_env_names if os.getenv(name)]
        unsafe = _prod_actionable_unsafe_reasons(self)
        openai_unsafe = [reason for reason in unsafe if reason.startswith("OPENAI_")]
        market_unsafe = [reason for reason in unsafe if reason.startswith("MARKET_DATA_")]
        decision_ready = self.decision.engine == "openai_compatible" and bool(
            self.decision.openai_base_url and self.decision.openai_model and openai_key_value == "<redacted>"
        ) and not openai_unsafe
        market_ready = self.market_data.provider == "okx_public" and not market_unsafe
        notification_ready = bool(self.notification.enabled and bark_key_value == "<redacted>")
        trading_safe = not self.trading.auto_order_enabled and self.trading.manual_execution_required
        forbidden_ready = len(forbidden_set) == 0
        event_provider_ready = self.macro_event.provider == "no_active_event"
        missing_event_metadata = self.macro_event.missing_no_active_event_metadata_envs()
        event_metadata_complete = event_provider_ready and not missing_event_metadata
        event_ready = event_provider_ready and event_metadata_complete
        candidate_sidecar_disabled = self.decision.candidate_sidecar_mode == "disabled"
        main_path_blockers: list[str] = []
        if self.decision.final_input_mode != "legacy_prompt":
            main_path_blockers.append("decision.final_input_mode must be legacy_prompt for prod-actionable")
        if self.workflow.execution_mode != "legacy_baseline":
            main_path_blockers.append("workflow.execution_mode must be legacy_baseline for prod-actionable")
        production_main_path_ready = candidate_sidecar_disabled and not main_path_blockers
        no_unsafe_readiness = not unsafe
        real_external_ready = all([decision_ready, market_ready, notification_ready, trading_safe, forbidden_ready, no_unsafe_readiness])
        prod_actionable_ready = real_external_ready and event_ready and production_main_path_ready
        fixture_only = self.decision.engine == "fixture" or self.market_data.provider == "fixture"

        return {
            "overall": {
                "status": "unsafe" if unsafe else "ready" if real_external_ready else "fixture_only" if fixture_only else "missing_env",
                "real_external_ready": real_external_ready,
                "summary": (
                    "真实模型、真实行情和手机通知配置已就绪，仍需人工复核并保持自动下单关闭。"
                    if real_external_ready
                    else "当前不是完整真实外部依赖模式；页面应明确提示演练数据、缺少密钥或通知未启用等原因。"
                ),
            },
            "decision_engine": {
                "status": (
                    "unsafe"
                    if openai_unsafe
                    else "ready"
                    if decision_ready
                    else "fixture_only"
                    if self.decision.engine == "fixture"
                    else "missing_env"
                ),
                "engine": self.decision.engine,
                "model": self.decision.openai_model,
                "base_url_set": bool(self.decision.openai_base_url),
                "unsafe": openai_unsafe,
                "message": (
                    "默认演练决策引擎不会调用外部模型。"
                    if self.decision.engine == "fixture"
                    else "外部模型需要地址、模型名和密钥同时存在。"
                ),
            },
            "openai_credentials": {
                "status": "ready" if openai_key_value == "<redacted>" else "missing_env",
                "api_key_env": self.decision.openai_api_key_env,
                "api_key_value": openai_key_value,
            },
            "market_data": {
                "status": "unsafe" if market_unsafe else "ready" if market_ready else "fixture_only",
                "provider": self.market_data.provider,
                "unsafe": market_unsafe,
                "message": "演练行情只适合流程验证。" if not market_ready else "已配置真实行情来源。",
            },
            "liquidity_order_book": {
                "status": "ready" if self.skill_providers.liquidity_order_book == "exchange_native" else "fixture_only",
                "provider": self.skill_providers.liquidity_order_book,
                "message": "开仓类提醒需要交易所原生订单簿事实才能进入人工复核。",
            },
            "event_status": {
                "status": "ready" if event_ready else "missing_env" if event_provider_ready else "disabled",
                "provider": self.macro_event.provider,
                "provider_ready": event_provider_ready,
                "assertion_metadata_complete": event_metadata_complete,
                "missing_assertion_metadata": missing_event_metadata,
                "message": (
                    "已确认本窗口没有影响本提醒的活跃宏观事件，并记录了操作员确认元数据。"
                    if event_ready
                    else "已启用无活跃宏观事件断言，但缺少确认人、确认时间、依据、窗口或有效期。"
                    if event_provider_ready
                    else "宏观事件状态未确认；开仓、触发或翻转类提醒会被阻断。"
                ),
            },
            "notification": {
                "status": (
                    "ready"
                    if notification_ready
                    else "disabled"
                    if not self.notification.enabled
                    else "missing_env"
                ),
                "enabled": self.notification.enabled,
                "provider": self.notification.provider,
                "bark_device_key_env": self.notification.bark_device_key_env,
                "bark_device_key_value": bark_key_value,
            },
            "trading_safety": {
                "status": "ready" if trading_safe else "unsafe",
                "auto_order_enabled": self.trading.auto_order_enabled,
                "manual_execution_required": self.trading.manual_execution_required,
            },
            "forbidden_env": {
                "status": "ready" if forbidden_ready else "unsafe",
                "present": forbidden_set,
                "checked": list(self.security.forbidden_env_names),
            },
            "prod_actionable": {
                "status": "ready" if prod_actionable_ready else "unsafe" if unsafe else "missing_env",
                "prod_actionable_ready": prod_actionable_ready,
                "real_external_ready": real_external_ready,
                "event_ready": event_ready,
                "event_assertion_metadata_complete": event_metadata_complete,
                "missing_event_assertion_metadata": missing_event_metadata,
                "candidate_sidecar_disabled": candidate_sidecar_disabled,
                "production_main_path_ready": production_main_path_ready,
                "main_path_blockers": main_path_blockers,
                "unsafe": unsafe,
                "summary": (
                    "真实模型、真实行情、Bark、事件状态、候选旁路关闭与人工安全边界均已满足；仍必须通过严格生产自测才能发布。"
                    if prod_actionable_ready
                    else "生产可行动提醒未就绪；需要真实模型、真实行情、Bark、事件状态、候选旁路关闭与人工安全边界同时满足。"
                ),
            },
        }


def _prod_actionable_unsafe_reasons(config: Config) -> list[str]:
    reasons: list[str] = []
    if config.decision.engine == "openai_compatible":
        if config.decision.openai_base_url and not _is_public_https_endpoint(config.decision.openai_base_url):
            reasons.append("OPENAI_BASE_URL must be a public https endpoint for prod-actionable")
        if config.decision.openai_model.strip().lower().startswith("mock"):
            reasons.append("OPENAI_MODEL must not be a mock model for prod-actionable")
    if config.market_data.provider == "okx_public":
        okx_base = config.market_data.okx_base_url.strip()
        if okx_base and okx_base.rstrip("/") != "https://www.okx.com":
            reasons.append("MARKET_DATA_OKX_BASE_URL must be unset or https://www.okx.com for prod-actionable")
    return reasons


def _is_public_https_endpoint(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not any([ip.is_loopback, ip.is_private, ip.is_link_local, ip.is_reserved, ip.is_multicast, ip.is_unspecified])


def parse_iso_datetime_with_timezone(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be an ISO-8601 datetime with timezone") from exc
    if parsed.tzinfo is None:
        raise ConfigError(f"{field_name} must include timezone")
    return parsed
