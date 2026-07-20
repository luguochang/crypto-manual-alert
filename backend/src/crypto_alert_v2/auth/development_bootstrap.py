import asyncio
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext, configured_development_actor
from crypto_alert_v2.config import Settings, get_settings


class BootstrapService(Protocol):
    async def bootstrap_actor(self, actor: ActorContext) -> None: ...


def development_actor(settings: Settings) -> ActorContext:
    if (
        settings.app_environment.strip().lower() != "development"
        or not settings.development_bootstrap_enabled
    ):
        raise RuntimeError("development bootstrap is not explicitly enabled")
    if settings.development_bootstrap_profile != "local-proof":
        raise RuntimeError("development bootstrap requires the local-proof profile")
    actor = configured_development_actor(settings)
    if actor is None:
        raise RuntimeError(
            "development bootstrap requires a complete local-proof identity"
        )
    return actor


async def bootstrap_development_membership(
    settings: Settings,
    service: BootstrapService,
) -> None:
    await service.bootstrap_actor(development_actor(settings))


async def run_default(settings: Settings) -> None:
    engine = create_async_engine(
        settings.product_database_url,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(session_factory=session_factory)
    try:
        await bootstrap_development_membership(settings, service)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_default(get_settings()))


__all__ = [
    "bootstrap_development_membership",
    "development_actor",
    "run_default",
]
