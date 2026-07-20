from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import threading
from typing import Any, Iterator

from langchain_core.runnables import RunnableBinding, RunnableLambda
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client
from urllib3.util.retry import Retry

import crypto_alert_v2.observability.callbacks as callbacks_module
from crypto_alert_v2.observability.callbacks import (
    create_observability_config_factory,
)
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.logging import install_sdk_log_redaction
from crypto_alert_v2.observability.redaction import redact_metadata, redact_payload


SYNTHETIC_API_KEY = "lsv2_loopback_test_only"
BUSINESS_SECRET = "business-secret-never-on-the-wire"
EXPECTED_RESULT = {"terminal_status": "succeeded", "artifact": "stable-result"}


@dataclass(frozen=True)
class _ReceivedRequest:
    path: str
    headers: dict[str, str]
    body: bytes
    response_status: int


@dataclass
class _LoopbackState:
    status_code: int = 503
    requests: list[_ReceivedRequest] = field(default_factory=list)
    lock: Any = field(default_factory=threading.Lock)

    def snapshot(self) -> tuple[_ReceivedRequest, ...]:
        with self.lock:
            return tuple(self.requests)


@contextmanager
def _loopback_server() -> Iterator[tuple[str, _LoopbackState]]:
    state = _LoopbackState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _record(self, body: bytes, response_status: int) -> None:
            with state.lock:
                state.requests.append(
                    _ReceivedRequest(
                        path=self.path,
                        headers=dict(self.headers),
                        body=body,
                        response_status=response_status,
                    )
                )

        def do_GET(self) -> None:
            self._record(b"", 500)
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            with state.lock:
                response_status = state.status_code
            self._record(body, response_status)

            response_body = b"loopback unavailable" if response_status == 503 else b""
            self.send_response(response_status)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            if response_body:
                self.wfile.write(response_body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)


def _new_loopback_client(
    api_url: str,
    *,
    hide_io: bool,
    tracing_error_callback: Any,
) -> Client:
    install_sdk_log_redaction()
    return Client(
        api_url=api_url,
        api_key=SYNTHETIC_API_KEY,
        # Use the official adapter configuration to avoid its default backoff. The
        # test has no retry loop of its own and still exercises Client.flush/close.
        retry_config=Retry(total=0),
        timeout_ms=(100, 100),
        auto_batch_tracing=True,
        info={
            "version": "",
            "batch_ingest_config": {
                "use_multipart_endpoint": False,
                "scale_up_qsize_trigger": 1000,
                "scale_up_nthreads_limit": 1,
                "scale_down_nempty_trigger": 4,
                "size_limit": 100,
                "size_limit_bytes": 1_000_000,
            },
        },
        anonymizer=redact_payload,
        hide_inputs=hide_io,
        hide_outputs=hide_io,
        hide_metadata=redact_metadata,
        tracing_error_callback=tracing_error_callback,
        disable_prompt_cache=True,
    )


def test_official_langsmith_loopback_outage_is_fail_open_and_recovers(
    caplog: Any,
) -> None:
    captured_errors: list[Exception] = []
    client: Client | None = None

    def tracing_error_callback(error: Exception) -> None:
        captured_errors.append(error)
        # Exercise the production callback as well as capturing the SDK callback
        # argument for direct, secret-free assertions below.
        callbacks_module._on_langsmith_tracing_error(error)

    with _loopback_server() as (api_url, server_state):

        def langsmith_client_factory(
            _runtime: ObservabilityRuntimeConfig,
            policy: Any,
        ) -> Client:
            nonlocal client
            assert policy.hide_io is True
            if client is None:
                client = _new_loopback_client(
                    api_url,
                    hide_io=policy.hide_io,
                    tracing_error_callback=tracing_error_callback,
                )
            return client

        runtime = ObservabilityRuntimeConfig(
            environment="test",
            release="loopback-test",
            langsmith_enabled=True,
            langsmith_api_key=SYNTHETIC_API_KEY,
            langsmith_project="crypto-alert-v2-loopback",
        )
        factory = create_observability_config_factory(
            runtime,
            langsmith_client_factory=langsmith_client_factory,
        )
        seen_configs: list[dict[str, Any]] = []

        def business(value: str, config: dict[str, Any]) -> dict[str, str]:
            assert value == f"payload:{BUSINESS_SECRET}"
            seen_configs.append(config)
            return EXPECTED_RESULT

        runnable = RunnableBinding(
            bound=RunnableLambda(business, name="loopback-business"),
            config_factories=[factory],
        )

        with caplog.at_level(
            logging.WARNING,
            logger="crypto_alert_v2.observability.delivery",
        ):
            try:
                first_result = runnable.invoke(
                    f"payload:{BUSINESS_SECRET}",
                    config={
                        "metadata": {
                            "tenant_id": "loopback-sensitive-tenant",
                            "sensitive_tenant": True,
                            "correlation_id": "loopback-outage",
                        }
                    },
                )
                assert first_result == EXPECTED_RESULT
                assert client is not None

                first_tracer = next(
                    handler
                    for handler in seen_configs[0]["callbacks"].handlers
                    if isinstance(handler, LangChainTracer)
                )
                assert first_tracer.client is client

                client.flush(timeout=1.0)
                failed_requests = server_state.snapshot()
                assert len(failed_requests) == 1
                assert failed_requests[0].path == "/runs/batch"
                assert failed_requests[0].response_status == 503
                assert failed_requests[0].headers["x-api-key"] == SYNTHETIC_API_KEY
                failed_payload = json.loads(failed_requests[0].body)
                assert failed_payload["post"] or failed_payload["patch"]
                assert BUSINESS_SECRET not in failed_requests[0].body.decode(
                    "utf-8", errors="replace"
                )

                assert len(captured_errors) == 1
                error_text = repr(captured_errors[0])
                assert "LangSmithError" in error_text
                assert BUSINESS_SECRET not in error_text
                assert SYNTHETIC_API_KEY not in error_text
                delivery_logs = [
                    record.getMessage()
                    for record in caplog.records
                    if record.name == "crypto_alert_v2.observability.delivery"
                ]
                failure_log = next(
                    message
                    for message in delivery_logs
                    if '"event":"observability_delivery_failure"' in message
                )
                assert '"provider":"langsmith"' in failure_log
                assert '"stage":"transport"' in failure_log
                assert BUSINESS_SECRET not in failure_log
                assert SYNTHETIC_API_KEY not in failure_log

                server_state.status_code = 204
                second_result = runnable.invoke(
                    f"payload:{BUSINESS_SECRET}",
                    config={
                        "metadata": {
                            "tenant_id": "loopback-sensitive-tenant",
                            "sensitive_tenant": True,
                            "correlation_id": "loopback-recovered",
                        }
                    },
                )
                assert second_result == EXPECTED_RESULT
                client.flush(timeout=1.0)

                recovered_requests = server_state.snapshot()
                assert [request.response_status for request in recovered_requests] == [
                    503,
                    204,
                ]
                assert all(
                    request.path == "/runs/batch" for request in recovered_requests
                )
                assert len(captured_errors) == 1
                assert all(
                    BUSINESS_SECRET
                    not in request.body.decode("utf-8", errors="replace")
                    for request in recovered_requests
                )
            finally:
                if client is not None:
                    client.close(timeout=1.0)
