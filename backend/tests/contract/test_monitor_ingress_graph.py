from uuid import uuid4

import pytest
from pydantic import ValidationError

from crypto_alert_v2.graph.graph import create_graph


def _input() -> dict[str, object]:
    return {
        "request": {
            "task_type": "monitor_ingress",
            "monitor_id": str(uuid4()),
            "schedule_version": 3,
            "cron_binding_id": str(uuid4()),
        }
    }


@pytest.mark.asyncio
async def test_monitor_ingress_uses_canonical_graph_without_provider_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = uuid4()
    official_run_id = uuid4()
    received_identity: dict[str, str | None] = {}

    async def admit(
        _request: object,
        *,
        official_run_id: str,
        official_thread_id: str | None,
    ) -> dict[str, object]:
        received_identity.update(
            run_id=official_run_id,
            thread_id=official_thread_id,
        )
        return {
            "trigger_id": str(uuid4()),
            "monitor_id": str(uuid4()),
            "status": "admitted",
            "reason": None,
            "task_id": str(task_id),
            "created": True,
        }

    monkeypatch.setattr(
        "crypto_alert_v2.graph.monitor_ingress.admit_monitor_ingress",
        admit,
    )
    result = await create_graph().ainvoke(
        _input(),
        config={
            "run_id": official_run_id,
            "configurable": {"thread_id": "official-thread-1"},
        },
    )

    assert result["task_type"] == "monitor_ingress"
    assert result["terminal_status"] == "succeeded"
    assert result["admitted_task_id"] == str(task_id)
    assert received_identity == {
        "run_id": str(official_run_id),
        "thread_id": "official-thread-1",
    }
    assert "market_snapshot" not in result
    assert "artifact" not in result


@pytest.mark.asyncio
async def test_monitor_ingress_rejects_business_payload_smuggling() -> None:
    request = _input()
    request["request"]["query_text"] = "must stay in Product PostgreSQL"  # type: ignore[index]

    with pytest.raises(ValidationError):
        await create_graph().ainvoke(request, config={"run_id": uuid4()})


@pytest.mark.asyncio
async def test_canonical_graph_rejects_unknown_task_type() -> None:
    with pytest.raises(ValueError, match="unsupported task_type"):
        await create_graph().ainvoke(
            {"request": {"task_type": "custom_scheduler"}},
            config={"run_id": uuid4()},
        )
