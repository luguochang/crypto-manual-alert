from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from crypto_alert_v2.domain.models import Action, Artifact, Symbol
from crypto_alert_v2.domain.deep_research import (
    DeepResearchArtifact,
    DeepResearchReport,
)
from crypto_alert_v2.observability.redaction import redact_text


ReviewPolicy = Literal["bypass", "required"]
ReviewAction = Literal["approve", "reject", "edit"]


class ArtifactReviewPayload(BaseModel):
    """Canonical public contract for an official artifact review interrupt."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["artifact_review"] = "artifact_review"
    schema_version: Literal["1.0"] = "1.0"
    allowed_actions: tuple[
        Literal["approve"],
        Literal["reject"],
        Literal["edit"],
    ] = ("approve", "reject", "edit")
    review_iteration: int = Field(ge=1)
    artifact: Artifact

    @model_validator(mode="after")
    def require_reviewable_draft(self) -> Self:
        if self.artifact.status != "draft":
            raise ValueError("artifact review payload requires a draft artifact")
        return self


class DeepResearchReviewPayload(BaseModel):
    """Canonical review interrupt for a typed deep-research draft."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["deep_research_review"] = "deep_research_review"
    schema_version: Literal["1.0"] = "1.0"
    allowed_actions: tuple[
        Literal["approve"],
        Literal["reject"],
        Literal["edit"],
    ] = ("approve", "reject", "edit")
    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    review_iteration: int = Field(ge=1)
    artifact: DeepResearchArtifact

    @model_validator(mode="after")
    def require_reviewable_draft(self) -> Self:
        if self.artifact.status != "draft":
            raise ValueError("deep research review payload requires a draft artifact")
        return self


ReviewInterruptPayload = Annotated[
    ArtifactReviewPayload | DeepResearchReviewPayload,
    Field(discriminator="kind"),
]
_REVIEW_INTERRUPT_PAYLOAD_ADAPTER = TypeAdapter(ReviewInterruptPayload)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: Literal["market_analysis"] = "market_analysis"
    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=2000)
    notify: bool = False

    @field_validator("query_text")
    @classmethod
    def redact_sensitive_query(cls, value: str) -> str:
        return redact_text(value)


class DeepResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: Literal["deep_research"] = "deep_research"
    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=4000)

    @field_validator("query_text")
    @classmethod
    def redact_sensitive_query(cls, value: str) -> str:
        return redact_text(value)


class ArtifactEdit(BaseModel):
    """Allowed human corrections to analysis content, excluding execution identity."""

    model_config = ConfigDict(extra="forbid")

    regime: (
        Literal["risk_on", "risk_off", "event_compression", "surprise_repricing"] | None
    ) = None
    factor_scores: dict[str, int] | None = None
    total_score: int | None = None
    main_action: Action | None = None
    reference_price: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    entry_trigger: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    stop_price: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    target_1: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    target_2: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    position_size_class: Literal["light", "standard", "heavy", "none"] | None = None
    max_leverage: int | None = Field(default=None, ge=1)
    risk_pct: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    root_cause_chain: list[str] | None = Field(default=None, min_length=1)
    why_not_opposite: str | None = Field(default=None, min_length=1)
    invalidation: str | None = Field(default=None, min_length=1)
    unavailable_data: list[str] | None = None
    manual_execution_required: bool | None = None
    expires_in_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_a_correction(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one artifact edit is required")
        return self


class DeepResearchReportEdit(BaseModel):
    """A complete typed report replacement; source provenance stays server-owned."""

    model_config = ConfigDict(extra="forbid")

    report: DeepResearchReport


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    edits: ArtifactEdit | DeepResearchReportEdit | None = None
    comment: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_action_payload(self) -> Self:
        if self.action == "edit" and self.edits is None:
            raise ValueError("edit review responses require edits")
        if self.action != "edit" and self.edits is not None:
            raise ValueError("only edit review responses may include edits")
        return self


def validate_review_response_for_payload(
    payload: ArtifactReviewPayload | DeepResearchReviewPayload,
    response: ReviewResponse,
) -> ReviewResponse:
    """Fail closed before a response mutates Product or Graph review state."""

    if response.action != "edit":
        return response
    if isinstance(payload, ArtifactReviewPayload):
        if not isinstance(response.edits, ArtifactEdit):
            raise ValueError("analysis review requires an artifact edit")
        return response
    if not isinstance(response.edits, DeepResearchReportEdit):
        raise ValueError("deep research review requires a deep research report edit")
    if response.edits.report == payload.artifact.report:
        raise ValueError("deep research edits must change the report")
    DeepResearchArtifact.model_validate(
        {
            **payload.artifact.model_dump(mode="json"),
            "report": response.edits.report.model_dump(mode="json"),
        }
    )
    return response


def parse_review_interrupt_payload(value: object) -> ReviewInterruptPayload:
    return _REVIEW_INTERRUPT_PAYLOAD_ADAPTER.validate_python(value)


def validate_review_payload_for_task(
    payload: ArtifactReviewPayload | DeepResearchReviewPayload,
    *,
    task_type: Literal["market_analysis", "deep_research"],
    symbol: Symbol,
    horizon: str,
) -> None:
    if task_type == "market_analysis":
        if not isinstance(payload, ArtifactReviewPayload):
            raise ValueError("market analysis task requires an artifact review payload")
        if payload.artifact.analysis.instrument != symbol:
            raise ValueError("analysis review instrument does not match the task")
        if payload.artifact.analysis.horizon != horizon:
            raise ValueError("analysis review horizon does not match the task")
        return
    if not isinstance(payload, DeepResearchReviewPayload):
        raise ValueError("deep research task requires a deep research review payload")
    if payload.symbol != symbol:
        raise ValueError("deep research review symbol does not match the task")
    if payload.horizon != horizon:
        raise ValueError("deep research review horizon does not match the task")


__all__ = [
    "AnalysisRequest",
    "DeepResearchRequest",
    "DeepResearchReportEdit",
    "DeepResearchReviewPayload",
    "ArtifactEdit",
    "ReviewAction",
    "ReviewPolicy",
    "ReviewResponse",
    "ReviewInterruptPayload",
    "parse_review_interrupt_payload",
    "validate_review_payload_for_task",
    "validate_review_response_for_payload",
]
