from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status

from crypto_alert_v2.api.app import create_default_app as create_default_product_app
from crypto_alert_v2.config import get_settings, requires_search_readiness
from crypto_alert_v2.graph.runtime import get_default_runtime_async
from crypto_alert_v2.providers.capability_probe import (
    SearchReadiness,
    SearchReadinessError,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    environment = settings.app_environment
    application.state.search_readiness = None
    async with AsyncExitStack() as stack:
        product_app = getattr(application.state, "product_app", None)
        if isinstance(product_app, FastAPI):
            await stack.enter_async_context(
                product_app.router.lifespan_context(product_app)
            )
        if requires_search_readiness(environment):
            runtime = await get_default_runtime_async()
            readiness = runtime.search_readiness
            if readiness is None:
                raise SearchReadinessError(
                    f"{environment} Agent Server startup requires search readiness"
                )
            application.state.search_readiness = readiness
        yield


async def search_readiness(request: Request) -> SearchReadiness:
    readiness = getattr(request.app.state, "search_readiness", None)
    if not isinstance(readiness, SearchReadiness):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search readiness is not available in this environment.",
        )
    return readiness


def create_app(*, product_app: FastAPI | None = None) -> FastAPI:
    if product_app is None:
        settings = get_settings()
        product_app = create_default_product_app(
            token_audience=settings.agent_server_internal_jwt_audience
        )
    application = FastAPI(
        title="Crypto Manual Alert V2 Agent Extensions",
        version="2.0.0",
        lifespan=lifespan,
    )
    application.add_api_route(
        "/app/system/readiness",
        search_readiness,
        methods=["GET"],
        response_model=SearchReadiness,
    )
    application.state.product_app = product_app
    application.mount("/app", product_app)
    return application


app = create_app()


__all__ = ["app", "create_app", "lifespan", "search_readiness"]
