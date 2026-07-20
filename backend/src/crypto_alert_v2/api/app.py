from contextlib import asynccontextmanager
from base64 import b64decode
from binascii import Error as BinasciiError
from hashlib import sha256
import asyncio
import hmac
import httpx
from typing import Annotated, Any, AsyncIterator, Mapping, Protocol
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.request_identity import request_identity_middleware
from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    DataDeletionSubmission,
    DataDeletionView,
    DataExportBundleView,
    DataExportManifestView,
    DataExportSubmission,
    DataExportView,
    DataLifecyclePolicyUpdate,
    DataLifecyclePolicyView,
    DeepResearchSubmission,
    ArtifactDetailView,
    ArtifactLibraryView,
    AuthContextListView,
    AuthContextSelection,
    AuthContextView,
    ForkSubmission,
    FeedbackSubmission,
    FeedbackView,
    HealthView,
    HomeView,
    IDEMPOTENCY_KEY_PATTERN,
    InboxQueryStatus,
    InboxReviewReceiptView,
    InboxReviewSubmission,
    InboxView,
    InterruptResponseSubmission,
    InterruptResponsesSubmission,
    MonitorCreateSubmission,
    MonitorListView,
    MonitorMutationSubmission,
    MonitorStatusFilter,
    MonitorTriggerListView,
    MonitorView,
    NotificationListView,
    NotificationResendSubmission,
    NotificationSettingsUpdate,
    NotificationSettingsView,
    NotificationView,
    RunDetailView,
    RunListView,
    TaskView,
)
from crypto_alert_v2.api.service import (
    ForkConflictError,
    IdempotencyConflictError,
    InvalidInboxCursorError,
    InterruptResponseConflictError,
    ProductAnalysisService,
    FeedbackConflictError,
    RunNotCancellableError,
    NotificationSettingsConflictError,
    NotificationSettingsUnavailableError,
    MonitorConditionEvaluatorUnavailableError,
    MonitorConflictError,
    MonitorEntitlementError,
    MonitorSourceError,
    TaskNotCancellableError,
    TaskNotRetryableError,
    WatchlistSymbolError,
)
from crypto_alert_v2.notifications.outbox import (
    NotificationNotResendable,
    NotificationRetryBudgetExhausted,
)
from crypto_alert_v2.notifications.credentials import (
    notification_credential_cipher_from_environment,
)
from crypto_alert_v2.testing.failure_injection import (
    FailureInjectionController,
    FailureInjectionConflict,
    FailureScenarioUpdate,
    failure_injection_from_settings,
)
from crypto_alert_v2.auth.context import (
    ActorContext,
    configured_development_actor,
    resolve_actor_context,
)
from crypto_alert_v2.auth.internal_token import InternalTokenVerifier
from crypto_alert_v2.auth.internal_token import IDENTITY_DISCOVERY_AUDIENCE
from crypto_alert_v2.auth.membership import (
    AUTH_CONTEXT_NOT_FOUND,
    AuthenticatedIdentity,
    DatabaseMembershipAuthority,
    MembershipAuthority,
    MembershipContext,
)
from crypto_alert_v2.config import Settings, get_settings
from crypto_alert_v2.lifecycle import LifecycleError


