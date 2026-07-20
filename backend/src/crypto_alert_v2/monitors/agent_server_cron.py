from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final
from uuid import UUID

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.monitors.models import MonitorCronSpec


RECONCILE_SEARCH_LIMIT: Final = 2
MONITOR_STREAM_MODES: Final = ("updates", "custom")


class MonitorCronDegradedError(RuntimeError):
    """The binding cannot be reconciled without an operator resolving drift."""

    status = "degraded"

    def __init__(
        self,
        cron_binding_id: UUID,
        *,
        reason: str,
        match_count: int,
    ) -> None:
        self.cron_binding_id = cron_binding_id
        self.reason = reason
        self.match_count = match_count
        super().__init__(
            f"Cron binding {cron_binding_id} is degraded: {reason} "
            f"(bounded match count: {match_count})"
        )


class AgentServerCronAdapter:
    """Actor-scoped adapter over the official LangGraph SDK Cron client."""

    def __init__(
        self,
        *,
        client: Any,
        assistant_id: str,
        authorization_provider: Callable[[ActorContext], str],
        include_end_time: bool = True,
    ) -> None:
        if not assistant_id:
            raise ValueError("assistant_id is required")
        self._client = client
        self._assistant_id = assistant_id
        self._authorization_provider = authorization_provider
        self._include_end_time = include_end_time

    async def create(self, actor: ActorContext, spec: MonitorCronSpec) -> Any:
        options: dict[str, Any] = {
            "schedule": spec.schedule,
            "input": spec.cron_input(),
            "metadata": spec.reference_metadata(),
            "enabled": False,
            "timezone": spec.timezone,
            "stream_mode": list(MONITOR_STREAM_MODES),
            "stream_resumable": True,
            "durability": "exit",
            "headers": self._authorization_headers(actor),
        }
        if self._include_end_time:
            options["end_time"] = spec.end_time
        return await self._client.crons.create(self._assistant_id, **options)

    async def search(
        self,
        actor: ActorContext,
        cron_binding_id: UUID,
    ) -> tuple[Mapping[str, Any], ...]:
        matches = await self._client.crons.search(
            metadata={"cron_binding_id": str(cron_binding_id)},
            limit=RECONCILE_SEARCH_LIMIT,
            offset=0,
            headers=self._authorization_headers(actor),
        )
        return tuple(matches)

    async def update(
        self,
        actor: ActorContext,
        cron_id: str,
        spec: MonitorCronSpec,
        *,
        enabled: bool | None = None,
    ) -> Any:
        if not cron_id:
            raise ValueError("cron_id is required")
        options: dict[str, Any] = {
            "schedule": spec.schedule,
            "input": spec.cron_input(),
            "metadata": spec.reference_metadata(),
            "timezone": spec.timezone,
            "stream_mode": list(MONITOR_STREAM_MODES),
            "stream_resumable": True,
            "durability": "exit",
            "headers": self._authorization_headers(actor),
        }
        if self._include_end_time:
            options["end_time"] = spec.end_time
        if enabled is not None:
            options["enabled"] = enabled
        return await self._client.crons.update(cron_id, **options)

    async def delete(self, actor: ActorContext, cron_id: str) -> None:
        if not cron_id:
            raise ValueError("cron_id is required")
        await self._client.crons.delete(
            cron_id,
            headers=self._authorization_headers(actor),
        )

    async def reconcile(self, actor: ActorContext, spec: MonitorCronSpec) -> Any:
        matches = await self.search(actor, spec.cron_binding_id)
        if len(matches) > 1:
            raise MonitorCronDegradedError(
                spec.cron_binding_id,
                reason="multiple Agent Server Crons share one binding",
                match_count=len(matches),
            )
        if not matches:
            return await self.create(actor, spec)

        match = matches[0]
        self._require_matching_references(match, spec)
        cron_id = match.get("cron_id")
        if not isinstance(cron_id, (str, UUID)) or not str(cron_id):
            raise MonitorCronDegradedError(
                spec.cron_binding_id,
                reason="the matched Agent Server Cron has no usable cron_id",
                match_count=1,
            )
        return await self.update(actor, str(cron_id), spec)

    def _authorization_headers(self, actor: ActorContext) -> dict[str, str]:
        authorization = self._authorization_provider(actor)
        if not isinstance(authorization, str) or not authorization.strip():
            raise ValueError("authorization provider returned no credential")
        return {"authorization": authorization}

    @staticmethod
    def _require_matching_references(
        match: Mapping[str, Any],
        spec: MonitorCronSpec,
    ) -> None:
        metadata = match.get("metadata")
        expected_binding_id = str(spec.cron_binding_id)
        expected_monitor_id = str(spec.monitor_id)
        if not isinstance(metadata, Mapping) or (
            metadata.get("cron_binding_id") != expected_binding_id
            or metadata.get("monitor_id") != expected_monitor_id
        ):
            raise MonitorCronDegradedError(
                spec.cron_binding_id,
                reason="the matched Cron has conflicting stable references",
                match_count=1,
            )


__all__ = [
    "AgentServerCronAdapter",
    "MONITOR_STREAM_MODES",
    "MonitorCronDegradedError",
    "RECONCILE_SEARCH_LIMIT",
]
