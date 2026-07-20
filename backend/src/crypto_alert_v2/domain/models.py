from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


Symbol = Literal["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
Action = Literal[
    "open_long",
    "open_short",
    "hold_long",
    "hold_short",
    "close_long",
    "close_short",
    "flip_long_to_short",
    "flip_short_to_long",
    "trigger_long",
    "trigger_short",
    "no_trade",
]

OPENING_ACTIONS = frozenset(
    {
        "open_long",
        "open_short",
        "trigger_long",
        "trigger_short",
        "flip_long_to_short",
        "flip_short_to_long",
    }
)
ALL_ACTIONS = frozenset(Action.__args__)
SUPPORTED_SYMBOLS: tuple[Symbol, ...] = (
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP",
)

PositiveDecimal = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
FactorScore = Annotated[int, Field(ge=-2, le=2)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriceLevel(DomainModel):
    price: PositiveDecimal
    size: PositiveDecimal

    @model_validator(mode="before")
    @classmethod
    def parse_exchange_level(cls, value: object) -> object:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return {"price": value[0], "size": value[1]}
        return value


class Ticker(DomainModel):
    last: PositiveDecimal
    bid: PositiveDecimal | None = None
    ask: PositiveDecimal | None = None
    volume_24h: NonNegativeDecimal | None = Field(
        default=None,
        validation_alias=AliasChoices("volume_24h", "vol_24h"),
    )

    @model_validator(mode="after")
    def validate_spread(self) -> Self:
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("ticker bid cannot exceed ask")
        return self


class OrderBook(DomainModel):
    bids: list[PriceLevel] = Field(default_factory=list)
    asks: list[PriceLevel] = Field(default_factory=list)


class Candle(DomainModel):
    timestamp: datetime = Field(validation_alias=AliasChoices("timestamp", "ts"))
    open: PositiveDecimal = Field(validation_alias=AliasChoices("open", "o"))
    high: PositiveDecimal = Field(validation_alias=AliasChoices("high", "h"))
    low: PositiveDecimal = Field(validation_alias=AliasChoices("low", "l"))
    close: PositiveDecimal = Field(validation_alias=AliasChoices("close", "c"))
    volume: NonNegativeDecimal = Field(validation_alias=AliasChoices("volume", "vol"))

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("candle OHLC values are inconsistent")
        if self.low > self.high:
            raise ValueError("candle low cannot exceed high")
        return self


class MarketSnapshot(DomainModel):
    symbol: Symbol
    fetched_at: datetime
    source_level: Literal[
        "exchange_native",
        "web_search_verified",
        "controlled_dependency",
    ]
    ticker: Ticker | None = None
    mark_price: PositiveDecimal | None = None
    index_price: PositiveDecimal | None = None
    funding_rate: Decimal | None = Field(default=None, allow_inf_nan=False)
    open_interest: NonNegativeDecimal | None = None
    order_book: OrderBook | None = None
    candles: list[Candle] = Field(default_factory=list)


class ResearchFinding(DomainModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https?://")
    fetched_at: datetime
    published_at: datetime | None = None


class ResearchBundle(DomainModel):
    vix: NonNegativeDecimal | None = None
    real_yield_10y: Decimal | None = Field(default=None, allow_inf_nan=False)
    dxy: PositiveDecimal | None = None
    macro_event_scan: list[ResearchFinding] | None = None
    findings: list[ResearchFinding] = Field(default_factory=list)
    source_conflicts: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class MarketAnalysis(DomainModel):
    regime: Literal["risk_on", "risk_off", "event_compression", "surprise_repricing"]
    factor_scores: dict[str, FactorScore]
    total_score: int
    main_action: Action
    instrument: Symbol
    horizon: str = Field(min_length=1)
    reference_price: PositiveDecimal
    entry_trigger: PositiveDecimal | None = None
    stop_price: PositiveDecimal | None = None
    target_1: PositiveDecimal | None = None
    target_2: PositiveDecimal | None = None
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    position_size_class: Literal["light", "standard", "heavy", "none"] = "none"
    max_leverage: int = Field(ge=1)
    risk_pct: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    root_cause_chain: list[str] = Field(min_length=1)
    why_not_opposite: str = Field(min_length=1)
    invalidation: str
    unavailable_data: list[str] = Field(default_factory=list)
    manual_execution_required: bool = True
    expires_in_seconds: int = Field(gt=0)

    @field_validator("root_cause_chain")
    @classmethod
    def validate_root_causes(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("root cause entries cannot be blank")
        return values


class EvidenceVerdict(DomainModel):
    sufficient: bool
    confidence_cap: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    missing_required: list[str] = Field(default_factory=list)
    missing_optional: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        if self.sufficient and self.missing_required:
            raise ValueError("sufficient evidence cannot have missing required fields")
        if not self.sufficient and not self.missing_required:
            raise ValueError(
                "insufficient evidence must identify missing required fields"
            )
        if not self.sufficient and self.confidence_cap != 0:
            raise ValueError("insufficient evidence must have a zero confidence cap")
        return self


class RiskBudget(DomainModel):
    allowed_symbols: tuple[Symbol, ...] = Field(default=SUPPORTED_SYMBOLS, min_length=1)
    max_leverage: int = Field(default=2, ge=1)
    max_risk_pct: Decimal = Field(default=Decimal("0.25"), gt=0, le=1)
    auto_order_enabled: bool = False


class RiskVerdict(DomainModel):
    allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence_cap: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        if self.allowed and self.blocked_reasons:
            raise ValueError("allowed risk verdict cannot have blocked reasons")
        if not self.allowed and not self.blocked_reasons:
            raise ValueError("blocked risk verdict must identify at least one reason")
        return self


class ModelExecutionAudit(DomainModel):
    """Non-sensitive audit metadata for one official LangChain agent result."""

    prompt_version: str = Field(min_length=1, max_length=128)
    call_count: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    observation_ids: list[str] = Field(default_factory=list, max_length=32)


class ArtifactProvenance(DomainModel):
    """Auditable provider identity without credentials or runtime internals."""

    market_provider: str = Field(min_length=1, max_length=64)
    search_provider: str = Field(min_length=1, max_length=128)
    search_parser_version: str = Field(min_length=1, max_length=128)
    model_provider: str = Field(min_length=1, max_length=64)
    model_name: str = Field(min_length=1, max_length=128)
    model_endpoint_host: str | None = Field(default=None, max_length=255)
    model_audits: list[ModelExecutionAudit] = Field(default_factory=list)


class Artifact(DomainModel):
    artifact_type: Literal["analysis_report"] = "analysis_report"
    schema_version: str = "1.0"
    content_version: int = Field(ge=1)
    status: Literal["draft", "streaming", "committed", "failed"]
    analysis: MarketAnalysis
    evidence_verdict: EvidenceVerdict
    risk_verdict: RiskVerdict
    source_references: list[str] = Field(default_factory=list)
    provenance: ArtifactProvenance | None = None
