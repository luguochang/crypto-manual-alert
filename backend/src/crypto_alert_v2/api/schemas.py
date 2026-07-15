from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from crypto_alert_v2.domain.models import Artifact, MarketSnapshot, Symbol
from crypto_alert_v2.graph.request import ArtifactReviewPayload, ReviewResponse
from crypto_alert_v2.providers.search import WebEvidence


IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$"


class AnalysisSubmission(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=2000)
    notify: bool = False


class ProductErrorView(BaseModel):
    code: str
    message: str
    retryable: bool = False
    provider: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    error_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    attempt: int | None = Field(default=None, ge=1, le=100)


class AgentStreamBindingView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    protocol: Literal["langgraph-v2"]
    assistant_id: StrictStr = Field(min_length=1, max_length=255)
    thread_id: StrictStr = Field(min_length=1, max_length=255)
    run_id: StrictStr = Field(min_length=1, max_length=255)


class PendingInterruptView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: StrictStr = Field(min_length=1, max_length=255)
    interrupt_id: StrictStr = Field(min_length=1, max_length=255)
    response_version: int = Field(ge=1)
    status: Literal["pending", "responding"]
    payload: ArtifactReviewPayload
    response: ReviewResponse | None = None
    expires_at: datetime | None = None
    responded_at: datetime | None = None


InboxQueryStatus = Literal[
    "active",
    "pending",
    "responding",
    "resolved",
    "expired",
    "all",
]


class InboxItemView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: StrictStr = Field(min_length=1, max_length=255)
    status: Literal["pending", "responding", "resolved", "expired", "cancelled"]
    payload: ArtifactReviewPayload
    response: ReviewResponse | None = None
    expires_at: datetime | None = None
    responded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    symbol: Symbol
    horizon: StrictStr = Field(min_length=1, max_length=32)
    query_text: StrictStr | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_coherent_response_state(self) -> "InboxItemView":
        if self.responded_at is not None and self.response is None:
            raise ValueError("responded inbox item requires its accepted response")
        if self.status == "pending" and (
            self.response is not None or self.responded_at is not None
        ):
            raise ValueError("pending inbox item cannot contain a response")
        if self.status in {"responding", "resolved"} and self.response is None:
            raise ValueError(f"{self.status} inbox item requires an accepted response")
        if self.status == "resolved" and self.responded_at is None:
            raise ValueError("resolved inbox item requires a response timestamp")
        if self.status == "expired" and self.expires_at is None:
            raise ValueError("expired inbox item requires an expiry timestamp")
        if self.payload.artifact.analysis.instrument != self.symbol:
            raise ValueError("inbox review instrument must match its task symbol")
        if self.payload.artifact.analysis.horizon != self.horizon:
            raise ValueError("inbox review horizon must match its task horizon")
        return self


class InboxView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[InboxItemView]
    next_cursor: StrictStr | None = None


class InterruptResponseSubmission(ReviewResponse):
    response_version: int = Field(ge=1)


class TaskView(BaseModel):
    task_id: str
    status: Literal[
        "queued",
        "running",
        "waiting_human",
        "succeeded",
        "blocked",
        "failed",
        "cancelled",
    ]
    symbol: Symbol
    horizon: str
    query_text: StrictStr | None = Field(default=None, min_length=1, max_length=2000)
    created_at: datetime
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    market_snapshot: MarketSnapshot | None = None
    web_evidence: list[WebEvidence] = Field(default_factory=list)
    artifact: Artifact | None = None
    errors: list[ProductErrorView] = Field(default_factory=list)
    agent_stream: AgentStreamBindingView | None = None
    pending_interrupts: list[PendingInterruptView] = Field(default_factory=list)


class RunSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    attempt: int = Field(ge=1)
    status: Literal[
        "queued",
        "running",
        "waiting_human",
        "succeeded",
        "blocked",
        "failed",
        "cancelled",
    ]
    symbol: Symbol
    horizon: str
    created_at: datetime
    finished_at: datetime | None = None
    main_action: Literal[
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
    ] | None = None


class RunListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RunSummaryView]
    limit: int = Field(ge=1, le=100)


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = "2.0.0"


class GraphExecutionError(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str = Field(min_length=1)
    retryable: bool = False


class TerminalGraphOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    terminal_status: Literal["succeeded", "blocked", "failed", "cancelled"]
    market_snapshot: MarketSnapshot | None = None
    web_evidence: list[WebEvidence] = Field(default_factory=list)
    artifact: Artifact | None = None
    errors: list[GraphExecutionError] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_terminal_contract(self) -> "TerminalGraphOutput":
        if self.terminal_status == "succeeded":
            if self.artifact is None or self.artifact.status != "committed":
                raise ValueError("succeeded output requires a committed artifact")
        elif self.terminal_status == "blocked":
            if self.artifact is None:
                raise ValueError("blocked output requires a reviewable artifact")
            if self.artifact.risk_verdict.allowed:
                raise ValueError("blocked output cannot contain an allowed risk verdict")
        return self


TaskPayload = dict[str, Any]
