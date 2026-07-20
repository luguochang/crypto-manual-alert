from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import ValidationError
import pytest

from crypto_alert_v2.api.app import UnavailableProductService, create_app
from crypto_alert_v2.api.schemas import ProductErrorView, TerminalGraphOutput
from crypto_alert_v2.api.request_identity import correlation_id_for_task
from crypto_alert_v2.api.service import (
    IdempotencyConflictError,
    InvalidInboxCursorError,
    InterruptResponseConflictError,
    MonitorConditionEvaluatorUnavailableError,
    NotificationSettingsConflictError,
    NotificationSettingsUnavailableError,
    ProductAnalysisService,
    _completion_projection,
    _public_error,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import Settings
from crypto_alert_v2.domain.models import (
    Artifact,
    EvidenceVerdict,
    MarketAnalysis,
    RiskVerdict,
)
from crypto_alert_v2.graph.request import ArtifactReviewPayload
from tests.fixtures.golden_cases import valid_market_analysis


PAUSE_ID = "33333333-3333-4333-8333-333333333333"
AUTH_CONTEXT_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.parametrize(
    ("statuses", "expected", "warning"),
    [
        ((), "not_enabled", None),
        (("not_requested", "not_requested"), "not_enabled", None),
        (("planned", "not_requested"), "pending", "observability_delivery_pending"),
        (("verified", "not_requested"), "complete", None),
        (("verified", "failed_terminal"), "degraded", "observability_delivery_failed"),
        (("unknown", "verified"), "degraded", "observability_delivery_failed"),
    ],
)
def test_completion_projection_uses_durable_observability_statuses(
    statuses: tuple[str, ...],
    expected: str,
    warning: str | None,
) -> None:
    scope, warnings = _completion_projection(
        status="succeeded",
        notification_requested=False,
        notification_status=None,
        observability_statuses=statuses,
    )

    assert scope["observability"] == expected
    if warning is None:
        assert not any(item.startswith("observability_") for item in warnings)
    else:
        assert warning in warnings


def _review_payload() -> dict[str, Any]:
    artifact = Artifact(
        content_version=1,
        status="draft",
        analysis=MarketAnalysis.model_validate(valid_market_analysis()),
        evidence_verdict=EvidenceVerdict(sufficient=True),
        risk_verdict=RiskVerdict(allowed=True),
        source_references=["https://example.com/review-source"],
    )
    return ArtifactReviewPayload(
        review_iteration=1,
        artifact=artifact,
    ).model_dump(mode="json")


class FakeProductService:
    def __init__(self) -> None:
        self.actor: ActorContext | None = None
        self.submission: Any = None
        self.idempotency_key: str | None = None
        self.selected_run_id: UUID | None = None
        self.feedback_run_id: str | None = None
        self.feedback_submission: Any = None
        self.cancelled_task_id: str | None = None
        self.cancelled_run_id: str | None = None
        self.cancel_idempotency_key: str | None = None
        self.retried_task_id: str | None = None
        self.retry_idempotency_key: str | None = None
        self.forked_task_id: str | None = None
        self.fork_submission: Any = None
        self.fork_idempotency_key: str | None = None
        self.responded_task_id: str | None = None
        self.responded_interrupt_id: str | None = None
        self.interrupt_submission: Any = None
        self.interrupt_idempotency_key: str | None = None
        self.inbox_review_pause_id: UUID | None = None
        self.inbox_review_submission: Any = None
        self.inbox_review_idempotency_key: str | None = None
        self.inbox_status: str | None = None
        self.inbox_limit: int | None = None
        self.inbox_cursor: str | None = None
        self.notification_task_id: str | None = None
        self.notification_id: str | None = None
        self.notification_resend_reason: str | None = None
        self.notification_settings_submission: Any = None
        self.watchlist_symbol: tuple[str, bool] | None = None
        self.dispatch_calls = 0

    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self.actor = actor
        self.submission = submission
        self.idempotency_key = idempotency_key
        return {
            "task_id": "task-1",
            "status": "queued",
            "symbol": submission.symbol,
            "horizon": submission.horizon,
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "artifact": None,
            "errors": [],
        }

    async def create_deep_research(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self.actor = actor
        self.submission = submission
        self.idempotency_key = idempotency_key
        return {
            "task_id": "task-research-1",
            "task_type": "deep_research",
            "status": "queued",
            "symbol": submission.symbol,
            "horizon": submission.horizon,
            "query_text": submission.query_text,
            "created_at": datetime(2026, 7, 19, tzinfo=UTC),
            "artifact": None,
            "deep_research_artifact": None,
            "errors": [],
        }

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.selected_run_id = run_id
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "failed",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "artifact": None,
            "errors": [
                {
                    "code": "provider_unavailable",
                    "message": "Market data provider is unavailable.",
                    "retryable": True,
                }
            ],
        }

    async def list_runs(self, actor: ActorContext, *, limit: int) -> dict[str, Any]:
        self.actor = actor
        return {
            "items": [
                {
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "task_id": "22222222-2222-4222-8222-222222222222",
                    "task_type": "market_analysis",
                    "attempt": 1,
                    "status": "succeeded",
                    "symbol": "BTC-USDT-SWAP",
                    "horizon": "4h",
                    "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                    "finished_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                    "main_action": "no_trade",
                }
            ],
            "limit": limit,
        }

    async def get_run(
        self,
        actor: ActorContext,
        run_id: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        if run_id != "11111111-1111-4111-8111-111111111111":
            return None
        return {
            "run": {
                "run_id": run_id,
                "task_id": "22222222-2222-4222-8222-222222222222",
                "attempt": 1,
                "status": "succeeded",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                "finished_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                "main_action": "no_trade",
            },
            "task": {
                "task_id": "22222222-2222-4222-8222-222222222222",
                "status": "succeeded",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                "artifact": None,
                "errors": [],
                "projection_scope": {
                    "mode": "latest",
                    "selected_run_id": None,
                },
            },
            "run_projection": {
                "task_id": "22222222-2222-4222-8222-222222222222",
                "status": "succeeded",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                "artifact": None,
                "errors": [],
                "projection_scope": {
                    "mode": "selected_run",
                    "selected_run_id": run_id,
                },
            },
            "is_current_run": True,
        }

    async def submit_feedback(
        self,
        actor: ActorContext,
        run_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.feedback_run_id = run_id
        self.feedback_submission = submission
        self.idempotency_key = idempotency_key
        if run_id != "11111111-1111-4111-8111-111111111111":
            return None
        return {
            "feedback_id": "77777777-7777-4777-8777-777777777777",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "run_id": run_id,
            "artifact_version_id": "55555555-5555-4555-8555-555555555555",
            "rating": submission.rating,
            "comment": submission.comment,
            "created_at": datetime(2026, 7, 13, 0, 6, tzinfo=UTC),
            "updated_at": datetime(2026, 7, 13, 0, 6, tzinfo=UTC),
        }

    async def list_artifacts(
        self, actor: ActorContext, *, limit: int
    ) -> dict[str, Any]:
        self.actor = actor
        return {
            "items": [
                {
                    "artifact_id": "44444444-4444-4444-8444-444444444444",
                    "artifact_version_id": "55555555-5555-4555-8555-555555555555",
                    "artifact_type": "analysis_report",
                    "schema_version": "1.0",
                    "version_number": 1,
                    "status": "committed",
                    "task_id": "22222222-2222-4222-8222-222222222222",
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "symbol": "BTC-USDT-SWAP",
                    "horizon": "4h",
                    "main_action": "no_trade",
                    "created_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                }
            ],
            "limit": limit,
        }

    async def get_home(self, actor: ActorContext) -> dict[str, Any]:
        self.actor = actor
        return {
            "watchlist": [
                {
                    "symbol": "BTC-USDT-SWAP",
                    "latest_snapshot": None,
                    "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                }
            ],
            "active_tasks": [],
            "pending_inbox_count": 0,
            "recent_reports": [],
        }

    async def set_watchlist_symbol(
        self,
        actor: ActorContext,
        symbol: str,
        *,
        included: bool,
    ) -> dict[str, Any]:
        self.actor = actor
        self.watchlist_symbol = (symbol, included)
        return await self.get_home(actor)

    async def get_artifact(
        self,
        actor: ActorContext,
        artifact_id: str,
        *,
        version_number: int | None = None,
    ) -> dict[str, Any] | None:
        self.actor = actor
        if artifact_id != "44444444-4444-4444-8444-444444444444":
            return None
        version = version_number or 1
        if version != 1:
            return None
        artifact = Artifact(
            content_version=1,
            status="committed",
            analysis=MarketAnalysis.model_validate(valid_market_analysis()),
            evidence_verdict=EvidenceVerdict(sufficient=True),
            risk_verdict=RiskVerdict(allowed=True),
            source_references=["https://example.com/report"],
        )
        return {
            "artifact_id": artifact_id,
            "artifact_type": "analysis_report",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "latest_version_number": 1,
            "versions": [
                {
                    "artifact_version_id": "55555555-5555-4555-8555-555555555555",
                    "artifact_id": artifact_id,
                    "version_number": 1,
                    "schema_version": "1.0",
                    "status": "committed",
                    "task_id": "22222222-2222-4222-8222-222222222222",
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "created_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                }
            ],
            "selected_version": {
                "artifact_version_id": "55555555-5555-4555-8555-555555555555",
                "artifact_id": artifact_id,
                "version_number": 1,
                "schema_version": "1.0",
                "status": "committed",
                "task_id": "22222222-2222-4222-8222-222222222222",
                "run_id": "11111111-1111-4111-8111-111111111111",
                "created_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                "content": artifact.model_dump(mode="json"),
                "decision": {
                    "decision_id": "66666666-6666-4666-8666-666666666666",
                    "decision_version": 1,
                    "decision": artifact.analysis.model_dump(mode="json"),
                    "evidence_verdict": artifact.evidence_verdict.model_dump(
                        mode="json"
                    ),
                    "risk_verdict": artifact.risk_verdict.model_dump(mode="json"),
                    "created_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                },
                "market_snapshots": [],
                "web_evidence": [],
            },
        }

    async def list_inbox(
        self,
        actor: ActorContext,
        *,
        status: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        self.actor = actor
        self.inbox_status = status
        self.inbox_limit = limit
        self.inbox_cursor = cursor
        return {
            "items": [
                {
                    "task_id": "22222222-2222-4222-8222-222222222222",
                    "pause_id": PAUSE_ID,
                    "pause_version": 1,
                    "status": "responding",
                    "member_count": 2,
                    "payload": _review_payload(),
                    "expires_at": datetime(2026, 7, 13, 0, 10, tzinfo=UTC),
                    "responded_at": datetime(2026, 7, 13, 0, 2, tzinfo=UTC),
                    "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                    "updated_at": datetime(2026, 7, 13, 0, 2, tzinfo=UTC),
                    "symbol": "BTC-USDT-SWAP",
                    "horizon": "4h",
                    "query_text": "Assess current BTC risk.",
                }
            ],
            "next_cursor": "next-cursor",
        }

    async def list_notifications(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.notification_task_id = task_id
        if task_id != "task-1":
            return None
        return {
            "task_id": "22222222-2222-4222-8222-222222222222",
            "items": [self._notification_view()],
        }

    async def request_notification_resend(
        self,
        actor: ActorContext,
        notification_id: str,
        submission: Any,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.notification_id = notification_id
        self.notification_resend_reason = submission.reason
        if notification_id != "77777777-7777-4777-8777-777777777777":
            return None
        return self._notification_view(manual_resend_pending=True)

    async def get_notification_settings(
        self,
        actor: ActorContext,
    ) -> dict[str, Any]:
        self.actor = actor
        return {
            "channel": "bark",
            "enabled": False,
            "configured": True,
            "updated_at": datetime(2026, 7, 13, 0, 4, tzinfo=UTC),
        }

    async def update_notification_settings(
        self,
        actor: ActorContext,
        submission: Any,
    ) -> dict[str, Any]:
        self.actor = actor
        self.notification_settings_submission = submission
        return {
            "channel": "bark",
            "enabled": submission.enabled,
            "configured": True,
            "updated_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
        }

    @staticmethod
    def _notification_view(
        *,
        manual_resend_pending: bool = False,
    ) -> dict[str, Any]:
        return {
            "notification_id": "77777777-7777-4777-8777-777777777777",
            "task_id": "22222222-2222-4222-8222-222222222222",
            "run_id": "33333333-3333-4333-8333-333333333333",
            "artifact_id": "44444444-4444-4444-8444-444444444444",
            "artifact_version_id": "55555555-5555-4555-8555-555555555555",
            "decision_id": "66666666-6666-4666-8666-666666666666",
            "decision_version": 1,
            "channel": "bark",
            "type": "analysis_completed",
            "status": "unknown",
            "attempt_count": 1,
            "manual_resend_pending": manual_resend_pending,
            "manual_resend_available": not manual_resend_pending,
            "manual_resend_requested_at": (
                datetime(2026, 7, 13, 0, 3, tzinfo=UTC)
                if manual_resend_pending
                else None
            ),
            "available_at": datetime(2026, 7, 13, tzinfo=UTC),
            "delivered_at": None,
            "terminal_at": datetime(2026, 7, 13, 0, 2, tzinfo=UTC),
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "updated_at": datetime(2026, 7, 13, 0, 3, tzinfo=UTC),
            "attempts": [
                {
                    "attempt_id": "88888888-8888-4888-8888-888888888888",
                    "attempt_number": 1,
                    "trigger": "automatic",
                    "result": "unknown",
                    "reason": "delivery_outcome_uncertain",
                    "delay_seconds": 0,
                    "retry_after_seconds": None,
                    "cost_units": "0.000000",
                    "provider_receipt": None,
                    "error_code": "delivery_outcome_uncertain",
                    "created_at": datetime(2026, 7, 13, 0, 1, tzinfo=UTC),
                    "finished_at": datetime(2026, 7, 13, 0, 2, tzinfo=UTC),
                }
            ],
        }

    async def cancel_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.cancelled_task_id = task_id
        self.cancel_idempotency_key = idempotency_key
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "running",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "cancel_requested_at": datetime(2026, 7, 13, 0, 1, tzinfo=UTC),
            "artifact": None,
            "errors": [],
        }

    async def cancel_run(
        self,
        actor: ActorContext,
        run_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.cancelled_run_id = run_id
        self.cancel_idempotency_key = idempotency_key
        if run_id != "11111111-1111-4111-8111-111111111111":
            return None
        return {
            "task_id": "22222222-2222-4222-8222-222222222222",
            "status": "running",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "cancel_requested_at": datetime(2026, 7, 13, 0, 1, tzinfo=UTC),
            "artifact": None,
            "errors": [],
        }

    async def fork_task(
        self,
        actor: ActorContext,
        task_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.forked_task_id = task_id
        self.fork_submission = submission
        self.fork_idempotency_key = idempotency_key
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "queued",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "artifact": None,
            "errors": [],
        }

    async def retry_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.retried_task_id = task_id
        self.retry_idempotency_key = idempotency_key
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "queued",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "artifact": None,
            "errors": [],
        }

    async def respond_interrupt(
        self,
        actor: ActorContext,
        task_id: str,
        interrupt_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.responded_task_id = task_id
        self.responded_interrupt_id = interrupt_id
        self.interrupt_submission = submission
        self.interrupt_idempotency_key = idempotency_key
        if task_id != "task-1" or interrupt_id != "interrupt-1":
            return None
        return {
            "task_id": task_id,
            "status": "waiting_human",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "artifact": None,
            "errors": [],
            "pending_interrupts": {
                "pause_id": PAUSE_ID,
                "pause_version": 1,
                "status": "responding",
                "expires_at": datetime(2026, 7, 13, 0, 10, tzinfo=UTC),
                "members": [
                    {
                        "interrupt_id": interrupt_id,
                        "response_version": submission.response_version,
                        "status": "responding",
                        "payload": _review_payload(),
                        "response": submission.model_dump(
                            mode="json",
                            exclude={"response_version"},
                            exclude_none=True,
                        ),
                        "responded_at": datetime(2026, 7, 13, 0, 1, tzinfo=UTC),
                    }
                ],
            },
        }

    async def respond_interrupts(
        self,
        actor: ActorContext,
        task_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.responded_task_id = task_id
        self.responded_interrupt_id = None
        self.interrupt_submission = submission
        self.interrupt_idempotency_key = idempotency_key
        if task_id != "task-1" or str(submission.pause_id) != PAUSE_ID:
            return None
        responded_at = datetime(2026, 7, 13, 0, 1, tzinfo=UTC)
        return {
            "task_id": task_id,
            "status": "waiting_human",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "artifact": None,
            "errors": [],
            "pending_interrupts": {
                "pause_id": submission.pause_id,
                "pause_version": submission.pause_version,
                "status": "responding",
                "expires_at": datetime(2026, 7, 13, 0, 10, tzinfo=UTC),
                "members": [
                    {
                        "interrupt_id": item.interrupt_id,
                        "response_version": item.response_version,
                        "status": "responding",
                        "payload": _review_payload(),
                        "response": item.response.model_dump(
                            mode="json",
                            exclude_none=True,
                        ),
                        "responded_at": responded_at,
                    }
                    for item in submission.responses
                ],
            },
        }

    async def respond_inbox_review(
        self,
        actor: ActorContext,
        pause_id: UUID,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.inbox_review_pause_id = pause_id
        self.inbox_review_submission = submission
        self.inbox_review_idempotency_key = idempotency_key
        if str(pause_id) != PAUSE_ID:
            return None
        return {
            "task_id": "task-1",
            "pause_id": pause_id,
            "pause_version": submission.pause_version,
            "status": "responding",
            "responded_at": datetime(2026, 7, 13, 0, 1, tzinfo=UTC),
        }

    async def dispatch_task(self, actor: ActorContext, task_id: str) -> None:
        del actor, task_id
        self.dispatch_calls += 1


class AcceptingTokenVerifier:
    def verify_authorization(self, authorization: str | None) -> dict[str, object]:
        assert authorization == "Bearer signed-internal-token"
        return {
            "sub": "oidc|user-1",
            "token_use": "user",
            "identity_issuer": "https://identity.example.com",
            "context_id": str(AUTH_CONTEXT_ID),
        }


class RejectingMissingAuthorizationVerifier:
    def verify_authorization(self, authorization: str | None) -> dict[str, object]:
        if authorization is None:
            raise PermissionError("Authorization header is required")
        raise AssertionError("this verifier only exercises missing Authorization")


class AcceptingMembershipAuthority:
    async def authorize(self, identity: Any, context_id: UUID) -> ActorContext:
        assert identity.issuer == "https://identity.example.com"
        assert identity.subject == "oidc|user-1"
        assert context_id == AUTH_CONTEXT_ID
        return ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="oidc|user-1",
            identity_issuer=identity.issuer,
            context_id=context_id,
            roles=("member",),
            permissions=("analysis:read", "analysis:write"),
        )

    async def discover(self, identity: Any) -> tuple[object, ...]:
        del identity
        return ()

    async def select(self, identity: Any, context_id: UUID) -> tuple[object, object]:
        del identity, context_id
        raise AssertionError("context selection is not exercised by this fixture")


def _production_app(
    service: FakeProductService,
    token_verifier: object,
    *,
    mode: str = "production",
) -> object:
    return create_app(
        service=service,
        mode=mode,
        token_verifier=token_verifier,
        identity_token_verifier=token_verifier,
        membership_authority=AcceptingMembershipAuthority(),
    )


class ConflictingProductService(FakeProductService):
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise IdempotencyConflictError(
            "Idempotency-Key was already used with a different analysis payload."
        )


class UnprovisionedProductService(FakeProductService):
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise PermissionError("actor membership was not found")

    async def respond_interrupt(
        self,
        actor: ActorContext,
        task_id: str,
        interrupt_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, interrupt_id, submission, idempotency_key
        raise PermissionError("actor membership was not found")

    async def respond_interrupts(
        self,
        actor: ActorContext,
        task_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, submission, idempotency_key
        raise PermissionError("actor membership was not found")


class ConflictingInterruptService(FakeProductService):
    def __init__(self, error: RuntimeError) -> None:
        super().__init__()
        self.error = error

    async def respond_interrupt(
        self,
        actor: ActorContext,
        task_id: str,
        interrupt_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, interrupt_id, submission, idempotency_key
        raise self.error

    async def respond_interrupts(
        self,
        actor: ActorContext,
        task_id: str,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, submission, idempotency_key
        raise self.error


class InvalidInboxCursorService(FakeProductService):
    async def list_inbox(
        self,
        actor: ActorContext,
        *,
        status: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        del actor, status, limit, cursor
        raise InvalidInboxCursorError("Invalid inbox cursor.")


class UnavailableMonitorEvaluatorService(FakeProductService):
    async def create_monitor(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del actor, idempotency_key
        raise MonitorConditionEvaluatorUnavailableError(submission.condition.kind)

    async def trigger_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, monitor_id, idempotency_key
        raise MonitorConditionEvaluatorUnavailableError("price")


def _development_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_environment": "development",
        "development_bootstrap_enabled": True,
        "development_bootstrap_profile": "local-proof",
        "development_bootstrap_subject": "compose-user",
        "development_bootstrap_tenant_id": "compose-tenant",
        "development_bootstrap_workspace_id": "compose-workspace",
        "development_bootstrap_roles": ("member",),
        "development_bootstrap_permissions": (
            "analysis:read",
            "analysis:write",
        ),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _development_app(service: FakeProductService) -> object:
    settings = _development_settings()
    return create_app(
        service=service,
        mode=settings.app_environment,
        settings=settings,
    )


def test_public_error_preserves_only_safe_provider_fallback_diagnostics() -> None:
    public_errors = _public_error(
        {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "provider_unavailable",
                    "provider": "builtin_web_search",
                    "error_type": "UnverifiedServerToolCall",
                    "attempt": 3,
                    "retryable": True,
                    "endpoint": "web_search_market",
                    "fallback_from": "okx",
                    "primary_attempt": 2,
                    "correlation_id": "must-not-cross-product-api",
                    "raw_response": "must-not-leak",
                    "authorization": "must-not-leak",
                }
            ],
        },
        correlation_id="task-owned-correlation",
    )

    assert public_errors == [
        {
            "code": "provider_unavailable",
            "message": "无法连接市场数据提供方，当前未生成分析结果。",
            "retryable": True,
            "correlation_id": "task-owned-correlation",
            "provider": "builtin_web_search",
            "error_type": "UnverifiedServerToolCall",
            "attempt": 3,
            "endpoint": "web_search_market",
            "fallback_from": "okx",
            "primary_attempt": 2,
        }
    ]
    ProductErrorView.model_validate(public_errors[0])


def test_public_error_drops_unsafe_or_unbounded_fallback_diagnostics() -> None:
    public_errors = _public_error(
        {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "provider_unavailable",
                    "retryable": True,
                    "endpoint": "https://provider.invalid/raw?authorization=secret",
                    "fallback_from": "okx\nraw-response",
                    "primary_attempt": 101,
                }
            ],
        },
        correlation_id="task-owned-correlation",
    )

    assert public_errors == [
        {
            "code": "provider_unavailable",
            "message": "无法连接市场数据提供方，当前未生成分析结果。",
            "retryable": True,
            "correlation_id": "task-owned-correlation",
        }
    ]


def test_public_error_reports_partial_research_when_verified_evidence_is_preserved() -> (
    None
):
    public_errors = _public_error(
        {
            "terminal_status": "failed",
            "web_evidence": [
                {
                    "final_url": "https://example.com/verified-market",
                    "evidence_relation": "market_snapshot",
                }
            ],
            "errors": [
                {
                    "code": "research_unavailable",
                    "endpoint": "research_events",
                    "retryable": True,
                }
            ],
        },
        correlation_id="task-owned-correlation",
    )

    assert public_errors == [
        {
            "code": "research_unavailable",
            "message": "研究检索阶段未完成；本次运行已保留 1 条可验证来源，但没有生成新的分析结果。",
            "retryable": True,
            "correlation_id": "task-owned-correlation",
            "endpoint": "research_events",
        }
    ]
    ProductErrorView.model_validate(public_errors[0])


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("endpoint", "https://provider.invalid/raw"),
        ("fallback_from", "okx\nraw-response"),
        ("primary_attempt", 101),
    ),
)
def test_product_error_view_rejects_unsafe_fallback_diagnostics(
    field: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "code": "provider_unavailable",
        "message": "Market providers failed.",
        "correlation_id": "task-owned-correlation",
        "retryable": True,
        "endpoint": "web_search_market",
        "fallback_from": "okx",
        "primary_attempt": 2,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ProductErrorView.model_validate(payload)


def test_model_invalid_output_has_a_safe_non_retryable_product_projection() -> None:
    public_errors = _public_error(
        {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "model_invalid_output",
                    "error_type": "StructuredOutputValidationError",
                    "retryable": False,
                    "raw_response": "must-not-leak",
                    "tool_args": {"must": "not-leak"},
                }
            ],
        },
        correlation_id="task-owned-correlation",
    )

    assert public_errors == [
        {
            "code": "model_invalid_output",
            "message": "分析模型未返回有效结构化结果，当前未生成分析结果。",
            "retryable": False,
            "correlation_id": "task-owned-correlation",
            "error_type": "StructuredOutputValidationError",
        }
    ]


def test_completion_projection_keeps_analysis_and_notification_outcomes_separate() -> (
    None
):
    scope, warnings = _completion_projection(
        status="succeeded",
        notification_requested=True,
        notification_status="failed_retryable",
    )

    assert scope == {
        "analysis": "complete",
        "notification": "retrying",
        "observability": "not_enabled",
    }
    assert warnings == ["notification_delivery_retrying"]


def test_failed_terminal_output_rejects_an_artifact() -> None:
    with pytest.raises(
        ValidationError, match="failed output cannot contain an artifact"
    ):
        TerminalGraphOutput.model_validate(
            {
                "terminal_status": "failed",
                "artifact": _review_payload()["artifact"],
                "errors": [{"code": "model_invalid_output", "retryable": False}],
            }
        )


def test_failed_terminal_output_requires_a_structured_error() -> None:
    with pytest.raises(ValidationError, match="failed output requires an error"):
        TerminalGraphOutput.model_validate({"terminal_status": "failed"})


@pytest.mark.parametrize(
    "code",
    (
        '{"authorization":"must-not-cross"}',
        "provider unavailable\nraw response",
        "X" * 129,
    ),
)
def test_terminal_error_code_rejects_unbounded_or_structured_text(code: str) -> None:
    with pytest.raises(ValidationError):
        TerminalGraphOutput.model_validate(
            {
                "terminal_status": "failed",
                "errors": [{"code": code, "retryable": False}],
            }
        )


def test_terminal_error_drops_unknown_raw_diagnostics() -> None:
    terminal = TerminalGraphOutput.model_validate(
        {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "provider_unavailable",
                    "provider": "okx",
                    "error_type": "ProviderUnavailable",
                    "retryable": True,
                    "endpoint": "web_search_market",
                    "fallback_from": "okx",
                    "primary_attempt": 2,
                    "raw_response": "must-not-persist",
                    "authorization": "must-not-persist",
                }
            ],
        }
    )

    payload = terminal.model_dump(mode="json", exclude_none=True)
    assert payload["errors"] == [
        {
            "code": "provider_unavailable",
            "retryable": True,
            "provider": "okx",
            "error_type": "ProviderUnavailable",
            "endpoint": "web_search_market",
            "fallback_from": "okx",
            "primary_attempt": 2,
        }
    ]


def test_product_service_has_no_in_process_dispatch_path() -> None:
    assert not hasattr(ProductAnalysisService, "dispatch_task")


@pytest.mark.asyncio
async def test_create_analysis_uses_server_owned_actor() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "origin": "http://127.0.0.1:3001",
                "idempotency-key": "analysis-admission-1",
                "x-request-id": "bff-analysis-request-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["correlation_id"] == correlation_id_for_task("task-1")
    assert response.headers["x-request-id"] == "bff-analysis-request-1"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.user_id == "compose-user"
    assert service.actor.roles == ("member",)
    assert service.idempotency_key == "analysis-admission-1"
    assert service.submission.model_dump(mode="json") == {
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "query_text": "Assess current BTC risk.",
        "notify": False,
    }
    assert service.dispatch_calls == 0


@pytest.mark.asyncio
async def test_create_deep_research_uses_the_same_product_admission_boundary() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/deep-research",
            headers={
                "origin": "http://127.0.0.1:3001",
                "idempotency-key": "deep-research-admission-1",
                "x-request-id": "bff-deep-research-request-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "7d",
                "query_text": "研究 BTC 机构采用趋势和主要反证。",
            },
        )

    assert response.status_code == 202
    assert response.json()["task_type"] == "deep_research"
    assert response.json()["status"] == "queued"
    assert response.headers["x-request-id"] == "bff-deep-research-request-1"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.user_id == "compose-user"
    assert service.idempotency_key == "deep-research-admission-1"
    assert service.submission.model_dump(mode="json") == {
        "task_type": "deep_research",
        "symbol": "BTC-USDT-SWAP",
        "horizon": "7d",
        "query_text": "研究 BTC 机构采用趋势和主要反证。",
    }
    assert service.dispatch_calls == 0


@pytest.mark.asyncio
async def test_create_analysis_rejects_client_owned_authority_and_identity() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "origin": "http://127.0.0.1:3001",
                "idempotency-key": "analysis-admission-attacker",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
                "tenant_id": "attacker",
                "user_id": "attacker",
                "roles": ["admin"],
                "authority": {"permissions": ["admin"]},
                "correlation_id": "client-owned-correlation",
                "request_id": "body-request-id",
            },
        )

    assert response.status_code == 422
    assert response.headers["x-request-id"]
    assert service.actor is None
    assert service.submission is None


@pytest.mark.asyncio
async def test_list_runs_uses_server_owned_actor_and_typed_projection() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/runs", params={"limit": 25})

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "run_id": "11111111-1111-4111-8111-111111111111",
                "task_id": "22222222-2222-4222-8222-222222222222",
                "task_type": "market_analysis",
                "attempt": 1,
                "status": "succeeded",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": "2026-07-13T00:00:00Z",
                "finished_at": "2026-07-13T00:05:00Z",
                "main_action": "no_trade",
            }
        ],
        "limit": 25,
    }
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.workspace_id == "compose-workspace"
    assert service.actor.user_id == "compose-user"
    assert service.actor.user_id == "compose-user"


@pytest.mark.asyncio
async def test_run_detail_and_artifact_library_use_server_owned_actor() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        run_response = await client.get(
            "/api/v2/runs/11111111-1111-4111-8111-111111111111"
        )
        library_response = await client.get("/api/v2/artifacts", params={"limit": 50})
        artifact_response = await client.get(
            "/api/v2/artifacts/44444444-4444-4444-8444-444444444444",
            params={"version_number": 1},
        )
        cancel_run_response = await client.post(
            "/api/v2/runs/11111111-1111-4111-8111-111111111111/cancel",
            headers={"Idempotency-Key": "cancel-run-contract"},
        )
        feedback_response = await client.post(
            "/api/v2/runs/11111111-1111-4111-8111-111111111111/feedback",
            headers={"Idempotency-Key": "feedback-contract"},
            json={"rating": "positive", "comment": "Useful evidence."},
        )

    assert run_response.status_code == 200
    assert (
        run_response.json()["run"]["run_id"] == "11111111-1111-4111-8111-111111111111"
    )
    assert (
        run_response.json()["task"]["task_id"] == "22222222-2222-4222-8222-222222222222"
    )
    assert library_response.status_code == 200
    assert library_response.json()["items"][0]["artifact_type"] == "analysis_report"
    assert (
        library_response.json()["items"][0]["run_id"]
        == "11111111-1111-4111-8111-111111111111"
    )
    assert artifact_response.status_code == 200
    assert artifact_response.json()["selected_version"]["version_number"] == 1
    assert (
        artifact_response.json()["selected_version"]["content"]["analysis"][
            "main_action"
        ]
        == "open_long"
    )
    assert cancel_run_response.status_code == 202
    assert cancel_run_response.json()["cancel_requested_at"] == "2026-07-13T00:01:00Z"
    assert service.cancelled_run_id == "11111111-1111-4111-8111-111111111111"
    assert feedback_response.status_code == 201
    assert feedback_response.json()["rating"] == "positive"
    assert service.feedback_run_id == "11111111-1111-4111-8111-111111111111"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.workspace_id == "compose-workspace"
    assert service.actor.user_id == "compose-user"


@pytest.mark.asyncio
async def test_list_inbox_uses_defaults_and_returns_a_strict_typed_projection() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/inbox")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "task_id": "22222222-2222-4222-8222-222222222222",
                "pause_id": PAUSE_ID,
                "pause_version": 1,
                "status": "responding",
                "member_count": 2,
                "payload": _review_payload(),
                "expires_at": "2026-07-13T00:10:00Z",
                "responded_at": "2026-07-13T00:02:00Z",
                "created_at": "2026-07-13T00:00:00Z",
                "updated_at": "2026-07-13T00:02:00Z",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
            }
        ],
        "next_cursor": "next-cursor",
    }
    assert service.inbox_status == "active"
    assert service.inbox_limit == 50
    assert service.inbox_cursor is None
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.workspace_id == "compose-workspace"


