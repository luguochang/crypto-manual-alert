from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when configuration is unsafe or invalid."""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a mapping: {p}")
    return data


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
            "security": {
                "forbid_trade_keys": self.security.forbid_trade_keys,
                "secret_env_names": list(self.security.secret_env_names),
                "forbidden_env_names": list(self.security.forbidden_env_names),
            },
        }


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"Config section must be a mapping: {name}")
    return value


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(data)
    if "APP_MODE" in os.environ:
        merged.setdefault("app", {})["mode"] = os.environ["APP_MODE"]
    if "DATA_DIR" in os.environ:
        merged.setdefault("app", {})["data_dir"] = os.environ["DATA_DIR"]
    if "AUTO_ORDER_ENABLED" in os.environ:
        merged.setdefault("trading", {})["auto_order_enabled"] = _env_bool("AUTO_ORDER_ENABLED", False)
    if "MARKET_DATA_PROVIDER" in os.environ:
        merged.setdefault("market_data", {})["provider"] = os.environ["MARKET_DATA_PROVIDER"]
    if "DECISION_ENGINE" in os.environ:
        merged.setdefault("decision", {})["engine"] = os.environ["DECISION_ENGINE"]
    if "DECISION_COMMAND" in os.environ:
        merged.setdefault("decision", {})["command"] = os.environ["DECISION_COMMAND"]
    if "DECISION_TIMEOUT_SECONDS" in os.environ:
        merged.setdefault("decision", {})["timeout_seconds"] = int(os.environ["DECISION_TIMEOUT_SECONDS"])
    if "OPENAI_BASE_URL" in os.environ:
        merged.setdefault("decision", {})["openai_base_url"] = os.environ["OPENAI_BASE_URL"]
    if "OPENAI_MODEL" in os.environ:
        merged.setdefault("decision", {})["openai_model"] = os.environ["OPENAI_MODEL"]
    if "OPENAI_API_KEY_ENV" in os.environ:
        merged.setdefault("decision", {})["openai_api_key_env"] = os.environ["OPENAI_API_KEY_ENV"]
    if "NOTIFICATION_ENABLED" in os.environ:
        merged.setdefault("notification", {})["enabled"] = _env_bool("NOTIFICATION_ENABLED", False)
    if "SCHEDULER_ENABLED" in os.environ:
        merged.setdefault("scheduler", {})["enabled"] = _env_bool("SCHEDULER_ENABLED", False)
    if "SCHEDULER_INTERVAL_SECONDS" in os.environ:
        merged.setdefault("scheduler", {})["interval_seconds"] = int(os.environ["SCHEDULER_INTERVAL_SECONDS"])
    if "SCHEDULER_JOB_TIMEOUT_SECONDS" in os.environ:
        merged.setdefault("scheduler", {})["job_timeout_seconds"] = int(os.environ["SCHEDULER_JOB_TIMEOUT_SECONDS"])
    if "RESEARCH_ENABLED" in os.environ:
        merged.setdefault("research", {})["enabled"] = _env_bool("RESEARCH_ENABLED", False)
    if "RESEARCH_SEARCH_PROVIDER" in os.environ:
        merged.setdefault("research", {})["search_provider"] = os.environ["RESEARCH_SEARCH_PROVIDER"]
    if "RESEARCH_PLANNER" in os.environ:
        merged.setdefault("research", {})["planner"] = os.environ["RESEARCH_PLANNER"]
    if "RESEARCH_LEADER_MODE" in os.environ:
        merged.setdefault("research", {})["leader_mode"] = os.environ["RESEARCH_LEADER_MODE"]
    if "RESEARCH_MAX_QUERIES" in os.environ:
        merged.setdefault("research", {})["max_queries"] = int(os.environ["RESEARCH_MAX_QUERIES"])
    if "RESEARCH_MAX_WORKERS" in os.environ:
        merged.setdefault("research", {})["max_workers"] = int(os.environ["RESEARCH_MAX_WORKERS"])
    if "RESEARCH_REQUEST_TIMEOUT_SECONDS" in os.environ:
        merged.setdefault("research", {})["request_timeout_seconds"] = int(os.environ["RESEARCH_REQUEST_TIMEOUT_SECONDS"])
    if "PLAN_TTL_SECONDS" in os.environ:
        merged.setdefault("trading", {})["plan_ttl_seconds"] = int(os.environ["PLAN_TTL_SECONDS"])
    if "STALE_MARKET_DATA_SECONDS" in os.environ:
        merged.setdefault("market_data", {})["stale_market_data_seconds"] = int(os.environ["STALE_MARKET_DATA_SECONDS"])
    return merged


def _build_config(data: dict[str, Any]) -> Config:
    return Config(
        app=AppConfig(**_section(data, "app")),
        trading=TradingConfig(**_section(data, "trading")),
        market_data=MarketDataConfig(**_section(data, "market_data")),
        decision=DecisionConfig(**_section(data, "decision")),
        notification=NotificationConfig(**_section(data, "notification")),
        scheduler=SchedulerConfig(**_section(data, "scheduler")),
        research=ResearchConfig(**_section(data, "research")),
        security=SecurityConfig(**_section(data, "security")),
    )


def _validate(config: Config) -> None:
    if config.app.mode not in {"OFF", "SHADOW", "MANUAL_ALERT"}:
        raise ConfigError(f"Unsupported app.mode: {config.app.mode}")
    if config.trading.auto_order_enabled:
        raise ConfigError("auto_order_enabled must remain false in manual-alert v1")
    if not config.trading.manual_execution_required:
        raise ConfigError("manual_execution_required must remain true in manual-alert v1")
    if config.trading.max_risk_per_trade_pct <= 0 or config.trading.max_risk_per_trade_pct > 1:
        raise ConfigError("max_risk_per_trade_pct must be within (0, 1]")
    if config.trading.max_leverage > 2:
        raise ConfigError("max_leverage must not exceed 2 in v1")
    if config.decision.engine == "command":
        raise ConfigError("decision.engine=command is disabled in manual-alert v1")
    if config.research.planner not in {"static", "llm"}:
        raise ConfigError(f"Unsupported research.planner: {config.research.planner}")
    if config.research.leader_mode not in {"static", "llm"}:
        raise ConfigError(f"Unsupported research.leader_mode: {config.research.leader_mode}")
    if config.research.search_provider not in {"disabled", "fixture", "duckduckgo_html", "responses_web_search"}:
        raise ConfigError(f"Unsupported research.search_provider: {config.research.search_provider}")
    if config.research.max_queries <= 0:
        raise ConfigError("research.max_queries must be positive")
    if config.research.max_workers <= 0:
        raise ConfigError("research.max_workers must be positive")
    if config.security.forbid_trade_keys:
        for name in config.security.forbidden_env_names:
            if os.getenv(name):
                raise ConfigError(f"forbidden environment variable is set: {name}")


def load_config(*paths: str | Path) -> Config:
    default_path = Path("config/default.yaml")
    data = _read_yaml(default_path)
    for path in paths:
        p = Path(path)
        if p == default_path:
            continue
        data = _deep_merge(data, _read_yaml(p))
    data = _apply_env_overrides(data)
    config = _build_config(data)
    _validate(config)
    return config
