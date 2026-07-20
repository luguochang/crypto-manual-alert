from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from langgraph.stream import CustomTransformer, UpdatesTransformer
from pydantic import ValidationError

from crypto_alert_v2.graph.graph import create_graph
from tests.contract.test_analysis_graph import valid_input, valid_runtime


MODULE_NAME = "crypto_alert_v2.graph.events"


def _events_module() -> Any:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name != MODULE_NAME:
            raise
        raise AssertionError(
            "CAPABILITY GAP [canonical-custom-events]: versioned Product custom "
            "event schemas do not exist"
        ) from exc


def _execution_config() -> dict[str, Any]:
    return {
        "configurable": {"thread_id": "official-thread-event-contract"},
        "metadata": {
            "tenant_id": "tenant-event-contract",
            "workspace_id": "workspace-event-contract",
            "task_id": "task-event-contract",
            "product_run_id": "product-run-event-contract",
            "request_id": "request-event-contract",
            "correlation_id": "correlation-event-contract",
            "operation": "submit",
        },
    }


def _stream_custom_events() -> list[dict[str, Any]]:
    graph = create_graph()
    payload = valid_input()
    payload["request"]["notify"] = True  # type: ignore[index]
    return list(
        graph.stream(
            payload,
            config=_execution_config(),
            context=valid_runtime(),
            stream_mode="custom",
        )
    )


def test_canonical_graph_emits_all_versioned_product_custom_events() -> None:
    events = _events_module()
    raw_events = _stream_custom_events()

    assert raw_events, "canonical Graph emitted no custom events"
    parsed = [events.parse_product_event(item) for item in raw_events]
    names = {item.name for item in parsed}
    assert names == {
        "task_progress",
        "artifact",
        "evidence",
        "usage",
        "notification",
        "quality",
    }

    sequences = [item.sequence for item in parsed]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences))
    assert len({item.event_id for item in parsed}) == len(parsed)
    assert all(len(item.event_id) == 64 for item in parsed)
    assert all(item.schema_version == "1.0" for item in parsed)
    assert all(item.task_id == "task-event-contract" for item in parsed)
    assert all(item.run_id == "product-run-event-contract" for item in parsed)
    assert all(item.thread_id == "official-thread-event-contract" for item in parsed)
    assert all(item.request_id == "request-event-contract" for item in parsed)
    assert all(item.correlation_id == "correlation-event-contract" for item in parsed)

    serialized = json.dumps(raw_events, ensure_ascii=True).lower()
    assert "assess current btc risk and opportunity" not in serialized
    assert "authorization" not in serialized
    assert "api_key" not in serialized
    assert "bearer " not in serialized


def test_custom_event_ids_are_stable_across_replay() -> None:
    _events_module()
    first = _stream_custom_events()
    second = _stream_custom_events()

    assert [(item["name"], item["sequence"], item["event_id"]) for item in first] == [
        (item["name"], item["sequence"], item["event_id"]) for item in second
    ]


def test_custom_event_union_rejects_unknown_names_and_payload_fields() -> None:
    events = _events_module()
    identity = {
        "schema_version": "1.0",
        "event_id": "a" * 64,
        "sequence": 1,
        "correlation_id": "correlation-event-contract",
        "task_id": "task-event-contract",
        "run_id": "product-run-event-contract",
        "thread_id": "official-thread-event-contract",
        "request_id": "request-event-contract",
    }

    with pytest.raises(ValidationError):
        events.parse_product_event(
            {
                **identity,
                "name": "raw_provider_payload",
                "payload": {"secret": "must not pass"},
            }
        )

    with pytest.raises(ValidationError):
        events.parse_product_event(
            {
                **identity,
                "name": "task_progress",
                "phase": "request_validated",
                "status": "active",
                "raw_query": "must not pass",
            }
        )


@pytest.mark.asyncio
async def test_canonical_graph_exposes_custom_events_through_v3_streaming() -> None:
    events = _events_module()
    graph = create_graph()
    with pytest.warns(match="v3 streaming protocol"):
        stream = await graph.astream_events(
            valid_input(),
            config=_execution_config(),
            context=valid_runtime(),
            version="v3",
            transformers=[CustomTransformer, UpdatesTransformer],
        )

    custom_payloads = []
    async for event in stream:
        if event.get("method") == "custom":
            custom_payloads.append(event["params"]["data"])

    assert custom_payloads
    assert {
        events.parse_product_event(payload).name for payload in custom_payloads
    } == {
        "task_progress",
        "artifact",
        "evidence",
        "usage",
        "notification",
        "quality",
    }
