from datetime import datetime
from typing import Annotated, Any, Literal, Mapping
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictStr,
    field_validator,
    model_serializer,
    model_validator,
)

from crypto_alert_v2.api.request_identity import correlation_id_for_task
from crypto_alert_v2.domain.models import (
    Action,
    Artifact,
    EvidenceVerdict,
    MarketSnapshot,
    RiskVerdict,
    Symbol,
)
from crypto_alert_v2.domain.decision_request import (
    DecisionComplexity,
    DecisionEntryKind,
    DecisionIntent,
    DecisionRequest,
    DecisionRoute,
    LiveSideEffectPolicy,
    PositionContext,
    RiskContext,
)
from crypto_alert_v2.domain.deep_research import DeepResearchArtifact
from crypto_alert_v2.graph.request import (
    ArtifactEdit,
    ArtifactReviewPayload,
    DeepResearchReportEdit,
    DeepResearchReviewPayload,
    ReviewInterruptPayload,
    ReviewAction,
    ReviewResponse,
)
from crypto_alert_v2.observability.redaction import redact_text
from crypto_alert_v2.providers.search import WebEvidence


IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$"

MONITOR_SCHEDULES = frozenset(
    {
        "*/5 * * * *",
        "*/15 * * * *",
        "0 * * * *",
        "0 */4 * * *",
        "0 0 * * *",
    }
)


class AnalysisSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=2000)
    notify: bool = False

    @field_validator("query_text")
    @classmethod
    def redact_sensitive_query(cls, value: str) -> str:
        return redact_text(value)


class DeepResearchSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: Literal["deep_research"] = "deep_research"
    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=4000)

    @field_validator("query_text")
    @classmethod
    def redact_sensitive_query(cls, value: str) -> str:
        return redact_text(value)


