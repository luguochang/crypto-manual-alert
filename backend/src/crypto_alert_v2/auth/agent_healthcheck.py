import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
from langgraph_sdk import get_client
from pydantic import ValidationError

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.config import Settings, get_settings
from crypto_alert_v2.providers.capability_probe import SearchReadiness


ReadinessFetcher = Callable[..., Awaitable[Mapping[str, Any]]]


def validate_search_readiness_payload(payload: object) -> SearchReadiness:
    try:
        readiness = SearchReadiness.model_validate(payload)
    except (ValidationError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Agent Server returned invalid or unsanitized search readiness"
        ) from exc
    if readiness.status != "ready":
        raise RuntimeError(
            "Agent Server returned invalid or unsanitized search readiness"
        )
    return readiness


async def _fetch_search_readiness(
    *,
    url: str,
    headers: Mapping[str, str],
) -> Mapping[str, Any]:
    async with httpx.AsyncClient(
        timeout=5.0,
        follow_redirects=False,
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, Mapping):
        raise RuntimeError("Agent Server search readiness response must be an object")
    return payload


async def check_agent_server(
    settings: Settings,
    *,
    client_factory: Callable[..., Any] = get_client,
    readiness_fetcher: ReadinessFetcher = _fetch_search_readiness,
) -> None:
    if settings.app_environment.strip().lower() != "production":
        raise RuntimeError("Agent Server healthcheck requires production mode")
    if not all(
        (
            settings.agent_healthcheck_subject,
            settings.agent_healthcheck_tenant_id,
            settings.agent_healthcheck_workspace_id,
            settings.agent_healthcheck_roles,
            settings.agent_healthcheck_permissions,
        )
    ):
        raise RuntimeError("Agent Server healthcheck requires an explicit probe principal")
    private_key = settings.internal_jwt_private_key
    key_id = settings.internal_jwt_key_id
    if private_key is None or key_id is None:
        raise RuntimeError("Agent Server healthcheck signing is not configured")
    actor = ActorContext(
        tenant_id=settings.agent_healthcheck_tenant_id,
        workspace_id=settings.agent_healthcheck_workspace_id,
        user_id=settings.agent_healthcheck_subject,
        roles=settings.agent_healthcheck_roles,
        permissions=settings.agent_healthcheck_permissions,
    )
    issuer = InternalTokenIssuer(
        private_key=private_key.get_secret_value(),
        key_id=key_id,
        issuer=settings.internal_jwt_issuer,
        audience=settings.agent_server_internal_jwt_audience,
        ttl_seconds=60,
    )
    token = issuer.issue(
        subject=actor.user_id,
        tenant_id=actor.tenant_id,
        workspace_id=actor.workspace_id,
        roles=actor.roles,
        permissions=actor.permissions,
    )
    headers = {"authorization": f"Bearer {token}"}
    client = client_factory(
        url=settings.agent_server_url,
        api_key=None,
        headers=headers,
    )
    assistants = await client.assistants.search(limit=100)
    if not any(
        assistant.get("graph_id") == settings.agent_assistant_id
        for assistant in assistants
    ):
        raise RuntimeError(f"{settings.agent_assistant_id} is not registered")
    readiness_payload = await readiness_fetcher(
        url=settings.agent_server_url.rstrip("/") + "/app/system/readiness",
        headers=headers,
    )
    validate_search_readiness_payload(readiness_payload)


if __name__ == "__main__":
    asyncio.run(check_agent_server(get_settings()))


__all__ = ["check_agent_server", "validate_search_readiness_payload"]