@pytest.mark.asyncio
async def test_inbox_review_forwards_product_owned_single_member_submission() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            f"/api/v2/inbox/{PAUSE_ID}/respond",
            headers={"idempotency-key": "inbox-review-1"},
            json={
                "pause_version": 4,
                "response": {
                    "action": "reject",
                    "comment": "Evidence needs a narrower conclusion.",
                },
            },
        )

    assert response.status_code == 202
    assert response.json() == {
        "task_id": "task-1",
        "pause_id": PAUSE_ID,
        "pause_version": 4,
        "status": "responding",
        "responded_at": "2026-07-13T00:01:00Z",
    }
    assert service.inbox_review_pause_id == UUID(PAUSE_ID)
    assert service.inbox_review_submission.pause_version == 4
    assert service.inbox_review_submission.response.action == "reject"
    assert service.inbox_review_idempotency_key == "inbox-review-1"


@pytest.mark.asyncio
async def test_inbox_review_rejects_runtime_projection_fields() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            f"/api/v2/inbox/{PAUSE_ID}/respond",
            headers={"idempotency-key": "inbox-review-runtime-field"},
            json={
                "pause_version": 1,
                "interrupt_id": "must-not-be-accepted",
                "response": {"action": "approve"},
            },
        )

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
async def test_list_notifications_returns_owner_scoped_status_and_attempts() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/tasks/task-1/notifications")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "22222222-2222-4222-8222-222222222222"
    assert payload["items"][0]["status"] == "unknown"
    assert payload["items"][0]["manual_resend_available"] is True
    assert payload["items"][0]["attempts"] == [
        {
            "attempt_id": "88888888-8888-4888-8888-888888888888",
            "attempt_number": 1,
            "trigger": "automatic",
            "result": "unknown",
            "reason": "delivery_outcome_uncertain",
            "delay_seconds": 0,
            "retry_after_seconds": None,
            "cost_units": "0.000000",
            "provider_receipt": None,
            "error_code": "delivery_outcome_uncertain",
            "created_at": "2026-07-13T00:01:00Z",
            "finished_at": "2026-07-13T00:02:00Z",
        }
    ]
    assert service.notification_task_id == "task-1"
    assert service.actor is not None
    assert service.actor.user_id == "compose-user"