class DecisionRequestSubmission(BaseModel):
    """Untrusted request body; actor and workspace are injected by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entry_kind: DecisionEntryKind
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

    def to_domain_request(
        self,
        *,
        actor_id: str,
        workspace_id: str,
    ) -> DecisionRequest:
        return DecisionRequest(
            actor_id=actor_id,
            workspace_id=workspace_id,
            **self.model_dump(),
        )


class PriceMonitorCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["price"] = "price"
    operator: Literal["gte", "lte"]
    threshold: float = Field(gt=0, allow_inf_nan=False)


class ThesisMonitorCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["thesis"] = "thesis"
    statement: StrictStr = Field(min_length=3, max_length=500)

    @field_validator("statement")
    @classmethod
    def redact_sensitive_statement(cls, value: str) -> str:
        return redact_text(value)


class ProviderHealthMonitorCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["provider_health"] = "provider_health"
    provider: Literal["okx", "tavily", "builtin_web_search"]
    consecutive_failures: int = Field(ge=1, le=10)


class ScheduledReviewMonitorCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["scheduled_review"] = "scheduled_review"


MonitorCondition = Annotated[
    PriceMonitorCondition
    | ThesisMonitorCondition
    | ProviderHealthMonitorCondition
    | ScheduledReviewMonitorCondition,
    Field(discriminator="kind"),
]
MonitorStatusFilter = Literal["running", "paused", "attention", "closed", "all"]


class MonitorQuietHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: StrictStr = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: StrictStr = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def reject_empty_window(self) -> "MonitorQuietHours":
        if self.start == self.end:
            raise ValueError("quiet-hours start and end must differ")
        return self


class MonitorCreateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: StrictStr = Field(min_length=1, max_length=120)
    artifact_id: UUID
    artifact_version_id: UUID
    run_task_type: Literal["market_analysis", "deep_research"]
    condition: MonitorCondition
    schedule: StrictStr = Field(min_length=9, max_length=32)
    timezone: StrictStr = Field(min_length=1, max_length=64)
    expires_at: datetime | None = None
    quiet_hours: MonitorQuietHours | None = None
    destination_ids: list[UUID] = Field(default_factory=list, max_length=8)

    @field_validator("schedule")
    @classmethod
    def require_supported_schedule(cls, value: str) -> str:
        if value not in MONITOR_SCHEDULES:
            raise ValueError("unsupported monitor schedule")
        return value

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA zone") from exc
        return value

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


class MonitorMutationSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class MonitorTriggerView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    trigger_kind: Literal["cron", "manual"]
    status: Literal["received", "suppressed", "admitted", "failed"]
    reason: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    task_id: UUID | None = None
    triggered_at: datetime
    created_at: datetime


class MonitorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: StrictStr = Field(min_length=1, max_length=120)
    status: Literal[
        "draft",
        "active",
        "paused",
        "degraded",
        "expired",
        "disabled",
    ]
    run_task_type: Literal["market_analysis", "deep_research"]
    artifact_id: UUID
    artifact_version_id: UUID
    symbol: Symbol
    horizon: StrictStr = Field(min_length=1, max_length=32)
    condition: MonitorCondition
    schedule: StrictStr = Field(min_length=9, max_length=32)
    timezone: StrictStr = Field(min_length=1, max_length=64)
    quiet_hours: MonitorQuietHours | None = None
    expires_at: datetime | None = None
    destination_ids: list[UUID] = Field(default_factory=list)
    version: int = Field(ge=1)
    schedule_version: int = Field(ge=1)
    cron_configured: bool
    next_run_at: datetime | None = None
    latest_trigger: MonitorTriggerView | None = None
    created_at: datetime
    updated_at: datetime


class MonitorListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MonitorView]


class MonitorTriggerListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MonitorTriggerView]


class UsageTotalsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_admission: int = Field(ge=0)
    trigger: int = Field(ge=0)
    model_token: int = Field(ge=0)
    search_request: int = Field(ge=0)
    runtime_millisecond: int = Field(ge=0)
    storage_byte: int = Field(ge=0)


class UsageEntitlementView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_task_types: list[StrictStr]
    active_monitor_limit: int = Field(ge=0)
    min_interval_seconds: int = Field(ge=1)
    max_concurrent_tasks: int = Field(ge=1)
    max_retention_days: int = Field(ge=1)
    limits: UsageTotalsView
    valid_from: datetime
    valid_until: datetime | None = None


class UsageReconciliationSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: datetime | None = None
    repair: bool = True


class UsageReconciliationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    period_start: datetime
    status: Literal["reconciled", "discrepant"]
    source_totals: UsageTotalsView
    ledger_totals: UsageTotalsView
    discrepancies: dict[str, dict[str, int]]
    source_hash: StrictStr = Field(min_length=64, max_length=64)
    ledger_hash: StrictStr = Field(min_length=64, max_length=64)
    repair_applied: bool
    created_at: datetime


class UsageGovernanceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: datetime
    entitlement: UsageEntitlementView
    totals: UsageTotalsView
    latest_reconciliation: UsageReconciliationView | None = None


DATA_LIFECYCLE_SCOPES = frozenset({"user_data"})
DATA_LIFECYCLE_DELETE_CONFIRMATION = "DELETE MY DATA"


class DataLifecyclePolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    product_retention_days: int | None = Field(default=None, ge=1, le=3650)
    artifact_retention_days: int | None = Field(default=None, ge=1, le=3650)
    task_retention_days: int | None = Field(default=None, ge=1, le=3650)
    run_retention_days: int | None = Field(default=None, ge=1, le=3650)
    decision_retention_days: int | None = Field(default=None, ge=1, le=3650)
    usage_retention_days: int | None = Field(default=None, ge=1, le=3650)
    completed_checkpoint_retention_days: int | None = Field(default=None, ge=1, le=3650)
    technical_projection_retention_days: int | None = Field(default=None, ge=1, le=3650)
    log_retention_days: int | None = Field(default=None, ge=1, le=3650)
    backup_retention_days: int | None = Field(default=None, ge=1, le=3650)
    retain_raw_prompt: bool | None = None
    retain_raw_response: bool | None = None
    legal_hold_active: bool | None = None
    legal_hold_reason: StrictStr | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_legal_hold(self) -> "DataLifecyclePolicyUpdate":
        if self.legal_hold_active is False and self.legal_hold_reason is not None:
            raise ValueError("legal_hold_reason requires an active legal hold")
        if self.legal_hold_active is True and not self.legal_hold_reason:
            raise ValueError("legal_hold_reason is required for an active legal hold")
        return self


class DataLifecyclePolicyView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    product_retention_days: int = Field(ge=1)
    artifact_retention_days: int = Field(ge=1)
    task_retention_days: int = Field(ge=1)
    run_retention_days: int = Field(ge=1)
    decision_retention_days: int = Field(ge=1)
    usage_retention_days: int = Field(ge=1)
    completed_checkpoint_retention_days: int = Field(ge=1)
    technical_projection_retention_days: int = Field(ge=1)
    log_retention_days: int = Field(ge=1)
    backup_retention_days: int = Field(ge=1)
    retain_raw_prompt: bool
    retain_raw_response: bool
    legal_hold_active: bool
    legal_hold_reason: StrictStr | None = None
    created_at: datetime
    updated_at: datetime


class DataExportSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scope: Literal["user_data"] = "user_data"


class DataExportView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    scope: Literal["user_data"]
    idempotency_key: StrictStr
    status: Literal["queued", "running", "succeeded", "failed"]
    attempt: int = Field(ge=0)
    lease_expires_at: datetime | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    expired_at: datetime | None = None
    manifest_version: int | None = Field(default=None, ge=1)
    manifest_hash: StrictStr | None = Field(default=None, min_length=64, max_length=64)
    last_error: StrictStr | None = None
    created_at: datetime
    updated_at: datetime


class DataExportManifestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    manifest_version: int | None = Field(default=None, ge=1)
    manifest_hash: StrictStr | None = Field(default=None, min_length=64, max_length=64)
    manifest: dict[str, Any] | None = None


class DataExportBundleView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    manifest_version: int | None = Field(default=None, ge=1)
    manifest_hash: StrictStr | None = Field(default=None, min_length=64, max_length=64)
    bundle: dict[str, Any] | None = None


class DataDeletionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    scope: Literal["user_data"] = "user_data"
    confirmation: Literal[DATA_LIFECYCLE_DELETE_CONFIRMATION]


class DataDeletionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    system: Literal[
        "product_db",
        "checkpoint",
        "store",
        "object_storage",
        "search",
        "langsmith",
        "langfuse",
        "logs",
        "backups",
    ]
    phase: Literal["delete", "survivor_scan", "retention_queue"]
    attempt: int = Field(ge=1)
    outcome: Literal[
        "succeeded",
        "not_applicable",
        "pending_external",
        "pending_expiry",
        "failed",
    ]
    affected_count: int = Field(ge=0)
    survivor_count: int = Field(ge=0)
    observed_at: datetime
    reference: dict[str, Any] | None = None
    evidence: dict[str, Any]
    receipt_hash: StrictStr = Field(min_length=64, max_length=64)


class DataDeletionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    scope: Literal["user_data"]
    idempotency_key: StrictStr
    status: Literal[
        "queued",
        "running",
        "pending_external",
        "succeeded",
        "blocked_legal_hold",
        "failed",
    ]
    attempt: int = Field(ge=0)
    lease_expires_at: datetime | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    expired_at: datetime | None = None
    legal_hold_active: bool
    legal_hold_reason: StrictStr | None = None
    system_status: dict[str, StrictStr]
    external_deletion_reference: dict[str, Any]
    receipts: list[DataDeletionReceiptView] = Field(default_factory=list)
    last_error: StrictStr | None = None
    created_at: datetime
    updated_at: datetime


class MemoryCreateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    scope: Literal["session", "workspace"]
    session_id: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    purpose: Literal[
        "session_clarification",
        "profile",
        "strategy_config",
        "process_lesson",
        "event",
        "badcase",
    ]
    key: StrictStr = Field(min_length=1, max_length=128)
    content: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    expires_at: datetime | None = None
    refreshed_at: datetime | None = None
    source_artifact_id: UUID | None = None

    @model_validator(mode="after")
    def require_scope_and_event_fields(self) -> "MemoryCreateSubmission":
        if self.scope == "session" and not self.session_id:
            raise ValueError("session memory requires session_id")
        if self.scope == "workspace" and self.session_id is not None:
            raise ValueError("workspace memory cannot have session_id")
        if self.purpose == "event" and self.refreshed_at is None:
            raise ValueError("event memory requires refreshed_at")
        return self


class MemoryUpdateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    content: dict[str, Any] | None = None
    enabled: bool | None = None
    expires_at: datetime | None = None
    refreshed_at: datetime | None = None


class MemoryDeleteSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    confirmation: Literal["DELETE_MEMORY"]


class MemoryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    session_id: StrictStr | None = None
    scope: Literal["session", "workspace"]
    purpose: Literal[
        "session_clarification",
        "profile",
        "strategy_config",
        "process_lesson",
        "event",
        "badcase",
    ]
    key: StrictStr
    content: dict[str, Any]
    enabled: bool
    expires_at: datetime | None = None
    refreshed_at: datetime | None = None
    source_artifact_id: UUID | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MemoryListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryView]
    limit: int = Field(ge=1, le=100)


class MemoryDeleteView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    requested_at: datetime
    completed_at: datetime | None = None


class OutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    artifact_version_id: UUID
    task_id: UUID
    run_id: UUID
    action: Action
    baseline: Literal["decision", "hold", "no_trade"]
    status: Literal["scheduled", "pending", "matured", "insufficient", "failed"]
    predicted_probability: float | None = Field(default=None, ge=0, le=1)
    realized_label: float | None = Field(default=None, ge=0, le=1)
    horizon: StrictStr
    source: Literal["exchange_native"]
    maturation_at: datetime
    observed_at: datetime | None = None
    metrics: dict[str, Any] | None = None
    source_hash: StrictStr | None = None
    created_at: datetime
    updated_at: datetime


class OutcomeListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OutcomeView]
    limit: int = Field(ge=1, le=100)
    reportable: bool
    sample_count: int = Field(ge=0)
    window_start: datetime | None = None


class ForkSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_run_id: UUID
    checkpoint_id: StrictStr | None = Field(default=None, min_length=1, max_length=255)


class AuthContextSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_id: UUID


class AuthContextView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_id: UUID
    tenant_id: StrictStr = Field(min_length=1, max_length=255)
    tenant_name: StrictStr = Field(min_length=1, max_length=255)
    workspace_id: StrictStr = Field(min_length=1, max_length=255)
    workspace_name: StrictStr = Field(min_length=1, max_length=255)
    role: StrictStr = Field(min_length=1, max_length=64)
    permissions: list[StrictStr]
    version: StrictStr = Field(min_length=1, max_length=64)


class AuthContextListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuthContextView]


class ProductErrorView(BaseModel):
    code: str
    message: str
    correlation_id: StrictStr = Field(min_length=1, max_length=255)
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
    endpoint: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    fallback_from: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    primary_attempt: int | None = Field(default=None, ge=1, le=100)


class AgentStreamBindingView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    protocol: Literal["langgraph-v2"]
    assistant_id: StrictStr = Field(min_length=1, max_length=255)
    thread_id: StrictStr = Field(min_length=1, max_length=255)
    run_id: StrictStr = Field(min_length=1, max_length=255)


class TaskStageView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    stage: Literal[
        "market_snapshot",
        "web_evidence",
        "analysis",
        "evidence_verdict",
        "risk_verdict",
        "artifact",
        "notification",
        "run",
    ]
    status: Literal[
        "committed",
        "planned",
        "succeeded",
        "blocked",
        "failed",
        "cancelled",
    ]
    recorded_at: datetime
    source: Literal["official_stream", "product_projection"]


class TaskStageHistoryView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    run_id: UUID
    stages: list[TaskStageView] = Field(default_factory=list)
    product_event_cursor: int | None = Field(default=None, ge=1)
    official_stream_cursor: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    official_stream_cursor_at: datetime | None = None

    @model_validator(mode="after")
    def require_coherent_cursors(self) -> "TaskStageHistoryView":
        sequences = [stage.sequence for stage in self.stages]
        if sequences != sorted(set(sequences)):
            raise ValueError("stage history sequences must be unique and ascending")
        expected_product_cursor = sequences[-1] if sequences else None
        if self.product_event_cursor != expected_product_cursor:
            raise ValueError(
                "product event cursor must identify the last projected stage"
            )
        if (self.official_stream_cursor is None) != (
            self.official_stream_cursor_at is None
        ):
            raise ValueError("official stream cursor and timestamp must be paired")
        return self


class PublicReviewResponse(BaseModel):
    """Response projection that omits optional fields absent from the decision."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: ReviewAction
    edits: ArtifactEdit | DeepResearchReportEdit | None = None
    comment: StrictStr | None = Field(default=None, min_length=1, max_length=1000)

    @model_serializer(mode="plain")
    def serialize_public_response(self) -> dict[str, object]:
        payload: dict[str, object] = {"action": self.action}
        if self.edits is not None:
            payload["edits"] = self.edits.model_dump(
                mode="json",
                exclude_none=True,
            )
        if self.comment is not None:
            payload["comment"] = self.comment
        return payload


