"""告警规则 - 9 条告警规则的触发和通知。

来源：V2技术设计缺口补充.md 第 9.3 节。

9 条告警规则：
| 告警                    | 条件                        | 通道          | 严重度   |
|-------------------------|----------------------------|---------------|----------|
| Agent Server 不可用      | health check 连续 3 次失败  | Email + Bark  | Critical |
| PostgreSQL 连接失败      | 连接池耗尽或连接超时         | Email         | Critical |
| Redis 不可用            | Agent Server 报错           | Email         | Critical |
| OKX API 连续失败        | 5 分钟内失败率 > 50%        | Email         | Warning  |
| 模型调用连续超时         | 10 分钟内超时率 > 30%       | Email         | Warning  |
| LangSmith/Langfuse 不可用| 上报失败连续 10 分钟        | Email         | Info     |
| Run 成功率下降          | 1 小时内 failed 率 > 20%    | Email         | Warning  |
| 通知发送失败率          | 1 小时内 failed 率 > 10%    | Email         | Warning  |
| 月度成本超预算          | workspace 月用量 > 配额 80% | In-app + Email| Warning  |
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field


# ===========================================================================
# 告警级别
# ===========================================================================

class AlertSeverity(str, Enum):
    """告警严重度。"""
    CRITICAL = "critical"  # 系统不可用，需立即处理
    WARNING = "warning"    # 业务降级，需关注
    INFO = "info"          # 信息性告警，不紧急


class AlertChannel(str, Enum):
    """告警通知通道。"""
    EMAIL = "email"
    BARK = "bark"
    IN_APP = "in_app"


class AlertStatus(str, Enum):
    """告警状态。"""
    FIRING = "firing"      # 正在触发
    RESOLVED = "resolved"  # 已恢复


# ===========================================================================
# 告警定义
# ===========================================================================

class AlertRule(BaseModel):
    """告警规则定义。"""
    id: str = Field(description="规则 ID")
    name: str = Field(description="告警名称")
    description: str = Field(description="告警描述")
    severity: AlertSeverity = Field(description="严重度")
    channels: list[AlertChannel] = Field(description="通知通道")
    condition: str = Field(description="触发条件描述")
    window_minutes: int = Field(default=5, description="检测窗口（分钟）")
    threshold: float = Field(description="触发阈值")
    cooldown_minutes: int = Field(
        default=30, description="冷却时间（分钟），避免重复告警"
    )


# 9 条告警规则定义
ALERT_RULES: list[AlertRule] = [
    AlertRule(
        id="agent_server_unavailable",
        name="Agent Server 不可用",
        description="Agent Server health check 连续 3 次失败",
        severity=AlertSeverity.CRITICAL,
        channels=[AlertChannel.EMAIL, AlertChannel.BARK],
        condition="health_check_consecutive_failures >= 3",
        window_minutes=5,
        threshold=3,
        cooldown_minutes=10,
    ),
    AlertRule(
        id="postgres_connection_failed",
        name="PostgreSQL 连接失败",
        description="PostgreSQL 连接池耗尽或连接超时",
        severity=AlertSeverity.CRITICAL,
        channels=[AlertChannel.EMAIL],
        condition="postgres_connection_error",
        window_minutes=1,
        threshold=1,
        cooldown_minutes=5,
    ),
    AlertRule(
        id="redis_unavailable",
        name="Redis 不可用",
        description="Redis 连接失败，Agent Server 报错",
        severity=AlertSeverity.CRITICAL,
        channels=[AlertChannel.EMAIL],
        condition="redis_connection_error",
        window_minutes=1,
        threshold=1,
        cooldown_minutes=5,
    ),
    AlertRule(
        id="okx_api_failures",
        name="OKX API 连续失败",
        description="5 分钟内 OKX API 失败率 > 50%",
        severity=AlertSeverity.WARNING,
        channels=[AlertChannel.EMAIL],
        condition="okx_failure_rate_5min > 0.5",
        window_minutes=5,
        threshold=0.5,
        cooldown_minutes=15,
    ),
    AlertRule(
        id="model_call_timeouts",
        name="模型调用连续超时",
        description="10 分钟内模型调用超时率 > 30%",
        severity=AlertSeverity.WARNING,
        channels=[AlertChannel.EMAIL],
        condition="model_timeout_rate_10min > 0.3",
        window_minutes=10,
        threshold=0.3,
        cooldown_minutes=15,
    ),
    AlertRule(
        id="telemetry_unavailable",
        name="LangSmith/Langfuse 不可用",
        description="遥测上报失败连续 10 分钟",
        severity=AlertSeverity.INFO,
        channels=[AlertChannel.EMAIL],
        condition="telemetry_report_failed_10min",
        window_minutes=10,
        threshold=1,
        cooldown_minutes=60,
    ),
    AlertRule(
        id="run_success_rate_drop",
        name="Run 成功率下降",
        description="1 小时内 Run failed 率 > 20%",
        severity=AlertSeverity.WARNING,
        channels=[AlertChannel.EMAIL],
        condition="run_failure_rate_1h > 0.2",
        window_minutes=60,
        threshold=0.2,
        cooldown_minutes=30,
    ),
    AlertRule(
        id="notification_failure_rate",
        name="通知发送失败率",
        description="1 小时内通知 failed 率 > 10%",
        severity=AlertSeverity.WARNING,
        channels=[AlertChannel.EMAIL],
        condition="notification_failure_rate_1h > 0.1",
        window_minutes=60,
        threshold=0.1,
        cooldown_minutes=30,
    ),
    AlertRule(
        id="monthly_cost_over_budget",
        name="月度成本超预算",
        description="workspace 月用量 > 配额 80%",
        severity=AlertSeverity.WARNING,
        channels=[AlertChannel.IN_APP, AlertChannel.EMAIL],
        condition="monthly_cost / monthly_budget > 0.8",
        window_minutes=60,  # 每小时检查一次
        threshold=0.8,
        cooldown_minutes=1440,  # 24 小时冷却
    ),
]


# ===========================================================================
# 告警事件
# ===========================================================================

class AlertEvent(BaseModel):
    """告警事件。"""
    rule_id: str = Field(description="触发的规则 ID")
    rule_name: str = Field(description="规则名称")
    severity: AlertSeverity = Field(description="严重度")
    status: AlertStatus = Field(description="状态")
    message: str = Field(description="告警消息")
    details: dict[str, Any] = Field(default_factory=dict, description="告警详情")
    fired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = Field(default=None)


# ===========================================================================
# 告警引擎
# ===========================================================================

@dataclass
class _RuleState:
    """规则内部状态。"""
    last_fired: datetime | None = None
    consecutive_failures: int = 0
    recent_events: list[datetime] = field(default_factory=list)


class AlertEngine:
    """告警引擎。

    管理告警规则的状态、触发条件和冷却时间。
    """

    def __init__(self, rules: list[AlertRule] | None = None) -> None:
        """初始化告警引擎。

        Args:
            rules: 告警规则列表（默认使用 ALERT_RULES）
        """
        self.rules = rules or ALERT_RULES
        self._states: dict[str, _RuleState] = {
            rule.id: _RuleState() for rule in self.rules
        }
        self._active_alerts: list[AlertEvent] = []
        self._handlers: list[Callable[[AlertEvent], None]] = []

    def add_handler(self, handler: Callable[[AlertEvent], None]) -> None:
        """添加告警处理函数。

        Args:
            handler: 处理函数，接收 AlertEvent
        """
        self._handlers.append(handler)

    def check_rule(
        self,
        rule_id: str,
        value: float,
        details: dict[str, Any] | None = None,
    ) -> AlertEvent | None:
        """检查单条规则是否触发。

        Args:
            rule_id: 规则 ID
            value: 当前指标值
            details: 告警详情

        Returns:
            AlertEvent 如果触发，否则 None
        """
        rule = next((r for r in self.rules if r.id == rule_id), None)
        if rule is None:
            return None

        state = self._states.get(rule_id)
        if state is None:
            return None

        now = datetime.now(timezone.utc)

        # 检查冷却
        if state.last_fired:
            cooldown = timedelta(minutes=rule.cooldown_minutes)
            if now - state.last_fired < cooldown:
                return None

        # 检查阈值
        if value > rule.threshold or (rule.threshold == 1 and value >= 1):
            event = AlertEvent(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                status=AlertStatus.FIRING,
                message=f"{rule.name}: {rule.description} (当前值: {value:.2%}, 阈值: {rule.threshold:.2%})",
                details=details or {},
            )
            state.last_fired = now
            self._active_alerts.append(event)
            self._notify_handlers(event)
            return event

        return None

    def check_health(
        self,
        health_status: dict[str, Any],
    ) -> list[AlertEvent]:
        """检查健康状态触发的告警。

        Args:
            health_status: 健康检查结果（/internal/health 的返回）

        Returns:
            触发的告警事件列表
        """
        events: list[AlertEvent] = []
        now = datetime.now(timezone.utc)

        for rule in self.rules:
            state = self._states[rule.id]

            if rule.id == "agent_server_unavailable":
                healthy = health_status.get("status") == "healthy"
                if not healthy:
                    state.consecutive_failures += 1
                else:
                    state.consecutive_failures = 0

                if state.consecutive_failures >= rule.threshold:
                    event = self.check_rule(
                        rule.id,
                        float(state.consecutive_failures),
                        {"consecutive_failures": state.consecutive_failures},
                    )
                    if event:
                        events.append(event)

            elif rule.id == "postgres_connection_failed":
                pg_status = health_status.get("checks", {}).get("postgres", {})
                if pg_status.get("status") != "healthy":
                    event = self.check_rule(
                        rule.id, 1.0, {"postgres_detail": pg_status}
                    )
                    if event:
                        events.append(event)

            elif rule.id == "redis_unavailable":
                redis_status = health_status.get("checks", {}).get("redis", {})
                if redis_status.get("status") != "healthy":
                    event = self.check_rule(
                        rule.id, 1.0, {"redis_detail": redis_status}
                    )
                    if event:
                        events.append(event)

        return events

    def check_okx_failures(
        self,
        failure_rate: float,
        window_minutes: int = 5,
    ) -> AlertEvent | None:
        """检查 OKX API 失败率。"""
        return self.check_rule(
            "okx_api_failures",
            failure_rate,
            {"window_minutes": window_minutes, "failure_rate": failure_rate},
        )

    def check_model_timeouts(
        self,
        timeout_rate: float,
        window_minutes: int = 10,
    ) -> AlertEvent | None:
        """检查模型调用超时率。"""
        return self.check_rule(
            "model_call_timeouts",
            timeout_rate,
            {"window_minutes": window_minutes, "timeout_rate": timeout_rate},
        )

    def check_run_failure_rate(
        self,
        failure_rate: float,
        window_minutes: int = 60,
    ) -> AlertEvent | None:
        """检查 Run 失败率。"""
        return self.check_rule(
            "run_success_rate_drop",
            failure_rate,
            {"window_minutes": window_minutes, "failure_rate": failure_rate},
        )

    def check_notification_failure_rate(
        self,
        failure_rate: float,
        window_minutes: int = 60,
    ) -> AlertEvent | None:
        """检查通知失败率。"""
        return self.check_rule(
            "notification_failure_rate",
            failure_rate,
            {"window_minutes": window_minutes, "failure_rate": failure_rate},
        )

    def check_monthly_cost(
        self,
        current_cost: float,
        budget: float,
    ) -> AlertEvent | None:
        """检查月度成本。"""
        if budget <= 0:
            return None
        ratio = current_cost / budget
        return self.check_rule(
            "monthly_cost_over_budget",
            ratio,
            {"current_cost": current_cost, "budget": budget, "ratio": ratio},
        )

    def check_telemetry(
        self,
        report_failed: bool,
        duration_minutes: int = 10,
    ) -> AlertEvent | None:
        """检查遥测上报。"""
        if report_failed and duration_minutes >= 10:
            return self.check_rule(
                "telemetry_unavailable",
                1.0,
                {"duration_minutes": duration_minutes},
            )
        return None

    def get_active_alerts(self) -> list[AlertEvent]:
        """获取当前活跃的告警。"""
        return [a for a in self._active_alerts if a.status == AlertStatus.FIRING]

    def resolve_alert(self, rule_id: str) -> AlertEvent | None:
        """恢复告警。

        Args:
            rule_id: 规则 ID

        Returns:
            已恢复的 AlertEvent，或 None
        """
        for alert in self._active_alerts:
            if alert.rule_id == rule_id and alert.status == AlertStatus.FIRING:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now(timezone.utc)
                self._notify_handlers(alert)
                return alert
        return None

    def _notify_handlers(self, event: AlertEvent) -> None:
        """通知所有处理函数。"""
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                pass  # 告警处理失败不应影响主流程


# ===========================================================================
# 默认告警引擎单例
# ===========================================================================

_engine: AlertEngine | None = None


def get_alert_engine() -> AlertEngine:
    """获取全局 AlertEngine 单例。"""
    global _engine
    if _engine is None:
        _engine = AlertEngine()
    return _engine


# ===========================================================================
# 通知发送（占位实现）
# ===========================================================================

async def send_alert_notification(event: AlertEvent) -> None:
    """发送告警通知。

    根据 AlertRule 的 channels 配置，发送到对应通道。
    Phase 6 占位实现：仅记录日志，实际使用时接入邮件/Bark 服务。

    Args:
        event: 告警事件
    """
    from crypto_alert_v2.observability.logging import get_logger

    logger = get_logger("alerts")
    logger.warning(
        "alert_triggered",
        rule_id=event.rule_id,
        rule_name=event.rule_name,
        severity=event.severity.value,
        status=event.status.value,
        message=event.message,
        details=event.details,
    )
