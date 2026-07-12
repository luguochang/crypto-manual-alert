"""配置管理 - YAML 配置加载 + Feature flags。

来源：V2技术设计缺口补充.md 第五节 + 设计文档 15-frontend-and-config-management.md。

功能：
1. YAML 配置文件加载（config/default.yaml, config/staging.yaml, config/prod.yaml）
2. Feature flags 管理（动态开关功能）
3. 配置合并（环境变量 > YAML > 默认值）
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# 配置环境
# ===========================================================================

class ConfigEnv(str, Enum):
    """配置环境。"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# ===========================================================================
# Feature Flags
# ===========================================================================

class FeatureFlags(BaseModel):
    """Feature flags - 动态开关功能。

    所有 flag 默认 False（安全保守），需要显式开启。
    """
    # Graph 功能
    deep_agents_research: bool = Field(
        default=False, description="启用 Deep Agents 研究子图（Phase 3）"
    )
    parallel_research: bool = Field(
        default=True, description="启用并行研究节点"
    )
    hitl_confirmation: bool = Field(
        default=True, description="启用 HITL 人工确认"
    )

    # 数据源
    okx_cache_enabled: bool = Field(
        default=False, description="启用 OKX Redis 缓存"
    )
    tavily_search_enabled: bool = Field(
        default=True, description="启用 Tavily 搜索"
    )

    # 通知
    bark_notification_enabled: bool = Field(
        default=True, description="启用 Bark 推送"
    )

    # 评测
    eval_auto_run: bool = Field(
        default=False, description="自动运行评测（CI/CD）"
    )
    outcome_tracking_enabled: bool = Field(
        default=False, description="启用 Outcome 追踪"
    )

    # 告警
    alerting_enabled: bool = Field(
        default=True, description="启用告警系统"
    )

    # 降级
    graceful_degradation: bool = Field(
        default=True, description="启用优雅降级（数据缺失时不崩溃）"
    )


# ===========================================================================
# 风险参数配置
# ===========================================================================

class RiskConfig(BaseModel):
    """风险参数配置。"""
    max_leverage: int = Field(default=2, ge=1, le=2, description="最大杠杆")
    risk_pct_max: float = Field(default=0.25, ge=0, le=0.25, description="单笔风险占比上限")
    confidence_threshold: float = Field(default=0.55, ge=0, le=1, description="最低置信度阈值")
    plan_expiry_seconds: int = Field(default=90, description="分析结果有效期（秒）")


# ===========================================================================
# 通知配置
# ===========================================================================

class NotificationConfig(BaseModel):
    """通知渠道配置。"""
    bark_enabled: bool = Field(default=True)
    bark_key: str = Field(default="")
    email_enabled: bool = Field(default=False)
    email_address: str = Field(default="")


# ===========================================================================
# 完整应用配置
# ===========================================================================

class AppConfig(BaseModel):
    """完整应用配置。

    合并优先级：环境变量 > YAML 配置 > 默认值。
    """
    env: ConfigEnv = Field(default=ConfigEnv.DEVELOPMENT)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)

    # Watchlist
    watchlist: list[str] = Field(
        default_factory=lambda: [
            "BTC-USDT-SWAP",
            "ETH-USDT-SWAP",
            "SOL-USDT-SWAP",
        ],
        description="允许分析的标的白名单",
    )

    # 默认分析周期
    default_horizon: str = Field(default="4h")

    # OKX
    okx_base_url: str = Field(default="https://www.okx.com")
    okx_rate_limit_concurrent: int = Field(default=5)
    okx_rate_limit_window_seconds: int = Field(default=2)

    # Agent Server
    agent_server_port: int = Field(default=2024)

    # 评测
    eval_dataset_name: str = Field(default="crypto_alert_eval_set_v1")
    eval_regression_threshold: float = Field(default=0.05)


# ===========================================================================
# YAML 配置加载器
# ===========================================================================

