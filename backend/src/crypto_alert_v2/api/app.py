from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator, Mapping, Protocol
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    HealthView,
    IDEMPOTENCY_KEY_PATTERN,
    RunListView,
    TaskView,
)
from crypto_alert_v2.api.service import (
    IdempotencyConflictError,
    ProductAnalysisService,
)
from crypto_alert_v2.auth.context import (
    ActorContext,
    configured_development_actor,
    resolve_actor_context,
)
from crypto_alert_v2.auth.internal_token import InternalTokenVerifier
from crypto_alert_v2.config import Settings, get_settings


class ProductService(Protocol):
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: AnalysisSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None: ...

    async def list_runs(self, actor: ActorContext, *, limit: int) -> dict[str, Any]: ...


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


def _actor_for_request(
    request: Request,
    *,
    mode: str,
    token_verifier: TokenVerifier | None,
    development_actor: ActorContext | None,
) -> ActorContext:
    normalized_mode = mode.strip().lower()
    try:
        authenticated_claims = None
        if development_actor is None:
            if token_verifier is None:
                raise PermissionError("internal token verification is not configured")
            authenticated_claims = token_verifier.verify_authorization(
                request.headers.get("authorization")
            )
        return resolve_actor_context(
            mode=mode,
            authenticated_claims=authenticated_claims,
            untrusted_payload={},
            host=request.headers.get("host", ""),
            origin=request.headers.get("origin"),
            peer_host=request.client.host if request.client is not None else "",
            development_actor=development_actor,
        )
    except PermissionError as exc:
        status_code = (
            status.HTTP_403_FORBIDDEN
            if normalized_mode == "development" and development_actor is not None
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def create_app(
    *,
    service: ProductService,
    mode: str,
    token_verifier: TokenVerifier | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    normalized_mode = mode.strip().lower()
    if (
        settings is not None
        and normalized_mode != settings.app_environment.strip().lower()
    ):
        raise ValueError("mode must match settings.app_environment")
    if normalized_mode in {"staging", "production"} and token_verifier is None:
        raise ValueError("token_verifier is required in staging and production")
    development_actor = (
        configured_development_actor(settings) if settings is not None else None
    )
    product = FastAPI(title="Crypto Manual Alert V2 Product API", version="2.0.0")

    @product.exception_handler(PermissionError)
    async def permission_denied(_: Request, __: PermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Actor is not provisioned for this workspace."},
        )

    @product.get("/api/v2/health", response_model=HealthView)
    async def health() -> HealthView:
        return HealthView()

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
        actor = _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
        )
        try:
            return await service.create_analysis(actor, submission, idempotency_key)
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
        actor = _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
        )
        task = await service.get_task(actor, task_id, run_id=run_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @product.get("/api/v2/runs", response_model=RunListView)
    async def list_runs(
        request: Request,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        actor = _actor_for_request(
            request,
            mode=mode,
            token_verifier=token_verifier,
            development_actor=development_actor,
        )
        return await service.list_runs(actor, limit=limit)

    return product


def create_default_app() -> FastAPI:
    settings = get_settings()
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(
        session_factory=session_factory,
    )
    mode = settings.app_environment
    development_actor = configured_development_actor(settings)
    internal_jwt_public_keys = getattr(settings, "internal_jwt_public_keys", {})
    token_verifier = None
    if development_actor is None and (
        internal_jwt_public_keys or mode.strip().lower() in {"staging", "production"}
    ):
        token_verifier = InternalTokenVerifier(
            public_keys=internal_jwt_public_keys,
            issuer=settings.internal_jwt_issuer,
            audience=settings.internal_jwt_audience,
            max_ttl_seconds=settings.internal_jwt_max_ttl_seconds,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if development_actor is not None:
            await service.bootstrap_actor(development_actor)
        yield
        await engine.dispose()

    product = create_app(
        service=service,
        mode=mode,
        token_verifier=token_verifier,
        settings=settings,
    )
    product.router.lifespan_context = lifespan
    product.state.product_service = service
    return product


app = create_default_app()