class PendingInterruptMemberView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    interrupt_id: StrictStr = Field(min_length=1, max_length=255)
    response_version: int = Field(ge=1)
    status: Literal["pending", "responding"]
    payload: ReviewInterruptPayload
    response: PublicReviewResponse | None = None
    responded_at: datetime | None = None

    @model_validator(mode="after")
    def require_coherent_response_state(self) -> "PendingInterruptMemberView":
        if self.status == "pending" and (
            self.response is not None or self.responded_at is not None
        ):
            raise ValueError("pending interrupt cannot contain an accepted response")
        if self.status == "responding" and (
            self.response is None or self.responded_at is None
        ):
            raise ValueError("responding interrupt requires its accepted response")
        return self


class PendingInterruptPauseView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pause_id: UUID
    pause_version: int = Field(ge=1)
    status: Literal["pending", "responding"]
    expires_at: datetime | None = None
    members: list[PendingInterruptMemberView] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_atomic_member_state(self) -> "PendingInterruptPauseView":
        if any(member.status != self.status for member in self.members):
            raise ValueError("interrupt pause members must share the aggregate status")
        interrupt_ids = [member.interrupt_id for member in self.members]
        if len(interrupt_ids) != len(set(interrupt_ids)):
            raise ValueError("interrupt pause members must be unique")
        return self


