from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from crypto_alert_v2.domain.models import Action, OPENING_ACTIONS, Symbol
from crypto_alert_v2.observability.redaction import redact_text


class DecisionEntryKind(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    POSTMORTEM = "postmortem"
    EVAL = "eval"
    REPLAY = "replay"
    SYSTEM = "system"


class DecisionIntent(StrEnum):
    MARKET_ANALYSIS = "market_analysis"
    DEEP_RESEARCH = "deep_research"
    MONITOR_REVIEW = "monitor_review"
    POSTMORTEM = "postmortem"
    EVALUATION = "evaluation"
    REPLAY = "replay"
    SYSTEM_QUERY = "system_query"
    UNKNOWN = "unknown"


class DecisionComplexity(StrEnum):
    SIMPLE_FAST = "simple_fast"
    STANDARD = "standard"
    DEEP_RESEARCH = "deep_research"
    EVAL_REPLAY = "eval_replay"
    BLOCKED_CLARIFY = "blocked_clarify"


class PositionSide(StrEnum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class RiskMode(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class LiveSideEffectPolicy(BaseModel):
    """Explicit capabilities for one request; trade and notification stay impossible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    live_market_data: bool = False
    live_web_research: bool = False
    product_writes: bool = False
    external_notifications: Literal[False] = False
    trade_execution: Literal[False] = False


class PositionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    side: PositionSide
    entry_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    size: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    leverage: Decimal | None = Field(
        default=None,
        ge=1,
        le=125,
        allow_inf_nan=False,
    )


class RiskContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: RiskMode = RiskMode.BALANCED
    max_loss_quote: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    max_position_notional: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )


class DecisionRequest(BaseModel):
    """Product request envelope; it does not own execution or Graph state."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = "1.0"
    entry_kind: DecisionEntryKind
    actor_id: StrictStr = Field(min_length=1, max_length=255)
    workspace_id: StrictStr = Field(min_length=1, max_length=255)
    session_id: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    intent: DecisionIntent
    intent_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    complexity: DecisionComplexity
    symbol: Symbol | None = None
    horizon: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    query_text: StrictStr = Field(min_length=1, max_length=4000)
    requested_action: Action | None = None
    position: PositionContext | None = None
    risk: RiskContext = Field(default_factory=RiskContext)
    side_effects: LiveSideEffectPolicy = Field(default_factory=LiveSideEffectPolicy)
    source_reference_id: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    @field_validator("query_text")
    @classmethod
    def redact_sensitive_query(cls, value: str) -> str:
        return redact_text(value)

    @model_validator(mode="after")
    def reject_live_providers_for_non_live_entry(self) -> Self:
        if self.entry_kind in {
            DecisionEntryKind.POSTMORTEM,
            DecisionEntryKind.EVAL,
            DecisionEntryKind.REPLAY,
            DecisionEntryKind.SYSTEM,
        } and (
            self.side_effects.live_market_data
            or self.side_effects.live_web_research
        ):
            raise ValueError(f"{self.entry_kind.value} cannot use live providers")
        return self


DecisionRouteStatus = Literal["admitted", "blocked_clarify", "unsupported_mode"]
ExecutableTaskType = Literal["market_analysis", "deep_research"]


class DecisionRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: DecisionRouteStatus
    complexity: DecisionComplexity
    task_type: ExecutableTaskType | None = None
    missing_slots: tuple[StrictStr, ...] = ()
    reason: StrictStr = Field(min_length=1, max_length=255)


_NON_LIVE_INTENTS = {
    DecisionIntent.POSTMORTEM,
    DecisionIntent.EVALUATION,
    DecisionIntent.REPLAY,
    DecisionIntent.SYSTEM_QUERY,
}


def _missing_execution_slots(request: DecisionRequest) -> tuple[str, ...]:
    missing: list[str] = []
    if request.symbol is None:
        missing.append("symbol")
    if request.horizon is None:
        missing.append("horizon")
    if request.requested_action not in OPENING_ACTIONS:
        return tuple(missing)
    if request.position is None:
        missing.extend(
            (
                "position",
                "position.entry_price",
                "position.size",
                "position.leverage",
            )
        )
    else:
        if request.position.entry_price is None:
            missing.append("position.entry_price")
        if request.position.size is None:
            missing.append("position.size")
        if request.position.leverage is None:
            missing.append("position.leverage")
    if request.risk.max_loss_quote is None:
        missing.append("risk.max_loss_quote")
    return tuple(missing)


def route_decision_request(request: DecisionRequest) -> DecisionRoute:
    """Apply deterministic admission policy before invoking the canonical Graph."""

    if request.intent is DecisionIntent.UNKNOWN:
        return DecisionRoute(
            status="blocked_clarify",
            complexity=DecisionComplexity.BLOCKED_CLARIFY,
            missing_slots=("intent",),
            reason="intent requires clarification",
        )
    if request.intent in _NON_LIVE_INTENTS:
        return DecisionRoute(
            status="unsupported_mode",
            complexity=DecisionComplexity.EVAL_REPLAY,
            reason="request is typed but has no live Graph executor",
        )

    missing_slots = _missing_execution_slots(request)
    if missing_slots:
        return DecisionRoute(
            status="blocked_clarify",
            complexity=DecisionComplexity.BLOCKED_CLARIFY,
            missing_slots=missing_slots,
            reason="required request slots are missing",
        )

    if request.intent is DecisionIntent.DEEP_RESEARCH:
        task_type: ExecutableTaskType = "deep_research"
        complexity = DecisionComplexity.DEEP_RESEARCH
    else:
        task_type = "market_analysis"
        complexity = request.complexity
        if complexity in {
            DecisionComplexity.DEEP_RESEARCH,
            DecisionComplexity.EVAL_REPLAY,
            DecisionComplexity.BLOCKED_CLARIFY,
        }:
            complexity = DecisionComplexity.STANDARD
    return DecisionRoute(
        status="admitted",
        complexity=complexity,
        task_type=task_type,
        reason="request admitted to existing Product execution",
    )


__all__ = [
    "DecisionComplexity",
    "DecisionEntryKind",
    "DecisionIntent",
    "DecisionRequest",
    "DecisionRoute",
    "DecisionRouteStatus",
    "ExecutableTaskType",
    "LiveSideEffectPolicy",
    "PositionContext",
    "PositionSide",
    "RiskContext",
    "RiskMode",
    "route_decision_request",
]
