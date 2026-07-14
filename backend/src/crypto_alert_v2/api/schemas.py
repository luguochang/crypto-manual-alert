from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from crypto_alert_v2.domain.models import Artifact, MarketSnapshot, Symbol
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
    market_snapshot: MarketSnapshot | None = None
    web_evidence: list[WebEvidence] = Field(default_factory=list)
    artifact: Artifact | None = None
    errors: list[ProductErrorView] = Field(default_factory=list)
    agent_stream: AgentStreamBindingView | None = None


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