@pytest.mark.asyncio
async def test_notification_resend_queues_audited_request() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/notifications/77777777-7777-4777-8777-777777777777/resend",
            json={"reason": "User confirmed a single retry."},
        )

    assert response.status_code == 202
    assert response.json()["manual_resend_pending"] is True
    assert response.json()["manual_resend_available"] is False
    assert service.notification_id == "77777777-7777-4777-8777-777777777777"
    assert service.notification_resend_reason == "User confirmed a single retry."
    assert service.actor is not None
    assert service.actor.workspace_id == "compose-workspace"


@pytest.mark.asyncio
async def test_notification_routes_do_not_disclose_unknown_resources() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        missing_task = await client.get("/api/v2/tasks/missing-task/notifications")
        missing_notification = await client.post(
            "/api/v2/notifications/99999999-9999-4999-8999-999999999999/resend",
            json={"reason": "User confirmed a single retry."},
        )

    assert missing_task.status_code == 404
    assert missing_notification.status_code == 404


@pytest.mark.asyncio
async def test_notification_settings_never_return_the_device_key() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/settings/notifications")

    assert response.status_code == 200
    assert response.json() == {
        "channel": "bark",
        "enabled": False,
        "configured": True,
        "updated_at": "2026-07-13T00:04:00Z",
    }
    assert "device" not in response.text.lower()
    assert "credential" not in response.text.lower()
    assert service.actor is not None
    assert service.actor.user_id == "compose-user"


