from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
import pytest

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.monitors.agent_server_cron import (
    AgentServerCronAdapter,
    MonitorCronDegradedError,
)
from crypto_alert_v2.monitors.models import MonitorCronSpec, MonitorIngressRequest


MONITOR_ID = UUID("11111111-1111-4111-8111-111111111111")
BINDING_ID = UUID("22222222-2222-4222-8222-222222222222")
END_TIME = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


class RecordingCrons:
    def __init__(self) -> None:
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.update_calls: list[tuple[str, dict[str, Any]]] = []
        self.delete_calls: list[tuple[str, dict[str, Any]]] = []
        self.search_result: list[dict[str, Any]] = []

    async def create(self, assistant_id: str, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append((assistant_id, kwargs))
        return {"cron_id": "cron-created"}

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return self.search_result

    async def update(self, cron_id: str, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append((cron_id, kwargs))
        return {"cron_id": cron_id}

    async def delete(self, cron_id: str, **kwargs: Any) -> None:
        self.delete_calls.append((cron_id, kwargs))


class RecordingClient:
    def __init__(self) -> None:
        self.crons = RecordingCrons()


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


def _spec(*, schedule_version: int = 3) -> MonitorCronSpec:
    return MonitorCronSpec(
        monitor_id=MONITOR_ID,
        schedule_version=schedule_version,
        cron_binding_id=BINDING_ID,
        schedule="*/15 * * * *",
        timezone="Asia/Shanghai",
        end_time=END_TIME,
    )


def _stable_references(*, schedule_version: int = 3) -> dict[str, str | int]:
    return {
        "monitor_id": str(MONITOR_ID),
        "schedule_version": schedule_version,
        "cron_binding_id": str(BINDING_ID),
    }


def test_monitor_models_are_strict_and_reject_product_business_payloads() -> None:
    request = MonitorIngressRequest(
        monitor_id=MONITOR_ID,
        schedule_version=3,
        cron_binding_id=BINDING_ID,
    )

    assert request.model_dump(mode="json") == {
        "task_type": "monitor_ingress",
        **_stable_references(),
    }
    with pytest.raises(ValidationError):
        MonitorIngressRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "query": "must stay in Product PostgreSQL",
            }
        )
    with pytest.raises(ValidationError):
        MonitorIngressRequest(
            monitor_id=MONITOR_ID,
            schedule_version="3",  # type: ignore[arg-type]
            cron_binding_id=BINDING_ID,
        )
    with pytest.raises(ValidationError):
        MonitorCronSpec(
            monitor_id=MONITOR_ID,
            schedule_version=3,
            cron_binding_id=BINDING_ID,
            schedule="*/15 * * * *",
            timezone="Not/A_Zone",
            end_time=END_TIME,
        )
    with pytest.raises(ValidationError):
        MonitorCronSpec(
            monitor_id=MONITOR_ID,
            schedule_version=3,
            cron_binding_id=BINDING_ID,
            schedule="*/15 * * * *",
            timezone="UTC",
            end_time=datetime(2026, 8, 1),
        )