InboxQueryStatus = Literal[
    "active",
    "pending",
    "responding",
    "resolved",
    "expired",
    "resume_failed",
    "all",
]


class InboxItemView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: StrictStr = Field(min_length=1, max_length=255)
    pause_id: UUID
    pause_version: int = Field(ge=1)
    status: Literal[
        "pending",
        "responding",
        "resolved",
        "expired",
        "resume_failed",
        "cancelled",
    ]
    member_count: int = Field(ge=1, le=64)
    payload: ReviewInterruptPayload
    expires_at: datetime | None = None
    responded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    symbol: Symbol
    horizon: StrictStr = Field(min_length=1, max_length=32)
    query_text: StrictStr | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def require_coherent_response_state(self) -> "InboxItemView":
        if self.status == "pending" and self.responded_at is not None:
            raise ValueError("pending inbox item cannot have a response timestamp")
        if self.status in {"responding", "resolved", "resume_failed"} and (
            self.responded_at is None
        ):
            raise ValueError(f"{self.status} inbox item requires a response timestamp")
        if self.status == "expired" and self.expires_at is None:
            raise ValueError("expired inbox item requires an expiry timestamp")
        if isinstance(self.payload, ArtifactReviewPayload):
            payload_symbol = self.payload.artifact.analysis.instrument
            payload_horizon = self.payload.artifact.analysis.horizon
        elif isinstance(self.payload, DeepResearchReviewPayload):
            payload_symbol = self.payload.symbol
            payload_horizon = self.payload.horizon
        else:
            raise ValueError("unsupported inbox review payload")
        if payload_symbol != self.symbol:
            raise ValueError("inbox review symbol must match its task symbol")
        if payload_horizon != self.horizon:
            raise ValueError("inbox review horizon must match its task horizon")
        return self


