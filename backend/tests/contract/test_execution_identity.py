from uuid import UUID

from crypto_alert_v2.api.request_identity import (
    REQUEST_ID_HEADER,
    correlation_id_for_task,
    resolve_request_id,
)
from crypto_alert_v2.api.schemas import TaskView


def test_task_id_derives_an_independent_server_owned_stable_correlation() -> None:
    task_id = "22222222-2222-4222-8222-222222222222"
    correlation_id = correlation_id_for_task(task_id)

    assert correlation_id != task_id
    assert UUID(correlation_id).version == 5
    assert correlation_id_for_task(UUID(task_id)) == correlation_id


def test_transport_request_id_accepts_a_bounded_value_or_generates_one() -> None:
    assert REQUEST_ID_HEADER == "X-Request-ID"
    assert resolve_request_id("bff-request-42") == "bff-request-42"

    generated = resolve_request_id("bad request id")
    assert generated != "bad request id"
    assert UUID(generated).version == 4


def test_task_and_safe_errors_override_untrusted_correlation() -> None:
    task_id = "22222222-2222-4222-8222-222222222222"
    view = TaskView.model_validate(
        {
            "task_id": task_id,
            "correlation_id": "client-owned-correlation",
            "status": "failed",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": "2026-07-16T00:00:00Z",
            "errors": [
                {
                    "code": "provider_unavailable",
                    "message": "Market data provider is unavailable.",
                    "retryable": True,
                    "correlation_id": "provider-owned-correlation",
                }
            ],
        }
    )

    correlation_id = correlation_id_for_task(task_id)
    assert view.correlation_id == correlation_id
    assert [error.correlation_id for error in view.errors] == [correlation_id]