@pytest.mark.asyncio
async def test_create_uses_only_stable_references_and_safe_cron_runtime_options() -> (
    None
):
    client = RecordingClient()
    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda actor: f"Bearer token-for-{actor.user_id}",
    )

    result = await adapter.create(_actor(), _spec())

    assert result == {"cron_id": "cron-created"}
    assert client.crons.create_calls == [
        (
            "crypto_analysis",
            {
                "schedule": "*/15 * * * *",
                "input": {
                    "request": {
                        "task_type": "monitor_ingress",
                        **_stable_references(),
                    }
                },
                "metadata": _stable_references(),
                "enabled": False,
                "timezone": "Asia/Shanghai",
                "end_time": END_TIME,
                "stream_mode": ["updates", "custom"],
                "stream_resumable": True,
                "durability": "exit",
                "headers": {"authorization": "Bearer token-for-user-1"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_nonproduction_runtime_compatibility_omits_only_remote_end_time() -> None:
    client = RecordingClient()
    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer actor-token",
        include_end_time=False,
    )

    await adapter.create(_actor(), _spec())
    await adapter.update(_actor(), "cron-local", _spec(), enabled=True)

    create_options = client.crons.create_calls[0][1]
    update_options = client.crons.update_calls[0][1]
    assert "end_time" not in create_options
    assert "end_time" not in update_options
    assert create_options["input"] == {"request": _spec().cron_input()["request"]}
    assert update_options["metadata"] == _stable_references()
    assert update_options["enabled"] is True


@pytest.mark.asyncio
async def test_reconcile_search_is_bounded_and_updates_the_single_binding() -> None:
    client = RecordingClient()
    client.crons.search_result = [
        {
            "cron_id": "cron-existing",
            "metadata": {
                **_stable_references(schedule_version=2),
                "tenant_id": "tenant-1",
                "workspace_id": "workspace-1",
                "user_id": "user-1",
            },
        }
    ]
    actors: list[ActorContext] = []

    def authorization_provider(actor: ActorContext) -> str:
        actors.append(actor)
        return "Bearer actor-token"

    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=authorization_provider,
    )
    actor = _actor()

    result = await adapter.reconcile(actor, _spec())

    assert result == {"cron_id": "cron-existing"}
    assert actors == [actor, actor]
    assert client.crons.search_calls == [
        {
            "metadata": {"cron_binding_id": str(BINDING_ID)},
            "limit": 2,
            "offset": 0,
            "headers": {"authorization": "Bearer actor-token"},
        }
    ]
    assert client.crons.create_calls == []
    assert client.crons.update_calls == [
        (
            "cron-existing",
            {
                "schedule": "*/15 * * * *",
                "input": {
                    "request": {
                        "task_type": "monitor_ingress",
                        **_stable_references(),
                    }
                },
                "metadata": _stable_references(),
                "timezone": "Asia/Shanghai",
                "end_time": END_TIME,
                "stream_mode": ["updates", "custom"],
                "stream_resumable": True,
                "durability": "exit",
                "headers": {"authorization": "Bearer actor-token"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_reconcile_creates_disabled_cron_only_when_binding_is_absent() -> None:
    client = RecordingClient()
    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer actor-token",
    )

    await adapter.reconcile(_actor(), _spec())

    assert len(client.crons.search_calls) == 1
    assert len(client.crons.create_calls) == 1
    assert client.crons.update_calls == []
    assert client.crons.create_calls[0][1]["enabled"] is False


@pytest.mark.asyncio
async def test_duplicate_binding_reports_degraded_without_blind_create_or_update() -> (
    None
):
    client = RecordingClient()
    matching = {
        "cron_id": "cron-1",
        "metadata": _stable_references(),
    }
    client.crons.search_result = [
        matching,
        {**matching, "cron_id": "cron-2"},
    ]
    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer actor-token",
    )

    with pytest.raises(MonitorCronDegradedError) as error:
        await adapter.reconcile(_actor(), _spec())

    assert error.value.status == "degraded"
    assert error.value.match_count == 2
    assert client.crons.create_calls == []
    assert client.crons.update_calls == []


@pytest.mark.asyncio
async def test_conflicting_binding_references_report_degraded() -> None:
    client = RecordingClient()
    client.crons.search_result = [
        {
            "cron_id": "cron-wrong-monitor",
            "metadata": {
                **_stable_references(),
                "monitor_id": "33333333-3333-4333-8333-333333333333",
            },
        }
    ]
    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer actor-token",
    )

    with pytest.raises(MonitorCronDegradedError, match="conflicting stable references"):
        await adapter.reconcile(_actor(), _spec())

    assert client.crons.create_calls == []
    assert client.crons.update_calls == []


@pytest.mark.asyncio
async def test_update_and_delete_forward_actor_authorization() -> None:
    client = RecordingClient()
    adapter = AgentServerCronAdapter(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer actor-token",
    )

    await adapter.update(_actor(), "cron-1", _spec(), enabled=True)
    await adapter.delete(_actor(), "cron-1")

    assert client.crons.update_calls[0][1]["enabled"] is True
    assert client.crons.update_calls[0][1]["headers"] == {
        "authorization": "Bearer actor-token"
    }
    assert client.crons.delete_calls == [
        ("cron-1", {"headers": {"authorization": "Bearer actor-token"}})
    ]