class ProductService(Protocol):
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: AnalysisSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    async def create_deep_research(
        self,
        actor: ActorContext,
        submission: DeepResearchSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    async def create_monitor(
        self,
        actor: ActorContext,
        submission: MonitorCreateSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    async def list_monitors(
        self,
        actor: ActorContext,
        *,
        status_filter: MonitorStatusFilter,
    ) -> dict[str, Any]: ...

    async def list_monitor_triggers(
        self,
        actor: ActorContext,
        monitor_id: str,
        *,
        limit: int,
    ) -> dict[str, Any] | None: ...

    async def pause_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def resume_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def trigger_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def disable_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None: ...

    async def list_runs(self, actor: ActorContext, *, limit: int) -> dict[str, Any]: ...

    async def get_run(
        self,
        actor: ActorContext,
        run_id: str,
    ) -> dict[str, Any] | None: ...

    async def submit_feedback(
        self,
        actor: ActorContext,
        run_id: str,
        submission: FeedbackSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def list_artifacts(
        self,
        actor: ActorContext,
        *,
        limit: int,
    ) -> dict[str, Any]: ...

    async def get_home(self, actor: ActorContext) -> dict[str, Any]: ...

    async def set_watchlist_symbol(
        self,
        actor: ActorContext,
        symbol: str,
        *,
        included: bool,
    ) -> dict[str, Any]: ...

    async def list_inbox(
        self,
        actor: ActorContext,
        *,
        status: InboxQueryStatus,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]: ...

    async def respond_inbox_review(
        self,
        actor: ActorContext,
        pause_id: UUID,
        submission: InboxReviewSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def list_notifications(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> dict[str, Any] | None: ...

    async def request_notification_resend(
        self,
        actor: ActorContext,
        notification_id: str,
        submission: NotificationResendSubmission,
    ) -> dict[str, Any] | None: ...

    async def get_notification_settings(
        self,
        actor: ActorContext,
    ) -> dict[str, Any]: ...

    async def update_notification_settings(
        self,
        actor: ActorContext,
        submission: NotificationSettingsUpdate,
    ) -> dict[str, Any]: ...

    async def cancel_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def cancel_run(
        self,
        actor: ActorContext,
        run_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def retry_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def fork_task(
        self,
        actor: ActorContext,
        task_id: str,
        submission: ForkSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def respond_interrupt(
        self,
        actor: ActorContext,
        task_id: str,
        interrupt_id: str,
        submission: InterruptResponseSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def respond_interrupts(
        self,
        actor: ActorContext,
        task_id: str,
        submission: InterruptResponsesSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    async def get_data_lifecycle_policy(self, actor: ActorContext) -> dict[str, Any]: ...

    async def update_data_lifecycle_policy(
        self, actor: ActorContext, submission: DataLifecyclePolicyUpdate
    ) -> dict[str, Any]: ...

    async def create_data_export(
        self, actor: ActorContext, submission: DataExportSubmission, idempotency_key: str
    ) -> dict[str, Any]: ...

    async def get_data_export(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None: ...

    async def get_data_export_manifest(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None: ...

    async def get_data_export_bundle(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None: ...

    async def create_data_deletion(
        self, actor: ActorContext, submission: DataDeletionSubmission, idempotency_key: str
    ) -> dict[str, Any]: ...

    async def get_data_deletion(
        self, actor: ActorContext, deletion_id: UUID
    ) -> dict[str, Any] | None: ...


class TokenVerifier(Protocol):
    def verify_authorization(self, authorization: str | None) -> Mapping[str, Any]: ...


class UnavailableProductService:
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: AnalysisSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def get_data_lifecycle_policy(self, actor: ActorContext) -> dict[str, Any]:
        del actor
        raise HTTPException(status_code=503, detail="Product persistence is not configured")

    async def update_data_lifecycle_policy(
        self, actor: ActorContext, submission: DataLifecyclePolicyUpdate
    ) -> dict[str, Any]:
        del actor, submission
        raise HTTPException(status_code=503, detail="Product persistence is not configured")

    async def create_data_export(
        self, actor: ActorContext, submission: DataExportSubmission, idempotency_key: str
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise HTTPException(status_code=503, detail="Product persistence is not configured")

    async def get_data_export(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        del actor, export_id
        return None

    async def get_data_export_manifest(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        del actor, export_id
        return None

    async def get_data_export_bundle(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        del actor, export_id
        return None

    async def create_data_deletion(
        self, actor: ActorContext, submission: DataDeletionSubmission, idempotency_key: str
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise HTTPException(status_code=503, detail="Product persistence is not configured")

    async def get_data_deletion(
        self, actor: ActorContext, deletion_id: UUID
    ) -> dict[str, Any] | None:
        del actor, deletion_id
        return None

    async def create_deep_research(
        self,
        actor: ActorContext,
        submission: DeepResearchSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def create_monitor(
        self,
        actor: ActorContext,
        submission: MonitorCreateSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def list_monitors(
        self,
        actor: ActorContext,
        *,
        status_filter: MonitorStatusFilter,
    ) -> dict[str, Any]:
        del actor, status_filter
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def list_monitor_triggers(
        self,
        actor: ActorContext,
        monitor_id: str,
        *,
        limit: int,
    ) -> dict[str, Any] | None:
        del actor, monitor_id, limit
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def pause_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, monitor_id, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def resume_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, monitor_id, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def trigger_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, monitor_id, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def disable_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, monitor_id, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        del actor, task_id, run_id
        return None

    async def list_runs(self, actor: ActorContext, *, limit: int) -> dict[str, Any]:
        del actor, limit
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def get_run(
        self,
        actor: ActorContext,
        run_id: str,
    ) -> dict[str, Any] | None:
        del actor, run_id
        return None

    async def list_artifacts(
        self,
        actor: ActorContext,
        *,
        limit: int,
    ) -> dict[str, Any]:
        del actor, limit
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def get_home(self, actor: ActorContext) -> dict[str, Any]:
        del actor
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def set_watchlist_symbol(
        self,
        actor: ActorContext,
        symbol: str,
        *,
        included: bool,
    ) -> dict[str, Any]:
        del actor, symbol, included
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def list_inbox(
        self,
        actor: ActorContext,
        *,
        status: InboxQueryStatus,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        del actor, status, limit, cursor
        raise HTTPException(
            status_code=503,
            detail="Product persistence is not configured",
        )

    async def respond_inbox_review(
        self,
        actor: ActorContext,
        pause_id: UUID,
        submission: InboxReviewSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, pause_id, submission, idempotency_key
        raise HTTPException(
            status_code=503,
            detail="Product persistence is not configured",
        )

    async def list_notifications(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> dict[str, Any] | None:
        del actor, task_id
        raise HTTPException(
            status_code=503,
            detail="Product persistence is not configured",
        )

    async def request_notification_resend(
        self,
        actor: ActorContext,
        notification_id: str,
        submission: NotificationResendSubmission,
    ) -> dict[str, Any] | None:
        del actor, notification_id, submission
        raise HTTPException(
            status_code=503,
            detail="Product persistence is not configured",
        )

    async def get_notification_settings(
        self,
        actor: ActorContext,
    ) -> dict[str, Any]:
        del actor
        raise HTTPException(
            status_code=503,
            detail="Product persistence is not configured",
        )

    async def update_notification_settings(
        self,
        actor: ActorContext,
        submission: NotificationSettingsUpdate,
    ) -> dict[str, Any]:
        del actor, submission
        raise HTTPException(
            status_code=503,
            detail="Product persistence is not configured",
        )

    async def cancel_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def retry_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def fork_task(
        self,
        actor: ActorContext,
        task_id: str,
        submission: ForkSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def respond_interrupt(
        self,
        actor: ActorContext,
        task_id: str,
        interrupt_id: str,
        submission: InterruptResponseSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, interrupt_id, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )

    async def respond_interrupts(
        self,
        actor: ActorContext,
        task_id: str,
        submission: InterruptResponsesSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del actor, task_id, submission, idempotency_key
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product persistence is not configured",
        )


async def _actor_for_request(
    request: Request,
    *,
    mode: str,
    token_verifier: TokenVerifier | None,
    development_actor: ActorContext | None,
    membership_authority: MembershipAuthority | None,
) -> ActorContext:
    if development_actor is not None:
        try:
            return resolve_actor_context(
                mode=mode,
                authenticated_claims=None,
                untrusted_payload={},
                host=request.headers.get("host", ""),
                origin=request.headers.get("origin"),
                peer_host=request.client.host if request.client is not None else "",
                development_actor=development_actor,
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
    try:
        if token_verifier is None:
            raise PermissionError("internal authorization is not configured")
        claims = token_verifier.verify_authorization(
            request.headers.get("authorization")
        )
        if claims.get("token_use") != "user":
            raise PermissionError("scoped user token is required")
        identity = _identity_from_claims(claims)
        context_id = UUID(str(claims["context_id"]))
    except (KeyError, PermissionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "resource_token_invalid",
                "message": "A valid scoped resource token is required.",
            },
        ) from exc
    if membership_authority is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "authorization_unavailable",
                "message": "Authorization is temporarily unavailable.",
            },
        )
    try:
        return await membership_authority.authorize(
            identity,
            context_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": AUTH_CONTEXT_NOT_FOUND,
                "message": "The authorization context is unavailable.",
            },
        ) from exc


def _identity_for_request(
    request: Request,
    *,
    token_verifier: TokenVerifier | None,
) -> AuthenticatedIdentity:
    try:
        if token_verifier is None:
            raise PermissionError("identity verification is not configured")
        claims = token_verifier.verify_authorization(
            request.headers.get("authorization")
        )
        if claims.get("token_use") != "identity_discovery":
            raise PermissionError("identity discovery token is required")
        return _identity_from_claims(claims)
    except (KeyError, PermissionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "identity_token_invalid",
                "message": "A valid identity discovery token is required.",
            },
        ) from exc


def _identity_from_claims(claims: Mapping[str, Any]) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        issuer=str(claims["identity_issuer"]),
        subject=str(claims["sub"]),
    )


async def _require_http_readiness(url: str, *, unavailable_detail: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=2.0, follow_redirects=False) as client:
            response = await client.get(url)
            response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=unavailable_detail,
        ) from exc


def _auth_context_view(context: MembershipContext) -> dict[str, Any]:
    return {
        "context_id": context.context_id,
        "tenant_id": context.tenant_id,
        "tenant_name": context.tenant_name,
        "workspace_id": context.workspace_id,
        "workspace_name": context.workspace_name,
        "role": context.role,
        "permissions": list(context.permissions),
        "version": context.version,
    }


def _lifecycle_http_error(exc: LifecycleError) -> HTTPException:
    conflict_codes = {"idempotency_conflict", "manifest_tampered", "bundle_tampered"}
    return HTTPException(
        status_code=409 if exc.code in conflict_codes else 422,
        detail={"code": exc.code, "message": str(exc)},
    )


def create_app(
    *,
    service: ProductService,
    mode: str,
    token_verifier: TokenVerifier | None = None,
    identity_token_verifier: TokenVerifier | None = None,
    membership_authority: MembershipAuthority | None = None,
    settings: Settings | None = None,
    failure_injection: FailureInjectionController | None = None,
    failure_injection_control_token: str | None = None,
) -> FastAPI:
    normalized_mode = mode.strip().lower()
    if (
        settings is not None
        and normalized_mode != settings.app_environment.strip().lower()
    ):
        raise ValueError("mode must match settings.app_environment")
    if normalized_mode in {"staging", "production"} and token_verifier is None:
        raise ValueError("token_verifier is required in staging and production")
    if normalized_mode in {"staging", "production"} and (
        identity_token_verifier is None or membership_authority is None
    ):
        raise ValueError(
            "identity_token_verifier and membership_authority are required "
            "in staging and production"
        )
    if failure_injection is not None and normalized_mode not in {
        "development",
        "local",
        "test",
    }:
        raise ValueError(
            "failure injection routes are allowed only in non-production local profiles"
        )
    development_actor = (
        configured_development_actor(settings) if settings is not None else None
    )
    product = FastAPI(title="Crypto Manual Alert V2 Product API", version="2.0.0")
    product.middleware("http")(request_identity_middleware)

    @product.exception_handler(PermissionError)
    async def permission_denied(_: Request, __: PermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": {
                    "code": "permission_required",
                    "message": "The requested operation is not permitted.",
                }
            },
        )

    @product.get("/api/v2/health", response_model=HealthView)
    async def health() -> HealthView:
        return HealthView()

    @product.get("/api/v2/readiness", response_model=HealthView)
    async def readiness() -> HealthView:
        agent_url = getattr(settings, "agent_readiness_url", None) if settings else None
        worker_url = (
            getattr(settings, "worker_readiness_url", None) if settings else None
        )
        if normalized_mode in {"staging", "production"} and not agent_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent readiness URL is not configured.",
            )
        if normalized_mode in {"staging", "production"} and not worker_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Worker readiness URL is not configured.",
            )
        database_check = getattr(service, "check_database", None)
        if normalized_mode in {"staging", "production"} and not callable(
            database_check
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Product database readiness is not configured.",
            )
        if callable(database_check):
            try:
                await database_check()
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Product database is not ready.",
                ) from exc
        if agent_url:
            await _require_http_readiness(
                agent_url,
                unavailable_detail="Agent Server is not ready.",
            )
        if worker_url:
            await _require_http_readiness(
                worker_url,
                unavailable_detail="Durable worker is not ready.",
            )
        return HealthView()

    if failure_injection is not None:

        async def failure_injection_actor(request: Request) -> ActorContext:
            provided_token = request.headers.get(
                "X-Failure-Injection-Control-Token", ""
            )
            if not failure_injection_control_token or not hmac.compare_digest(
                provided_token, failure_injection_control_token
            ):
                raise PermissionError("failure injection control token is required")
            actor = await _actor_for_request(
                request,
                mode=mode,
                token_verifier=token_verifier,
                development_actor=development_actor,
                membership_authority=membership_authority,
            )
            if "failure_injection:write" not in actor.permissions:
                raise PermissionError("failure_injection:write permission is required")
            return actor

        @product.get(
            "/api/v2/testing/failure-scenario",
            include_in_schema=False,
        )
        async def get_failure_scenario(request: Request) -> dict[str, Any]:
            await failure_injection_actor(request)
            snapshot = await asyncio.to_thread(failure_injection.snapshot)
            return snapshot.model_dump(mode="json")

        @product.put(
            "/api/v2/testing/failure-scenario",
            include_in_schema=False,
        )
        async def set_failure_scenario(
            submission: FailureScenarioUpdate,
            request: Request,
        ) -> dict[str, Any]:
            await failure_injection_actor(request)
            try:
                snapshot = await asyncio.to_thread(
                    failure_injection.set,
                    submission.scenario,
                    expected_generation=submission.expected_generation,
                )
                return snapshot.model_dump(mode="json")
            except FailureInjectionConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @product.delete(
            "/api/v2/testing/failure-scenario",
            include_in_schema=False,
        )
        async def reset_failure_scenario(
            request: Request,
            generation: Annotated[str, Header(alias="X-Failure-Injection-Generation")],
        ) -> dict[str, Any]:
            await failure_injection_actor(request)
            try:
                snapshot = await asyncio.to_thread(
                    failure_injection.reset,
                    expected_generation=generation,
                )
                return snapshot.model_dump(mode="json")
            except FailureInjectionConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    @product.get(
        "/api/v2/auth/contexts",
        response_model=AuthContextListView,
    )
    async def list_auth_contexts(request: Request) -> dict[str, Any]:
        if development_actor is not None:
            actor = await _actor_for_request(
                request,
                mode=mode,
                token_verifier=token_verifier,
                development_actor=development_actor,
                membership_authority=membership_authority,
            )
            identity = AuthenticatedIdentity(
                issuer=actor.identity_issuer,
                subject=actor.user_id,
            )
        else:
            identity = _identity_for_request(
                request,
                token_verifier=identity_token_verifier,
            )
        if membership_authority is None:
            raise HTTPException(status_code=503, detail="Authorization unavailable")
        contexts = await membership_authority.discover(identity)
        return {"items": [_auth_context_view(context) for context in contexts]}

    @product.post(
        "/api/v2/auth/context/select",
        response_model=AuthContextView,
    )
    async def select_auth_context(
        submission: AuthContextSelection,
        request: Request,
    ) -> dict[str, Any]:
        if development_actor is not None:
            actor = await _actor_for_request(
                request,
                mode=mode,
                token_verifier=token_verifier,
                development_actor=development_actor,
                membership_authority=membership_authority,
            )
            identity = AuthenticatedIdentity(
                issuer=actor.identity_issuer,
                subject=actor.user_id,
            )
        else:
            identity = _identity_for_request(
                request,
                token_verifier=identity_token_verifier,
            )
        if membership_authority is None:
            raise HTTPException(status_code=503, detail="Authorization unavailable")
        try:
            _, context = await membership_authority.select(
                identity,
                submission.context_id,
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": AUTH_CONTEXT_NOT_FOUND,
                    "message": "The selected authorization context is unavailable.",
                },
            ) from exc
        return _auth_context_view(context)

    @product.post(
        "/api/v2/analysis",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_analysis(
        submission: AnalysisSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.create_analysis(actor, submission, idempotency_key)
        except IdempotencyConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @product.get("/api/v2/monitors", response_model=MonitorListView)
    async def list_monitors(
        request: Request,
        status_filter: MonitorStatusFilter = Query(default="running", alias="status"),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        return await service.list_monitors(actor, status_filter=status_filter)

    @product.post(
        "/api/v2/monitors",
        response_model=MonitorView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_monitor(
        submission: MonitorCreateSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.create_monitor(actor, submission, idempotency_key)
        except MonitorConditionEvaluatorUnavailableError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": str(exc),
                    "condition": exc.condition_kind,
                },
            ) from exc
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MonitorEntitlementError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except MonitorSourceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @product.get(
        "/api/v2/monitors/{monitor_id}/triggers",
        response_model=MonitorTriggerListView,
    )
    async def list_monitor_triggers(
        monitor_id: str,
        request: Request,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        result = await service.list_monitor_triggers(actor, monitor_id, limit=limit)
        if result is None:
            raise HTTPException(status_code=404, detail="Monitor not found")
        return result

    async def _mutate_monitor(
        operation: str,
        monitor_id: str,
        submission: MonitorMutationSubmission | None,
        request: Request,
        idempotency_key: str,
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            if operation == "pause":
                assert submission is not None
                result = await service.pause_monitor(
                    actor, monitor_id, submission, idempotency_key
                )
            elif operation == "resume":
                assert submission is not None
                result = await service.resume_monitor(
                    actor, monitor_id, submission, idempotency_key
                )
            elif operation == "disable":
                assert submission is not None
                result = await service.disable_monitor(
                    actor, monitor_id, submission, idempotency_key
                )
            else:
                result = await service.trigger_monitor(
                    actor, monitor_id, idempotency_key
                )
        except (IdempotencyConflictError, MonitorConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MonitorConditionEvaluatorUnavailableError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": str(exc),
                    "condition": exc.condition_kind,
                },
            ) from exc
        except MonitorEntitlementError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Monitor not found")
        return result

    @product.post(
        "/api/v2/monitors/{monitor_id}/pause",
        response_model=MonitorView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def pause_monitor(
        monitor_id: str,
        submission: MonitorMutationSubmission,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, Any]:
        return await _mutate_monitor(
            "pause", monitor_id, submission, request, idempotency_key
        )

    @product.post(
        "/api/v2/monitors/{monitor_id}/resume",
        response_model=MonitorView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def resume_monitor(
        monitor_id: str,
        submission: MonitorMutationSubmission,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, Any]:
        return await _mutate_monitor(
            "resume", monitor_id, submission, request, idempotency_key
        )

    @product.post(
        "/api/v2/monitors/{monitor_id}/trigger",
        response_model=MonitorView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_monitor(
        monitor_id: str,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, Any]:
        return await _mutate_monitor(
            "trigger", monitor_id, None, request, idempotency_key
        )

    @product.delete(
        "/api/v2/monitors/{monitor_id}",
        response_model=MonitorView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def disable_monitor(
        monitor_id: str,
        submission: MonitorMutationSubmission,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, Any]:
        return await _mutate_monitor(
            "disable", monitor_id, submission, request, idempotency_key
        )

    @product.post(
        "/api/v2/deep-research",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_deep_research(
        submission: DeepResearchSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.create_deep_research(
                actor,
                submission,
                idempotency_key,
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @product.get("/api/v2/tasks/{task_id}", response_model=TaskView)
    async def get_task(
        task_id: str,
        request: Request,
        run_id: UUID | None = Query(default=None),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        task = await service.get_task(actor, task_id, run_id=run_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @product.post(
        "/api/v2/runs/{run_id}/cancel",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def cancel_run(
        run_id: str,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            task = await service.cancel_run(actor, run_id, idempotency_key)
        except RunNotCancellableError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return task

    @product.get("/api/v2/runs", response_model=RunListView)
    async def list_runs(
        request: Request,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        return await service.list_runs(actor, limit=limit)

    @product.get("/api/v2/home", response_model=HomeView)
    async def get_home(request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        return await service.get_home(actor)

    @product.put("/api/v2/watchlist/{symbol}", response_model=HomeView)
    async def add_watchlist_symbol(symbol: str, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.set_watchlist_symbol(actor, symbol, included=True)
        except WatchlistSymbolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @product.delete("/api/v2/watchlist/{symbol}", response_model=HomeView)
    async def remove_watchlist_symbol(symbol: str, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.set_watchlist_symbol(actor, symbol, included=False)
        except WatchlistSymbolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @product.get("/api/v2/runs/{run_id}", response_model=RunDetailView)
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        run = await service.get_run(actor, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @product.post(
        "/api/v2/runs/{run_id}/feedback",
        response_model=FeedbackView,
        status_code=status.HTTP_201_CREATED,
    )
    async def submit_feedback(
        run_id: str,
        submission: FeedbackSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            feedback = await service.submit_feedback(
                actor,
                run_id,
                submission,
                idempotency_key,
            )
        except FeedbackConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if feedback is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return feedback

    @product.get("/api/v2/artifacts", response_model=ArtifactLibraryView)
    async def list_artifacts(
        request: Request,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        return await service.list_artifacts(actor, limit=limit)

    @product.get("/api/v2/artifacts/{artifact_id}", response_model=ArtifactDetailView)
    async def get_artifact(
        artifact_id: str,
        request: Request,
        version_number: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        artifact = await service.get_artifact(
            actor,
            artifact_id,
            version_number=version_number,
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    @product.get("/api/v2/inbox", response_model=InboxView)
    async def list_inbox(
        request: Request,
        inbox_status: InboxQueryStatus = Query(default="active", alias="status"),
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, min_length=1, max_length=2048),
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.list_inbox(
                actor,
                status=inbox_status,
                limit=limit,
                cursor=cursor,
            )
        except InvalidInboxCursorError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @product.post(
        "/api/v2/inbox/{pause_id}/respond",
        response_model=InboxReviewReceiptView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def respond_inbox_review(
        pause_id: UUID,
        submission: InboxReviewSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            receipt = await service.respond_inbox_review(
                actor,
                pause_id,
                submission,
                idempotency_key,
            )
        except (IdempotencyConflictError, InterruptResponseConflictError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        if receipt is None:
            raise HTTPException(status_code=404, detail="Inbox review not found")
        return receipt

    @product.get(
        "/api/v2/tasks/{task_id}/notifications",
        response_model=NotificationListView,
    )
    async def list_notifications(
        task_id: str,
        request: Request,
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        notifications = await service.list_notifications(actor, task_id)
        if notifications is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return notifications

    @product.post(
        "/api/v2/notifications/{notification_id}/resend",
        response_model=NotificationView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def request_notification_resend(
        notification_id: str,
        submission: NotificationResendSubmission,
        request: Request,
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            notification = await service.request_notification_resend(
                actor,
                notification_id,
                submission,
            )
        except (NotificationNotResendable, NotificationRetryBudgetExhausted) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if notification is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        return notification

    @product.get(
        "/api/v2/settings/notifications",
        response_model=NotificationSettingsView,
    )
    async def get_notification_settings(request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        return await service.get_notification_settings(actor)

    @product.patch(
        "/api/v2/settings/notifications",
        response_model=NotificationSettingsView,
    )
    async def update_notification_settings(
        submission: NotificationSettingsUpdate,
        request: Request,
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.update_notification_settings(actor, submission)
        except NotificationSettingsConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except NotificationSettingsUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @product.post(
        "/api/v2/tasks/{task_id}/cancel",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def cancel_task(
        task_id: str,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            task = await service.cancel_task(actor, task_id, idempotency_key)
        except TaskNotCancellableError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @product.post(
        "/api/v2/tasks/{task_id}/retry",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def retry_task(
        task_id: str,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            task = await service.retry_task(actor, task_id, idempotency_key)
        except TaskNotRetryableError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @product.post(
        "/api/v2/tasks/{task_id}/fork",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def fork_task(
        task_id: str,
        submission: ForkSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            task = await service.fork_task(
                actor,
                task_id,
                submission,
                idempotency_key,
            )
        except (ForkConflictError, IdempotencyConflictError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task or source Run not found")
        return task

    @product.post(
        "/api/v2/tasks/{task_id}/interrupts/respond-all",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def respond_interrupts(
        task_id: str,
        submission: InterruptResponsesSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            task = await service.respond_interrupts(
                actor,
                task_id,
                submission,
                idempotency_key,
            )
        except (IdempotencyConflictError, InterruptResponseConflictError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task or pause not found")
        return task

    @product.post(
        "/api/v2/tasks/{task_id}/interrupts/{interrupt_id}/respond",
        response_model=TaskView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def respond_interrupt(
        task_id: str,
        interrupt_id: str,
        submission: InterruptResponseSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            task = await service.respond_interrupt(
                actor,
                task_id,
                interrupt_id,
                submission,
                idempotency_key,
            )
        except (IdempotencyConflictError, InterruptResponseConflictError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Task or interrupt not found")
        return task

    @product.get(
        "/api/v2/data-lifecycle/policy",
        response_model=DataLifecyclePolicyView,
    )
    async def get_data_lifecycle_policy(request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        return await service.get_data_lifecycle_policy(actor)

    @product.put(
        "/api/v2/data-lifecycle/policy",
        response_model=DataLifecyclePolicyView,
    )
    async def update_data_lifecycle_policy(
        submission: DataLifecyclePolicyUpdate,
        request: Request,
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.update_data_lifecycle_policy(actor, submission)
        except LifecycleError as exc:
            raise _lifecycle_http_error(exc) from exc

    @product.post(
        "/api/v2/data-lifecycle/exports",
        response_model=DataExportView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_data_export(
        submission: DataExportSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.create_data_export(actor, submission, idempotency_key)
        except LifecycleError as exc:
            raise _lifecycle_http_error(exc) from exc

    @product.get(
        "/api/v2/data-lifecycle/exports/{export_id}",
        response_model=DataExportView,
    )
    async def get_data_export(export_id: UUID, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        result = await service.get_data_export(actor, export_id)
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "data_export_not_found", "message": "Data export not found"})
        return result

    @product.get(
        "/api/v2/data-lifecycle/exports/{export_id}/manifest",
        response_model=DataExportManifestView,
    )
    async def get_data_export_manifest(export_id: UUID, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            result = await service.get_data_export_manifest(actor, export_id)
        except LifecycleError as exc:
            raise _lifecycle_http_error(exc) from exc
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "data_export_not_found", "message": "Data export not found"})
        return result

    @product.get(
        "/api/v2/data-lifecycle/exports/{export_id}/bundle",
        response_model=DataExportBundleView,
    )
    async def get_data_export_bundle(export_id: UUID, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            result = await service.get_data_export_bundle(actor, export_id)
        except LifecycleError as exc:
            raise _lifecycle_http_error(exc) from exc
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "data_export_not_found", "message": "Data export not found"})
        return result

    @product.post(
        "/api/v2/data-lifecycle/deletions",
        response_model=DataDeletionView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_data_deletion(
        submission: DataDeletionSubmission,
        request: Request,
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                pattern=IDEMPOTENCY_KEY_PATTERN,
            ),
        ],
    ) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        try:
            return await service.create_data_deletion(actor, submission, idempotency_key)
        except LifecycleError as exc:
            raise _lifecycle_http_error(exc) from exc

    @product.get(
        "/api/v2/data-lifecycle/deletions/{deletion_id}",
        response_model=DataDeletionView,
    )
    async def get_data_deletion(deletion_id: UUID, request: Request) -> dict[str, Any]:
        actor = await _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
            membership_authority=membership_authority,
        )
        result = await service.get_data_deletion(actor, deletion_id)
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "data_deletion_not_found", "message": "Data deletion not found"})
        return result

    return product


def create_default_app(*, token_audience: str | None = None) -> FastAPI:
    settings = get_settings()
    failure_injection = failure_injection_from_settings(settings)
    notification_credential_cipher = notification_credential_cipher_from_environment()
    if (
        settings.app_environment in {"staging", "production"}
        and notification_credential_cipher is None
    ):
        raise ValueError(
            "NOTIFICATION_CREDENTIAL_KEY is required in staging and production"
        )
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(
        session_factory=session_factory,
        inbox_cursor_key=_configured_inbox_cursor_key(settings),
        notification_credential_cipher=notification_credential_cipher,
    )
    mode = settings.app_environment
    development_actor = configured_development_actor(settings)
    internal_jwt_public_keys = getattr(settings, "internal_jwt_public_keys", {})
    token_verifier = None
    identity_token_verifier = None
    membership_authority = DatabaseMembershipAuthority(session_factory=session_factory)
    if development_actor is None and (
        internal_jwt_public_keys or mode.strip().lower() in {"staging", "production"}
    ):
        token_verifier = InternalTokenVerifier(
            public_keys=internal_jwt_public_keys,
            issuer=settings.internal_jwt_issuer,
            audience=(
                token_audience
                if token_audience is not None
                else settings.internal_jwt_audience
            ),
            max_ttl_seconds=settings.internal_jwt_max_ttl_seconds,
        )
        identity_token_verifier = InternalTokenVerifier(
            public_keys=internal_jwt_public_keys,
            issuer=settings.internal_jwt_issuer,
            audience=IDENTITY_DISCOVERY_AUDIENCE,
            max_ttl_seconds=settings.internal_jwt_max_ttl_seconds,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if development_actor is not None:
            await service.bootstrap_actor(development_actor)
        yield
        await engine.dispose()

    failure_injection_control_token = getattr(
        settings, "failure_injection_control_token", None
    )
    product = create_app(
        service=service,
        mode=mode,
        token_verifier=token_verifier,
        identity_token_verifier=identity_token_verifier,
        membership_authority=membership_authority,
        settings=settings,
        failure_injection=failure_injection,
        failure_injection_control_token=(
            failure_injection_control_token.get_secret_value()
            if failure_injection_control_token is not None
            else None
        ),
    )
    product.router.lifespan_context = lifespan
    product.state.product_service = service
    product.state.failure_injection = failure_injection
    return product


def _configured_inbox_cursor_key(settings: Settings) -> bytes | None:
    configured_key = getattr(settings, "product_inbox_cursor_key", None)
    if configured_key is not None:
        value = configured_key.get_secret_value().strip()
        if value:
            try:
                encoded = value.encode("ascii")
                key_material = b64decode(
                    encoded + (b"=" * (-len(encoded) % 4)),
                    altchars=b"-_",
                    validate=True,
                )
            except (BinasciiError, UnicodeEncodeError):
                raise ValueError(
                    "Product Inbox cursor key must be URL-safe Base64"
                ) from None
            if len(key_material) < 32:
                raise ValueError(
                    "Product Inbox cursor key must decode to at least 32 bytes"
                )
            return sha256(
                b"crypto-alert-v2:product-inbox-cursor:configured-key\0" + key_material
            ).digest()
    if settings.app_environment in {"staging", "production"}:
        raise ValueError(
            "A server-side secret is required for stable Product Inbox cursors"
        )
    return None


app = create_default_app()