@pytest.mark.asyncio
async def test_notification_settings_patch_forwards_a_secret_submission_without_echo() -> (
    None
):
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.patch(
            "/api/v2/settings/notifications",
            json={"enabled": True, "device_key": "bark-device-key-canary"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "channel": "bark",
        "enabled": True,
        "configured": True,
        "updated_at": "2026-07-13T00:05:00Z",
    }
    assert "bark-device-key-canary" not in response.text
    assert service.notification_settings_submission.enabled is True
    assert (
        service.notification_settings_submission.device_key.get_secret_value()
        == "bark-device-key-canary"
    )
    assert "bark-device-key-canary" not in repr(
        service.notification_settings_submission
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {"enabled": True, "device_key": "short"},
        {
            "enabled": True,
            "device_key": "bark-device-key-canary",
            "tenant_id": "client-owned",
        },
        {"enabled": True, "credential_ciphertext": "client-owned"},
    ),
)
async def test_notification_settings_patch_rejects_invalid_or_client_owned_fields(
    payload: dict[str, Any],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.patch(
            "/api/v2/settings/notifications",
            json=payload,
        )

    assert response.status_code == 422
    assert service.notification_settings_submission is None


class ConflictingNotificationSettingsService(FakeProductService):
    async def update_notification_settings(
        self,
        actor: ActorContext,
        submission: Any,
    ) -> dict[str, Any]:
        del actor, submission
        raise NotificationSettingsConflictError(
            "A Bark device key is required before notifications can be enabled."
        )


class UnavailableNotificationSettingsService(FakeProductService):
    async def update_notification_settings(
        self,
        actor: ActorContext,
        submission: Any,
    ) -> dict[str, Any]:
        del actor, submission
        raise NotificationSettingsUnavailableError(
            "Notification credential encryption is not configured."
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "status_code", "detail"),
    (
        (
            ConflictingNotificationSettingsService(),
            409,
            "A Bark device key is required before notifications can be enabled.",
        ),
        (
            UnavailableNotificationSettingsService(),
            503,
            "Notification credential encryption is not configured.",
        ),
    ),
)
async def test_notification_settings_patch_maps_safe_service_errors(
    service: FakeProductService,
    status_code: int,
    detail: str,
) -> None:
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.patch(
            "/api/v2/settings/notifications",
            json={"enabled": True, "device_key": "bark-device-key-canary"},
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inbox_status",
    ("active", "pending", "responding", "resolved", "expired", "all"),
)
async def test_list_inbox_forwards_supported_status_limit_and_cursor(
    inbox_status: str,
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get(
            "/api/v2/inbox",
            params={
                "status": inbox_status,
                "limit": 100,
                "cursor": "opaque-cursor",
            },
        )

    assert response.status_code == 200
    assert service.inbox_status == inbox_status
    assert service.inbox_limit == 100
    assert service.inbox_cursor == "opaque-cursor"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    (
        {"status": "cancelled"},
        {"status": "unknown"},
        {"limit": 0},
        {"limit": 101},
        {"cursor": ""},
        {"cursor": "x" * 2049},
    ),
)
async def test_list_inbox_rejects_invalid_query_parameters(
    params: dict[str, object],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/inbox", params=params)

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
async def test_list_inbox_fails_closed_for_a_malformed_opaque_cursor() -> None:
    transport = httpx.ASGITransport(app=_development_app(InvalidInboxCursorService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get(
            "/api/v2/inbox",
            params={"cursor": "not-a-valid-inbox-cursor"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid inbox cursor."}


@pytest.mark.asyncio
async def test_get_task_forwards_an_explicit_historical_run_selection() -> None:
    service = FakeProductService()
    run_id = "11111111-1111-4111-8111-111111111111"
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.get(
            "/api/v2/tasks/task-1",
            params={"run_id": run_id},
        )

    assert response.status_code == 200
    assert service.selected_run_id == UUID(run_id)


@pytest.mark.asyncio
async def test_cancel_task_persists_a_server_owned_product_command() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/cancel",
            headers={"idempotency-key": "cancel-task-1"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert response.json()["cancel_requested_at"] == "2026-07-13T00:01:00Z"
    assert service.cancelled_task_id == "task-1"
    assert service.cancel_idempotency_key == "cancel-task-1"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"


@pytest.mark.asyncio
async def test_retry_task_persists_a_server_owned_product_command() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/retry",
            headers={"idempotency-key": "retry-task-1"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert service.retried_task_id == "task-1"
    assert service.retry_idempotency_key == "retry-task-1"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"


@pytest.mark.asyncio
async def test_fork_task_derives_checkpoint_from_owner_scoped_source_run() -> None:
    service = FakeProductService()
    source_run_id = "11111111-1111-4111-8111-111111111111"
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/fork",
            headers={"idempotency-key": "fork-task-1"},
            json={"source_run_id": source_run_id},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert service.forked_task_id == "task-1"
    assert service.fork_submission.source_run_id == UUID(source_run_id)
    assert service.fork_submission.checkpoint_id is None
    assert service.fork_idempotency_key == "fork-task-1"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"


@pytest.mark.asyncio
async def test_fork_task_rejects_unrecognized_runtime_coordinates() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/fork",
            headers={"idempotency-key": "fork-task-invalid"},
            json={
                "source_run_id": "11111111-1111-4111-8111-111111111111",
                "checkpoint_id": "checkpoint-1",
                "checkpoint_ns": "browser-controlled",
            },
        )

    assert response.status_code == 422
    assert service.forked_task_id is None


@pytest.mark.asyncio
async def test_respond_interrupt_forwards_strict_review_and_returns_task_view() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/interrupt-1/respond",
            headers={"idempotency-key": "respond-interrupt-1"},
            json={
                "response_version": 3,
                "action": "edit",
                "comment": "Reduce risk before approval.",
                "edits": {
                    "main_action": "no_trade",
                    "max_leverage": 1,
                },
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "waiting_human"
    assert body["pending_interrupts"]["status"] == "responding"
    review = body["pending_interrupts"]["members"][0]["response"]
    assert review["action"] == "edit"
    assert review["comment"] == "Reduce risk before approval."
    assert review["edits"]["main_action"] == "no_trade"
    assert review["edits"]["max_leverage"] == 1
    assert service.responded_task_id == "task-1"
    assert service.responded_interrupt_id == "interrupt-1"
    assert service.interrupt_idempotency_key == "respond-interrupt-1"
    assert service.interrupt_submission.response_version == 3
    assert service.interrupt_submission.action == "edit"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.workspace_id == "compose-workspace"
    assert service.actor.user_id == "compose-user"


@pytest.mark.asyncio
async def test_respond_all_forwards_one_strict_aggregate_command() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/respond-all",
            headers={"idempotency-key": "respond-pause-1"},
            json={
                "pause_id": PAUSE_ID,
                "pause_version": 4,
                "responses": [
                    {
                        "interrupt_id": "interrupt-root",
                        "response_version": 2,
                        "response": {"action": "approve"},
                    },
                    {
                        "interrupt_id": "interrupt-nested",
                        "response_version": 7,
                        "response": {
                            "action": "reject",
                            "comment": "Nested evidence is insufficient.",
                        },
                    },
                ],
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["pending_interrupts"]["pause_id"] == PAUSE_ID
    assert body["pending_interrupts"]["pause_version"] == 4
    assert [
        member["interrupt_id"] for member in body["pending_interrupts"]["members"]
    ] == ["interrupt-root", "interrupt-nested"]
    assert service.responded_task_id == "task-1"
    assert service.responded_interrupt_id is None
    assert service.interrupt_idempotency_key == "respond-pause-1"
    assert [item.interrupt_id for item in service.interrupt_submission.responses] == [
        "interrupt-root",
        "interrupt-nested",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {
            "pause_id": PAUSE_ID,
            "pause_version": 1,
            "responses": [],
        },
        {
            "pause_id": PAUSE_ID,
            "pause_version": 1,
            "responses": [
                {
                    "interrupt_id": "duplicate",
                    "response_version": 1,
                    "response": {"action": "approve"},
                },
                {
                    "interrupt_id": "duplicate",
                    "response_version": 1,
                    "response": {"action": "reject"},
                },
            ],
        },
        {
            "pause_id": PAUSE_ID,
            "pause_version": 1,
            "responses": [
                {
                    "interrupt_id": "nested",
                    "response_version": 1,
                    "response": {"action": "edit"},
                }
            ],
        },
        {
            "pause_id": PAUSE_ID,
            "pause_version": 1,
            "responses": [
                {
                    "interrupt_id": "root",
                    "response_version": 1,
                    "response": {"action": "approve", "unexpected": True},
                }
            ],
        },
    ),
)
async def test_respond_all_rejects_partial_or_invalid_batch_contract(
    payload: dict[str, Any],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/respond-all",
            headers={"idempotency-key": "respond-invalid-pause"},
            json=payload,
        )

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {"response_version": 0, "action": "approve"},
        {"response_version": 1, "action": "edit"},
        {
            "response_version": 1,
            "action": "approve",
            "edits": {"main_action": "no_trade"},
        },
        {"response_version": 1, "action": "reject", "comment": ""},
        {"response_version": 1, "action": "approve", "unexpected": True},
        {
            "response_version": 1,
            "action": "edit",
            "edits": {"main_action": "no_trade", "unexpected": True},
        },
    ),
)
async def test_respond_interrupt_reuses_strict_graph_review_validation(
    payload: dict[str, Any],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/interrupt-1/respond",
            headers={"idempotency-key": "respond-invalid-review"},
            json=payload,
        )

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    (
        {},
        {"idempotency-key": "contains spaces"},
        {"idempotency-key": "x" * 256},
    ),
)
async def test_respond_interrupt_requires_an_allowed_idempotency_key(
    headers: dict[str, str],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/interrupt-1/respond",
            headers=headers,
            json={"response_version": 1, "action": "approve"},
        )

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
async def test_respond_interrupt_returns_404_without_leaking_scope() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/not-visible/respond",
            headers={"idempotency-key": "respond-not-visible"},
            json={"response_version": 1, "action": "approve"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task or interrupt not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "detail"),
    (
        (
            IdempotencyConflictError(
                "Idempotency-Key was already used with a different interrupt "
                "response payload."
            ),
            "Idempotency-Key was already used with a different interrupt "
            "response payload.",
        ),
        (
            InterruptResponseConflictError("Interrupt response_version is stale."),
            "Interrupt response_version is stale.",
        ),
    ),
)
async def test_respond_interrupt_maps_service_conflicts_to_409(
    error: RuntimeError,
    detail: str,
) -> None:
    transport = httpx.ASGITransport(
        app=_development_app(ConflictingInterruptService(error))
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/interrupt-1/respond",
            headers={"idempotency-key": "respond-conflict"},
            json={"response_version": 1, "action": "approve"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": detail}


@pytest.mark.asyncio
async def test_respond_interrupt_returns_503_when_persistence_is_unavailable() -> None:
    transport = httpx.ASGITransport(app=_development_app(UnavailableProductService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/interrupt-1/respond",
            headers={"idempotency-key": "respond-unavailable"},
            json={"response_version": 1, "action": "approve"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Product persistence is not configured"}


@pytest.mark.asyncio
async def test_respond_interrupt_returns_403_for_an_unprovisioned_actor() -> None:
    transport = httpx.ASGITransport(app=_development_app(UnprovisionedProductService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/interrupts/interrupt-1/respond",
            headers={"idempotency-key": "respond-unprovisioned"},
            json={"response_version": 1, "action": "approve"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "permission_required",
            "message": "The requested operation is not permitted.",
        }
    }


@pytest.mark.asyncio
async def test_cancel_task_returns_404_without_leaking_cross_tenant_existence() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/not-visible/cancel",
            headers={"idempotency-key": "cancel-not-visible"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    (
        {},
        {"idempotency-key": "contains spaces"},
        {"idempotency-key": "x" * 256},
    ),
)
async def test_create_analysis_requires_an_allowed_idempotency_key(
    headers: dict[str, str],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=create_app(service=service, mode="local"))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers=headers,
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
async def test_create_analysis_returns_explicit_409_for_payload_conflict() -> None:
    transport = httpx.ASGITransport(
        app=_development_app(ConflictingProductService()),
        raise_app_exceptions=False,
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "analysis-conflict-1"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Idempotency-Key was already used with a different analysis payload."
        )
    }


@pytest.mark.asyncio
async def test_production_missing_auth_returns_401_not_500() -> None:
    transport = httpx.ASGITransport(
        app=_production_app(
            FakeProductService(),
            RejectingMissingAuthorizationVerifier(),
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "production-missing-auth"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401


@pytest.mark.parametrize("environment", ("staging", "production"))
def test_hosted_runtime_requires_token_verifier_at_startup(environment: str) -> None:
    with pytest.raises(ValueError, match="token_verifier"):
        create_app(service=FakeProductService(), mode=environment)


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ("local", "test", "development"))
async def test_non_explicit_development_runtime_does_not_bypass_jwt(
    environment: str,
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=create_app(service=service, mode=environment))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": f"{environment}-missing-auth"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401
    assert service.actor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "overrides"),
    (
        ("local-environment", {"app_environment": "local"}),
        ("test-environment", {"app_environment": "test"}),
        ("disabled", {"development_bootstrap_enabled": False}),
        ("missing-profile", {"development_bootstrap_profile": ""}),
        ("missing-subject", {"development_bootstrap_subject": ""}),
        ("missing-tenant", {"development_bootstrap_tenant_id": ""}),
        ("missing-workspace", {"development_bootstrap_workspace_id": ""}),
        ("missing-roles", {"development_bootstrap_roles": ()}),
        ("missing-permissions", {"development_bootstrap_permissions": ()}),
        ("whitespace-subject", {"development_bootstrap_subject": " \t "}),
        ("whitespace-tenant", {"development_bootstrap_tenant_id": " \t "}),
        (
            "whitespace-workspace",
            {"development_bootstrap_workspace_id": " \t "},
        ),
        ("whitespace-roles", {"development_bootstrap_roles": (" \t ",)}),
        (
            "whitespace-permissions",
            {"development_bootstrap_permissions": (" \t ",)},
        ),
    ),
)
async def test_incomplete_development_bootstrap_does_not_bypass_jwt(
    case: str,
    overrides: dict[str, object],
) -> None:
    del case
    settings = _development_settings(**overrides)
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=settings.app_environment,
            settings=settings,
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "incomplete-development-bootstrap"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401
    assert service.actor is None


@pytest.mark.asyncio
async def test_complete_local_proof_development_runtime_uses_configured_actor() -> None:
    settings = _development_settings()
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=settings.app_environment,
            settings=settings,
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "explicit-development-bootstrap"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 202
    assert service.actor == ActorContext(
        tenant_id="compose-tenant",
        workspace_id="compose-workspace",
        user_id="compose-user",
        identity_issuer="crypto-alert-v2-development",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


@pytest.mark.asyncio
async def test_loopback_request_metadata_does_not_override_remote_peer() -> None:
    settings = _development_settings()
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=settings.app_environment,
            settings=settings,
        ),
        client=("203.0.113.10", 4321),
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "host": "127.0.0.1:8011",
                "origin": "http://127.0.0.1:3001",
                "idempotency-key": "spoofed-loopback-metadata",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 403
    assert service.actor is None


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ("staging", "production"))
async def test_hosted_runtime_requires_jwt(environment: str) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=_production_app(
            service,
            RejectingMissingAuthorizationVerifier(),
            mode=environment,
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": f"{environment}-missing-jwt"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401
    assert service.actor is None


@pytest.mark.asyncio
async def test_production_uses_verified_internal_token_claims() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=_production_app(service, AcceptingTokenVerifier())
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "authorization": "Bearer signed-internal-token",
                "idempotency-key": "production-analysis-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 202
    assert service.actor is not None
    assert service.actor.tenant_id == "tenant-1"
    assert service.actor.workspace_id == "workspace-1"
    assert service.actor.user_id == "oidc|user-1"


@pytest.mark.asyncio
async def test_unprovisioned_production_actor_returns_403_not_500() -> None:
    transport = httpx.ASGITransport(
        app=_production_app(
            UnprovisionedProductService(),
            AcceptingTokenVerifier(),
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "authorization": "Bearer signed-internal-token",
                "idempotency-key": "unprovisioned-analysis-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "permission_required",
            "message": "The requested operation is not permitted.",
        }
    }


@pytest.mark.asyncio
async def test_task_view_returns_readable_failure_not_raw_graph_state() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get(
            "/api/v2/tasks/task-1",
            headers={"origin": "http://127.0.0.1:3001"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["correlation_id"] == correlation_id_for_task("task-1")
    assert body["errors"][0]["code"] == "provider_unavailable"
    assert body["errors"][0]["correlation_id"] == correlation_id_for_task("task-1")
    assert body["market_snapshot"] is None
    assert body["web_evidence"] == []
    assert "state" not in body
    assert "messages" not in body


@pytest.mark.asyncio
async def test_home_and_watchlist_routes_return_product_projection() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        home_response = await client.get(
            "/api/v2/home",
            headers={"origin": "http://127.0.0.1:3001"},
        )
        watchlist_response = await client.delete(
            "/api/v2/watchlist/BTC-USDT-SWAP",
            headers={"origin": "http://127.0.0.1:3001"},
        )

    assert home_response.status_code == 200
    assert home_response.json()["watchlist"][0]["symbol"] == "BTC-USDT-SWAP"
    assert "raw_state" not in home_response.json()
    assert watchlist_response.status_code == 200
    assert service.watchlist_symbol == ("BTC-USDT-SWAP", False)


@pytest.mark.asyncio
async def test_request_id_is_returned_on_safe_http_errors() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"x-request-id": "bff-validation-request-1"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 422
    assert response.headers["x-request-id"] == "bff-validation-request-1"


@pytest.mark.asyncio
async def test_health_is_explicit() -> None:
    transport = httpx.ASGITransport(
        app=create_app(service=FakeProductService(), mode="local")
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "2.0.0"}


@pytest.mark.asyncio
async def test_readiness_is_separate_from_liveness_in_local_runtime() -> None:
    transport = httpx.ASGITransport(
        app=create_app(service=FakeProductService(), mode="local")
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "2.0.0"}


@pytest.mark.asyncio
async def test_create_monitor_returns_stable_422_for_unavailable_evaluator() -> None:
    transport = httpx.ASGITransport(app=_development_app(UnavailableMonitorEvaluatorService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/monitors",
            headers={"Idempotency-Key": "monitor-price-1"},
            json={
                "name": "BTC price threshold",
                "artifact_id": "44444444-4444-4444-8444-444444444444",
                "artifact_version_id": "55555555-5555-4555-8555-555555555555",
                "run_task_type": "market_analysis",
                "condition": {
                    "kind": "price",
                    "operator": "gte",
                    "threshold": 70000,
                },
                "schedule": "0 * * * *",
                "timezone": "UTC",
                "expires_at": "2026-08-01T00:00:00Z",
                "destination_ids": [],
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "monitor_condition_evaluator_unavailable",
            "message": "No evaluator is available for monitor condition 'price'.",
            "condition": "price",
        }
    }


@pytest.mark.asyncio
async def test_manual_monitor_trigger_returns_stable_422_for_unavailable_evaluator() -> None:
    transport = httpx.ASGITransport(app=_development_app(UnavailableMonitorEvaluatorService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/monitors/44444444-4444-4444-8444-444444444444/trigger",
            headers={"Idempotency-Key": "monitor-price-trigger-1"},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "monitor_condition_evaluator_unavailable"
    )
    assert response.json()["detail"]["condition"] == "price"