class ConfigLoader:
    """YAML 配置加载器。

    从 config/ 目录加载 YAML 配置文件，支持环境覆盖。
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        """初始化配置加载器。

        Args:
            config_dir: 配置文件目录（默认为项目根的 config/ 目录）
        """
        if config_dir is None:
            # 默认查找项目根目录下的 config/
            config_dir = Path(__file__).parent.parent.parent.parent.parent / "config"
        self.config_dir = Path(config_dir)

    def load_yaml(self, filename: str) -> dict[str, Any]:
        """加载单个 YAML 文件。

        Args:
            filename: 文件名（如 default.yaml）

        Returns:
            配置字典，文件不存在或解析失败返回空字典
        """
        filepath = self.config_dir / filename
        if not filepath.exists():
            return {}

        try:
            import yaml
        except ImportError:
            return {}

        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_config(self, env: ConfigEnv | str | None = None) -> AppConfig:
        """加载完整配置。

        加载顺序：
        1. default.yaml（基础配置）
        2. {env}.yaml（环境覆盖）
        3. 环境变量覆盖

        Args:
            env: 配置环境（默认从 APP_ENV 环境变量读取）

        Returns:
            AppConfig: 完整应用配置
        """
        if env is None:
            env = os.environ.get("APP_ENV", "development")

        if isinstance(env, str):
            env = ConfigEnv(env)

        # 加载 YAML
        base_config = self.load_yaml("default.yaml")
        env_config = self.load_yaml(f"{env.value}.yaml")

        # 合并 YAML（环境覆盖默认）
        merged = _deep_merge(base_config, env_config)

        # 环境变量覆盖
        merged = _apply_env_overrides(merged)

        # 设置环境
        merged["env"] = env.value

        return AppConfig(**merged)

    def load_feature_flags(self, env: ConfigEnv | str | None = None) -> FeatureFlags:
        """仅加载 feature flags。

        Args:
            env: 配置环境

        Returns:
            FeatureFlags: feature flags 配置
        """
        config = self.load_config(env)
        return config.feature_flags


# ===========================================================================
# 辅助函数
# ===========================================================================

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个字典。

    override 中的值覆盖 base 中的同名值。
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """应用环境变量覆盖。

    支持的覆盖格式：
    - APP_ 前缀的环境变量覆盖顶层配置
    - FEATURE_ 前缀覆盖 feature flags
    """
    # Feature flags 覆盖
    feature_overrides: dict[str, Any] = {}
    for key, value in os.environ.items():
        if key.startswith("FEATURE_"):
            flag_name = key[8:].lower()  # 去掉 FEATURE_ 前缀
            feature_overrides[flag_name] = _parse_bool(value)

    if feature_overrides:
        config.setdefault("feature_flags", {})
        config["feature_flags"].update(feature_overrides)

    # 通知覆盖
    if os.environ.get("BARK_KEY"):
        config.setdefault("notification", {})
        config["notification"]["bark_key"] = os.environ["BARK_KEY"]

    return config


def _parse_bool(value: str) -> bool:
    """解析布尔值。"""
    return value.lower() in ("true", "1", "yes", "on")


# ===========================================================================
# 模块级单例
# ===========================================================================

_loader: ConfigLoader | None = None
_config: AppConfig | None = None


def get_config_loader() -> ConfigLoader:
    """获取全局 ConfigLoader 单例。"""
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
    return _loader


def get_config() -> AppConfig:
    """获取全局 AppConfig 单例。"""
    global _config
    if _config is None:
        _config = get_config_loader().load_config()
    return _config


def get_feature_flags() -> FeatureFlags:
    """获取 feature flags。"""
    return get_config().feature_flags


def is_feature_enabled(flag_name: str) -> bool:
    """检查 feature flag 是否启用。

    Args:
        flag_name: flag 名称（如 "deep_agents_research"）

    Returns:
        True 如果启用
    """
    flags = get_feature_flags()
    return getattr(flags, flag_name, False)