class InboxView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[InboxItemView]
    next_cursor: StrictStr | None = None


class InboxReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pause_version: int = Field(ge=1)
    response: ReviewResponse


class InboxReviewReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: StrictStr = Field(min_length=1, max_length=255)
    pause_id: UUID
    pause_version: int = Field(ge=1)
    status: Literal[
        "responding",
        "resolved",
        "expired",
        "resume_failed",
        "cancelled",
    ]
    responded_at: datetime


class InterruptResponseSubmission(ReviewResponse):
    response_version: int = Field(ge=1)


class InterruptResponseItemSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    interrupt_id: StrictStr = Field(min_length=1, max_length=255)
    response_version: int = Field(ge=1)
    response: ReviewResponse


class InterruptResponsesSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pause_id: UUID
    pause_version: int = Field(ge=1)
    responses: list[InterruptResponseItemSubmission] = Field(
        min_length=1,
        max_length=64,
    )

    @model_validator(mode="after")
    def require_unique_interrupts(self) -> "InterruptResponsesSubmission":
        interrupt_ids = [item.interrupt_id for item in self.responses]
        if len(interrupt_ids) != len(set(interrupt_ids)):
            raise ValueError("interrupt responses must contain unique interrupt IDs")
        return self


class TaskCompletionScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: Literal["pending", "complete", "blocked", "failed", "cancelled"]
    notification: Literal[
        "not_requested",
        "not_started",
        "pending",
        "retrying",
        "complete",
        "failed",
        "unknown",
    ]
    observability: Literal[
        "not_enabled",
        "pending",
        "degraded",
        "complete",
    ] = "not_enabled"


class TaskProjectionScopeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["latest", "selected_run"] = "latest"
    selected_run_id: UUID | None = None

    @model_validator(mode="after")
    def require_selected_run_identity(self) -> "TaskProjectionScopeView":
        if self.mode == "latest" and self.selected_run_id is not None:
            raise ValueError("latest Task projection cannot select a Run")
        if self.mode == "selected_run" and self.selected_run_id is None:
            raise ValueError("selected Run Task projection requires its Run ID")
        return self


