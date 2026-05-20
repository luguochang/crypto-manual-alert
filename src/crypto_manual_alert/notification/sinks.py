from __future__ import annotations

import os
from urllib.parse import quote

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import DecisionPlan, NotificationResult, RiskVerdict


class NotificationSink:
    def send(self, plan: DecisionPlan, verdict: RiskVerdict) -> NotificationResult:
        raise NotImplementedError


class NoopNotificationSink(NotificationSink):
    def send(self, plan: DecisionPlan, verdict: RiskVerdict) -> NotificationResult:
        return NotificationResult(ok=True, status_code=None, error="notification disabled")


class BarkNotificationSink(NotificationSink):
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.notification.bark_base_url.rstrip("/")
        self.device_key = os.getenv(config.notification.bark_device_key_env, "")
        if config.notification.enabled and not self.device_key:
            raise ValueError(f"{config.notification.bark_device_key_env} is required when notification.enabled=true")

    def send(self, plan: DecisionPlan, verdict: RiskVerdict) -> NotificationResult:
        title = f"{plan.instrument} {plan.main_action} {self._probability(plan)}"
        body = self._body(plan, verdict)
        if len(body) > self.config.notification.max_body_chars:
            body = body[: self.config.notification.max_body_chars - 20] + "\n...truncated"
        url = f"{self.base_url}/{quote(self.device_key, safe='')}/{quote(title, safe='')}/{quote(body, safe='')}"
        last_error: str | None = None
        for _ in range(self.config.notification.retry_count + 1):
            try:
                response = httpx.get(url, timeout=self.config.notification.timeout_seconds)
                if response.status_code < 400:
                    return NotificationResult(ok=True, status_code=response.status_code)
                last_error = f"HTTP {response.status_code}"
            except Exception as exc:  # noqa: BLE001 - 通知失败只能降级为审计记录，不能改变交易判断。
                last_error = f"{type(exc).__name__}: {exc}"
        return NotificationResult(ok=False, error=redact(last_error or "unknown notification error", [self.device_key]))

    def _probability(self, plan: DecisionPlan) -> str:
        if plan.probability is None:
            return ""
        return f"{round(plan.probability * 100)}%"

    def _body(self, plan: DecisionPlan, verdict: RiskVerdict) -> str:
        allowed_text = "可手动核对" if verdict.allowed else "风控阻断"
        lines = [
            f"状态：{allowed_text}",
            "强提醒：系统不会自动下单，请打开 OKX App 手动核对。",
            f"Plan ID：{plan.plan_id}",
            f"有效期：{plan.expires_at.isoformat()}",
            f"入场/触发：{plan.entry_trigger}",
            f"止损：{plan.stop_price}",
            f"T1/T2：{plan.target_1} / {plan.target_2}",
            f"风险：{plan.risk_pct}% 杠杆≤{plan.max_leverage}",
            f"反向理由：{plan.why_not_opposite}",
        ]
        if verdict.reasons:
            lines.append("阻断原因：" + "; ".join(verdict.reasons))
        if verdict.warnings:
            lines.append("警告：" + "; ".join(verdict.warnings))
        if plan.unavailable_data:
            lines.append("数据缺口：" + ", ".join(plan.unavailable_data))
        return "\n".join(lines)


def redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted
