from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status

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
    if requires_search_readiness(environment):
        runtime = await get_default_runtime_async()
        readiness = runtime.search_readiness
        if readiness is None:
            raise SearchReadinessError(
                f"{environment} Agent Server startup requires search readiness"
            )
        application.state.search_readiness = readiness
    yield


app = FastAPI(
    title="Crypto Manual Alert V2 Agent Extensions",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/app/system/readiness", response_model=SearchReadiness)
async def search_readiness(request: Request) -> SearchReadiness:
    readiness = getattr(request.app.state, "search_readiness", None)
    if not isinstance(readiness, SearchReadiness):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search readiness is not available in this environment.",
        )
    return readiness


__all__ = ["app", "lifespan", "search_readiness"]