class TaskView(BaseModel):
    task_id: str
    task_type: Literal["market_analysis", "deep_research"] = "market_analysis"
    correlation_id: StrictStr = Field(min_length=1, max_length=255)
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
    query_text: StrictStr | None = Field(default=None, min_length=1, max_length=4000)
    created_at: datetime
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    market_snapshot: MarketSnapshot | None = None
    web_evidence: list[WebEvidence] = Field(default_factory=list)
    artifact: Artifact | None = None
    deep_research_artifact: DeepResearchArtifact | None = None
    errors: list[ProductErrorView] = Field(default_factory=list)
    completion_scope: TaskCompletionScope
    warnings: list[StrictStr] = Field(default_factory=list)
    agent_stream: AgentStreamBindingView | None = None
    stage_history: TaskStageHistoryView | None = None
    pending_interrupts: PendingInterruptPauseView | None = None
    projection_scope: TaskProjectionScopeView = Field(
        default_factory=TaskProjectionScopeView
    )

    @model_validator(mode="before")
    @classmethod
    def enforce_server_owned_correlation(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        projected = dict(value)
        correlation_id = correlation_id_for_task(str(projected.get("task_id", "")))
        projected["correlation_id"] = correlation_id
        status = projected.get("status")
        projected.setdefault(
            "completion_scope",
            {
                "analysis": {
                    "succeeded": "complete",
                    "blocked": "blocked",
                    "failed": "failed",
                    "cancelled": "cancelled",
                }.get(status, "pending"),
                "notification": "not_requested",
                "observability": "not_enabled",
            },
        )
        projected.setdefault("warnings", [])
        errors = projected.get("errors")
        if isinstance(errors, list):
            projected["errors"] = [
                {**error, "correlation_id": correlation_id}
                if isinstance(error, Mapping)
                else error
                for error in errors
            ]
        return projected

    @model_validator(mode="after")
    def require_coherent_operational_state(self) -> "TaskView":
        if (
            self.task_type == "market_analysis"
            and self.deep_research_artifact is not None
        ):
            raise ValueError("market analysis Task cannot expose a research artifact")
        if self.task_type == "deep_research" and self.artifact is not None:
            raise ValueError("deep research Task cannot expose an analysis artifact")
        if (
            self.status == "waiting_human"
            and self.pending_interrupts is None
            and self.projection_scope.mode != "selected_run"
        ):
            raise ValueError("current waiting_human Task requires an active pause")
        if self.status != "waiting_human" and self.pending_interrupts is not None:
            raise ValueError("only waiting_human Task may expose an active pause")
        if (
            self.projection_scope.selected_run_id is not None
            and self.stage_history is not None
            and self.stage_history.run_id != self.projection_scope.selected_run_id
        ):
            raise ValueError("Task stage history must match its selected Run")
        return self


class DecisionAdmissionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: DecisionRequest
    route: DecisionRoute
    task: TaskView | None = None


class RunSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    task_type: Literal["market_analysis", "deep_research"] = "market_analysis"
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
    main_action: (
        Literal[
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
        | None
    ) = None


class RunListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RunSummaryView]
    limit: int = Field(ge=1, le=100)


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rating: Literal["positive", "negative"]
    comment: StrictStr | None = Field(default=None, max_length=2000)


class FeedbackView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: UUID
    task_id: UUID
    run_id: UUID
    artifact_version_id: UUID | None = None
    rating: Literal["positive", "negative"]
    comment: StrictStr | None = None
    created_at: datetime
    updated_at: datetime


class PostmortemSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Literal["operator_postmortem", "evaluation_badcase"] = (
        "operator_postmortem"
    )
    title: StrictStr = Field(min_length=1, max_length=255)
    summary: StrictStr = Field(min_length=1, max_length=4000)
    root_cause: StrictStr | None = Field(default=None, max_length=4000)
    expected_behavior: StrictStr | None = Field(default=None, max_length=4000)
    actual_behavior: StrictStr | None = Field(default=None, max_length=4000)


class FrozenReplayView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    postmortem_id: UUID
    task_id: UUID
    run_id: UUID
    artifact_version_id: UUID | None = None
    schema_version: Literal["frozen-replay-v1"]
    source_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    allow_live_fetch: Literal[False]
    allow_live_side_effects: Literal[False]
    rule_metrics: dict[str, Any]
    created_at: datetime


class PostmortemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    feedback_id: UUID | None = None
    task_id: UUID
    run_id: UUID
    artifact_version_id: UUID | None = None
    category: Literal[
        "negative_feedback", "operator_postmortem", "evaluation_badcase"
    ]
    status: Literal["open", "frozen", "closed"]
    title: StrictStr
    summary: StrictStr
    root_cause: StrictStr | None = None
    expected_behavior: StrictStr | None = None
    actual_behavior: StrictStr | None = None
    source_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_replay: FrozenReplayView | None = None
    created_at: datetime
    updated_at: datetime


class PostmortemListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PostmortemView]
    limit: int = Field(ge=1, le=100)


class ImprovementDatasetSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: StrictStr = Field(min_length=1, max_length=255)
    replay_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("replay_ids")
    @classmethod
    def require_unique_replays(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("replay_ids must be unique")
        return value


class ImprovementDatasetView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: StrictStr
    status: Literal["draft", "frozen"]
    replay_count: int = Field(ge=1)
    case_names: list[StrictStr] = Field(min_length=1)
    source_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ImprovementDatasetListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ImprovementDatasetView]
    limit: int = Field(ge=1, le=100)


class ImprovementCandidateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: StrictStr = Field(min_length=1, max_length=255)
    base_version: StrictStr = Field(min_length=1, max_length=255)
    candidate_version: StrictStr = Field(min_length=1, max_length=255)
    rollback_target_version: StrictStr = Field(min_length=1, max_length=255)
    rationale: StrictStr = Field(min_length=1, max_length=4000)
    diff: dict[str, Any]


class ImprovementExperimentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dataset_id: UUID
    prompt_version: StrictStr = Field(min_length=1, max_length=255)
    git_revision: StrictStr = Field(min_length=1, max_length=255)


class ImprovementExperimentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    dataset_id: UUID
    candidate_id: UUID
    status: Literal["succeeded", "failed"]
    prompt_version: StrictStr
    git_revision: StrictStr
    case_results: list[dict[str, Any]]
    metrics: dict[str, Any]
    gate_report: dict[str, Any]
    source_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    completed_at: datetime
    created_at: datetime


class ImprovementReviewDecisionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["approve", "reject"]
    comment: StrictStr | None = Field(default=None, min_length=1, max_length=1000)


class ImprovementReviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    candidate_id: UUID
    status: Literal["pending", "approved", "rejected"]
    official_assistant_id: StrictStr | None = None
    official_thread_id: StrictStr | None = None
    official_run_id: StrictStr | None = None
    official_interrupt_id: StrictStr | None = None
    interrupt_payload: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ImprovementShadowSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_runs: int = Field(default=1, ge=1, le=100)


class ImprovementShadowView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    candidate_id: UUID
    baseline_version: StrictStr
    status: Literal["running", "passed", "failed"]
    minimum_runs: int = Field(ge=1)
    observed_runs: int = Field(ge=0)
    comparison: dict[str, Any]
    source_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ImprovementReleaseSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: StrictStr = Field(min_length=1, max_length=4000)


class ImprovementReleaseEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    candidate_id: UUID
    action: Literal["promoted", "rolled_back"]
    from_version: StrictStr
    to_version: StrictStr
    rollback_target_version: StrictStr
    reason: StrictStr
    evidence: dict[str, Any]
    source_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime


class ImprovementCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: StrictStr
    base_version: StrictStr
    candidate_version: StrictStr
    rollback_target_version: StrictStr
    rationale: StrictStr
    diff: dict[str, Any]
    version_hash: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal[
        "draft",
        "evaluated",
        "pending_review",
        "approved",
        "rejected",
        "shadow",
        "active",
        "rolled_back",
    ]
    latest_experiment: ImprovementExperimentView | None = None
    latest_review: ImprovementReviewView | None = None
    latest_shadow: ImprovementShadowView | None = None
    release_events: list[ImprovementReleaseEventView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ImprovementCandidateListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ImprovementCandidateView]
    limit: int = Field(ge=1, le=100)


class RunDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: RunSummaryView
    task: TaskView
    run_projection: TaskView
    is_current_run: bool
    feedback: FeedbackView | None = None

    @model_validator(mode="after")
    def require_current_and_historical_projection_scopes(self) -> "RunDetailView":
        if self.task.projection_scope.mode != "latest":
            raise ValueError("Run detail Task must be the current projection")
        if self.run_projection.projection_scope.mode != "selected_run":
            raise ValueError("Run detail history must be a selected Run projection")
        if self.run_projection.projection_scope.selected_run_id != UUID(
            self.run.run_id
        ):
            raise ValueError("Run detail projection must match its selected Run")
        if self.task.task_id != self.run.task_id:
            raise ValueError("Run detail current Task must match its Run")
        if self.run_projection.task_id != self.run.task_id:
            raise ValueError("Run detail historical Task must match its Run")
        return self


class ArtifactLibraryItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    artifact_version_id: UUID
    artifact_type: StrictStr = Field(min_length=1, max_length=64)
    schema_version: StrictStr = Field(min_length=1, max_length=32)
    version_number: int = Field(ge=1)
    status: Literal["draft", "streaming", "committed", "failed"]
    task_id: UUID
    run_id: UUID
    symbol: Symbol
    horizon: StrictStr = Field(min_length=1, max_length=32)
    main_action: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    created_at: datetime


class ArtifactLibraryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ArtifactLibraryItemView]
    limit: int = Field(ge=1, le=100)


class WatchlistItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    latest_snapshot: MarketSnapshot | None = None
    created_at: datetime


class HomeActiveTaskView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    run_id: UUID | None = None
    status: Literal["queued", "running", "waiting_human"]
    symbol: Symbol
    horizon: StrictStr = Field(min_length=1, max_length=32)
    created_at: datetime


class HomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlist: list[WatchlistItemView]
    active_tasks: list[HomeActiveTaskView]
    pending_inbox_count: int = Field(ge=0)
    recent_reports: list[ArtifactLibraryItemView]


class ArtifactVersionSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_version_id: UUID
    artifact_id: UUID
    version_number: int = Field(ge=1)
    schema_version: StrictStr = Field(min_length=1, max_length=32)
    status: Literal["draft", "streaming", "committed", "failed"]
    task_id: UUID
    run_id: UUID
    created_at: datetime


class ArtifactDecisionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID
    decision_version: int = Field(ge=1)
    decision: dict[str, Any]
    evidence_verdict: EvidenceVerdict
    risk_verdict: RiskVerdict
    created_at: datetime


class ArtifactVersionDetailView(ArtifactVersionSummaryView):
    content: Artifact | DeepResearchArtifact
    decision: ArtifactDecisionView | None = None
    market_snapshots: list[MarketSnapshot] = Field(default_factory=list)
    web_evidence: list[WebEvidence] = Field(default_factory=list)


class ArtifactDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    artifact_type: StrictStr = Field(min_length=1, max_length=64)
    task_id: UUID
    symbol: Symbol
    horizon: StrictStr = Field(min_length=1, max_length=32)
    latest_version_number: int = Field(ge=0)
    versions: list[ArtifactVersionSummaryView]
    selected_version: ArtifactVersionDetailView | None = None


class NotificationAttemptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: UUID
    attempt_number: int = Field(ge=1, le=5)
    trigger: Literal["automatic", "manual"]
    result: Literal[
        "leased",
        "sending",
        "delivered",
        "failed_retryable",
        "failed_terminal",
        "unknown",
        "released",
    ]
    reason: StrictStr | None = None
    delay_seconds: int = Field(ge=0)
    retry_after_seconds: int | None = Field(default=None, ge=0)
    cost_units: StrictStr
    provider_receipt: StrictStr | None = None
    error_code: StrictStr | None = None
    created_at: datetime
    finished_at: datetime | None = None


class NotificationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: UUID
    task_id: UUID
    run_id: UUID
    artifact_id: UUID
    artifact_version_id: UUID
    decision_id: UUID
    decision_version: int = Field(ge=1)
    channel: StrictStr
    type: StrictStr
    status: Literal[
        "planned",
        "leased",
        "sending",
        "delivered",
        "failed_retryable",
        "failed_terminal",
        "unknown",
    ]
    attempt_count: int = Field(ge=0, le=5)
    manual_resend_pending: bool
    manual_resend_available: bool
    manual_resend_requested_at: datetime | None = None
    available_at: datetime
    delivered_at: datetime | None = None
    terminal_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    attempts: list[NotificationAttemptView]


class NotificationListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    items: list[NotificationView]


class NotificationResendSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: StrictStr = Field(min_length=4, max_length=500)


class NotificationSettingsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["bark"] = "bark"
    enabled: bool
    configured: bool
    updated_at: datetime | None = None


class NotificationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool
    device_key: SecretStr | None = Field(default=None, min_length=8, max_length=255)


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = "2.0.0"


class GraphExecutionError(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    code: StrictStr = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    retryable: bool = False
    provider: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    error_type: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    attempt: int | None = Field(default=None, ge=1, le=100)
    endpoint: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    fallback_from: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    primary_attempt: int | None = Field(default=None, ge=1, le=100)
    correlation_id: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    field: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    expected: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    actual: StrictStr | None = Field(default=None, min_length=1, max_length=128)


class TerminalGraphOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    terminal_status: Literal["succeeded", "blocked", "failed", "cancelled"]
    market_snapshot: MarketSnapshot | None = None
    web_evidence: list[WebEvidence] = Field(default_factory=list)
    artifact: Artifact | None = None
    deep_research_artifact: DeepResearchArtifact | None = None
    errors: list[GraphExecutionError] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_terminal_contract(self) -> "TerminalGraphOutput":
        if self.terminal_status == "succeeded":
            committed_outputs = int(
                self.artifact is not None and self.artifact.status == "committed"
            ) + int(
                self.deep_research_artifact is not None
                and self.deep_research_artifact.status == "committed"
            )
            if committed_outputs != 1:
                raise ValueError(
                    "succeeded output requires exactly one committed artifact"
                )
        elif self.terminal_status == "blocked":
            draft_outputs = int(
                self.artifact is not None and self.artifact.status == "draft"
            ) + int(
                self.deep_research_artifact is not None
                and self.deep_research_artifact.status == "draft"
            )
            if draft_outputs != 1:
                raise ValueError(
                    "blocked output requires exactly one reviewable draft artifact"
                )
            if self.artifact is not None and self.artifact.risk_verdict.allowed:
                raise ValueError(
                    "blocked output cannot contain an allowed risk verdict"
                )
        elif self.terminal_status == "failed":
            if self.artifact is not None or self.deep_research_artifact is not None:
                raise ValueError("failed output cannot contain an artifact")
            if not self.errors:
                raise ValueError("failed output requires an error")
        return self


TaskPayload = dict[str, Any]
ProductSubmission = AnalysisSubmission | DeepResearchSubmission
