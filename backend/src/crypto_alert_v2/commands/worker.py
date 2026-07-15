from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Protocol
from uuid import uuid4

from langgraph_sdk import get_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.agent_server import AgentServerRunner
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.commands.dispatcher import CommandDispatcher
from crypto_alert_v2.config import get_settings


logger = logging.getLogger(__name__)


class Dispatcher(Protocol):
    async def dispatch_once(self) -> bool: ...


async def run_worker(
    dispatcher: Dispatcher,
    *,
    once: bool = False,
    poll_interval: float = 0.5,
    stop_event: asyncio.Event | None = None,
) -> None:
    if poll_interval < 0:
        raise ValueError("poll_interval cannot be negative")
    stop = stop_event or asyncio.Event()
    while not stop.is_set():
        try:
            handled = await dispatcher.dispatch_once()
        except Exception:
            if once:
                raise
            logger.exception("Command dispatcher iteration failed")
            handled = False
        if once:
            return
        if handled:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
        except TimeoutError:
            pass


async def _run_default(*, worker_id: str, once: bool, poll_interval: float) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    runner = AgentServerRunner(
        client=get_client(url=settings.agent_server_url),
        assistant_id=settings.agent_assistant_id,
        authorization_provider=_authorization_provider(settings),
    )
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id=worker_id,
    )
    try:
        await run_worker(
            dispatcher,
            once=once,
            poll_interval=poll_interval,
        )
    finally:
        await engine.dispose()


def _authorization_provider(settings: object):
    mode = str(getattr(settings, "app_environment")).strip().lower()
    if mode in {"local", "test", "development"}:
        local_token = getattr(settings, "agent_server_local_token")
        if local_token is None:
            raise RuntimeError("worker local token is not configured")
        secret = local_token.get_secret_value()
        return lambda actor: f"Bearer {secret}"

    private_key_value = getattr(settings, "internal_jwt_private_key")
    key_id = getattr(settings, "internal_jwt_key_id")
    if private_key_value is None or key_id is None:
        raise RuntimeError("worker internal JWT signing is not configured")
    issuer = InternalTokenIssuer(
        private_key=private_key_value.get_secret_value(),
        key_id=key_id,
        issuer=str(getattr(settings, "internal_jwt_issuer")),
        audience=str(getattr(settings, "agent_server_internal_jwt_audience")),
        ttl_seconds=60,
    )

    def issue(actor: ActorContext) -> str:
        token = issuer.issue(
            subject=actor.user_id,
            tenant_id=actor.tenant_id,
            workspace_id=actor.workspace_id,
            roles=actor.roles,
            permissions=actor.permissions,
            token_use="worker",
            identity_issuer=actor.identity_issuer,
            context_id=actor.context_id,
        )
        return f"Bearer {token}"

    return issue


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch durable Product commands")
    parser.add_argument("--worker-id", default=f"worker-{uuid4().hex[:12]}")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(
            _run_default(
                worker_id=args.worker_id,
                once=args.once,
                poll_interval=args.poll_interval,
            )
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()


__all__ = ["main", "run_worker"]
