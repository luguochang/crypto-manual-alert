from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_alert_v2.domain.models import Action, Artifact, Symbol


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


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=2000)
    notify: bool = False


class ArtifactEdit(BaseModel):
    """Allowed human corrections to analysis content, excluding execution identity."""

    model_config = ConfigDict(extra="forbid")

    regime: Literal[
        "risk_on", "risk_off", "event_compression", "surprise_repricing"
    ] | None = None
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


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    edits: ArtifactEdit | None = None
    comment: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_action_payload(self) -> Self:
        if self.action == "edit" and self.edits is None:
            raise ValueError("edit review responses require edits")
        if self.action != "edit" and self.edits is not None:
            raise ValueError("only edit review responses may include edits")
        return self


__all__ = [
    "AnalysisRequest",
    "ArtifactEdit",
    "ReviewAction",
    "ReviewPolicy",
    "ReviewResponse",
]
