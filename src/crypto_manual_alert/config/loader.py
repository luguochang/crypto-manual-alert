from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from .final_input_switch_review import validate_final_input_switch_review_path
from .models import (
    AppConfig,
    Config,
    ConfigError,
    DecisionConfig,
    EvalConfig,
    EvalFinancialQualityConfig,
    EvalReleaseGateConfig,
    MacroEventConfig,
    MarketDataConfig,
    MacroEventConfig,
    NotificationConfig,
    ResearchConfig,
    SchedulerConfig,
    SecurityConfig,
    ShadowConfig,
    SkillProvidersConfig,
    TradingConfig,
    WorkflowConfig,
)


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
    if "SHADOW_WORKER_MODE" in os.environ:
        merged.setdefault("shadow", {})["worker_mode"] = os.environ["SHADOW_WORKER_MODE"]
    if "WORKFLOW_EXECUTION_MODE" in os.environ:
        merged.setdefault("workflow", {})["execution_mode"] = os.environ["WORKFLOW_EXECUTION_MODE"]
    if "MACRO_EVENT_PROVIDER" in os.environ:
        merged.setdefault("macro_event", {})["provider"] = os.environ["MACRO_EVENT_PROVIDER"]
    if "PLAN_TTL_SECONDS" in os.environ:
        merged.setdefault("trading", {})["plan_ttl_seconds"] = int(os.environ["PLAN_TTL_SECONDS"])
    if "STALE_MARKET_DATA_SECONDS" in os.environ:
        merged.setdefault("market_data", {})["stale_market_data_seconds"] = int(os.environ["STALE_MARKET_DATA_SECONDS"])
    return merged


def _build_config(data: dict[str, Any]) -> Config:
    eval_section = _section(data, "eval")
    eval_release_gate = eval_section.get("release_gate", {})
    if not isinstance(eval_release_gate, dict):
        raise ConfigError("Config section must be a mapping: eval.release_gate")
    eval_financial_quality = eval_section.get("financial_quality", {})
    if not isinstance(eval_financial_quality, dict):
        raise ConfigError("Config section must be a mapping: eval.financial_quality")
    return Config(
        app=AppConfig(**_section(data, "app")),
        trading=TradingConfig(**_section(data, "trading")),
        market_data=MarketDataConfig(**_section(data, "market_data")),
        decision=DecisionConfig(**_section(data, "decision")),
        notification=NotificationConfig(**_section(data, "notification")),
        scheduler=SchedulerConfig(**_section(data, "scheduler")),
        research=ResearchConfig(**_section(data, "research")),
        eval=EvalConfig(
            release_gate=EvalReleaseGateConfig(**eval_release_gate),
            financial_quality=EvalFinancialQualityConfig(**eval_financial_quality),
        ),
        shadow=ShadowConfig(**_section(data, "shadow")),
        workflow=WorkflowConfig(**_section(data, "workflow")),
        skill_providers=SkillProvidersConfig(**_section(data, "skill_providers")),
        macro_event=MacroEventConfig(**_section(data, "macro_event")),
        security=SecurityConfig(**_section(data, "security")),
    )


def _validate(config: Config) -> None:
    if config.app.mode not in {"OFF", "SHADOW", "MANUAL_ALERT"}:
        raise ConfigError(f"Unsupported app.mode: {config.app.mode}")
    if config.trading.auto_order_enabled:
        raise ConfigError("auto_order_enabled must remain false for manual-alert mode")
    if not config.trading.manual_execution_required:
        raise ConfigError("manual_execution_required must remain true for manual-alert mode")
    if config.trading.max_risk_per_trade_pct <= 0 or config.trading.max_risk_per_trade_pct > 1:
        raise ConfigError("max_risk_per_trade_pct must be within (0, 1]")
    if config.trading.max_leverage > 2:
        raise ConfigError("max_leverage must not exceed 2 in manual-alert mode")
    if config.decision.engine == "command":
        raise ConfigError("decision.engine=command is disabled for manual-alert mode")
    if config.decision.final_input_mode == "decision_input":
        validate_final_input_switch_review_path(config.decision.final_input_mode_switch_review_path)
    elif config.decision.final_input_mode != "legacy_prompt":
        raise ConfigError(f"Unsupported decision.final_input_mode: {config.decision.final_input_mode}")
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
    if config.shadow.worker_mode not in {"local_audit", "llm_tool_shadow"}:
        raise ConfigError("shadow.worker_mode must be one of: local_audit, llm_tool_shadow")
    if config.workflow.execution_mode not in {"legacy_baseline", "controlled_shadow", "production_candidate_swarm"}:
        raise ConfigError(
            "workflow.execution_mode must be one of: legacy_baseline, controlled_shadow, production_candidate_swarm"
        )
    if config.skill_providers.realtime_search not in {"disabled", "fixture", "responses_web_search"}:
        raise ConfigError("skill_providers.realtime_search must be one of: disabled, fixture, responses_web_search")
    if config.skill_providers.root_cause not in {"disabled", "fixture", "realtime_search"}:
        raise ConfigError("skill_providers.root_cause must be one of: disabled, fixture, realtime_search")
    if config.skill_providers.liquidity_order_book not in {"disabled", "fixture", "exchange_native"}:
        raise ConfigError("skill_providers.liquidity_order_book must be one of: disabled, fixture, exchange_native")
    if config.macro_event.provider not in {"disabled", "no_active_event"}:
        raise ConfigError("macro_event.provider must be one of: disabled, no_active_event")
    if config.eval.release_gate.minimum_case_count < 1:
        raise ConfigError("eval.release_gate.minimum_case_count must be at least 1")
    if not 0 <= config.eval.release_gate.schema_valid_rate_threshold <= 1:
        raise ConfigError("eval.release_gate.schema_valid_rate_threshold must be within [0, 1]")
    allowed_badcase_severities = {"low", "medium", "high", "critical"}
    unknown_badcase_severities = [
        severity
        for severity in config.eval.release_gate.required_badcase_severities
        if severity not in allowed_badcase_severities
    ]
    if unknown_badcase_severities:
        raise ConfigError("eval.release_gate.required_badcase_severities contains unsupported severity")
    if not config.eval.financial_quality.evaluation_targets:
        raise ConfigError("eval.financial_quality.evaluation_targets must not be empty")
    if config.eval.financial_quality.minimum_scored_count < 1:
        raise ConfigError("eval.financial_quality.minimum_scored_count must be at least 1")
    if not 0 <= config.eval.financial_quality.minimum_direction_hit_rate <= 1:
        raise ConfigError("eval.financial_quality.minimum_direction_hit_rate must be within [0, 1]")
    if not 0 <= config.eval.financial_quality.maximum_brier_score <= 1:
        raise ConfigError("eval.financial_quality.maximum_brier_score must be within [0, 1]")
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
