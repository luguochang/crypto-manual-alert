from __future__ import annotations

from typing import Any
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
FAKE_PUBLIC_KEY = "pk-lf-transport-test-only-canary"
FAKE_SECRET_KEY = "sk-lf-transport-test-only-canary"
RESPONSE_SECRET = "transport-response-secret-canary"
_RESULT_PREFIX = "LANGFUSE_TRANSPORT_PROBE="

_PROBE = textwrap.dedent(
    f"""
    from __future__ import annotations

    from http.server import BaseHTTPRequestHandler, HTTPServer
    import json
    import logging
    from threading import Thread
    from time import monotonic, sleep
    from typing import Any

    from langchain_core.runnables import RunnableBinding, RunnableLambda
    from langfuse.langchain import CallbackHandler
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    from crypto_alert_v2.observability.callbacks import (
        create_observability_config_factory,
        initialize_langfuse_client,
    )
    from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig


    records: list[dict[str, str]] = []
    requests: list[dict[str, Any]] = []
    mode = {{"value": "outage"}}
    expected_authorization = "Basic " + __import__("base64").b64encode(
        b"{FAKE_PUBLIC_KEY}:{FAKE_SECRET_KEY}"
    ).decode("ascii")


    class LogCollector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(
                {{
                    "logger": record.name,
                    "level": record.levelname,
                    "message": record.getMessage(),
                }}
            )


    class LoopbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            export = ExportTraceServiceRequest()
            export.ParseFromString(body)
            spans = [
                span
                for resource in export.resource_spans
                for scope in resource.scope_spans
                for span in scope.spans
            ]
            requests.append(
                {{
                    "mode": mode["value"],
                    "path": self.path,
                    "content_type": self.headers.get("Content-Type"),
                    "authorization_is_test_credential": (
                        self.headers.get("Authorization") == expected_authorization
                    ),
                    "body_size": len(body),
                    "span_names": [span.name for span in spans],
                    "trace_ids": sorted({{span.trace_id.hex() for span in spans}}),
                }}
            )

            if mode["value"] == "outage":
                response = b"Authorization: Bearer {RESPONSE_SECRET}"
                self.send_response(503)
            else:
                response = b""
                self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)


    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(LogCollector())

    server = HTTPServer(("127.0.0.1", 0), LoopbackHandler)
    server_thread = Thread(
        target=server.serve_forever,
        kwargs={{"poll_interval": 0.01}},
        name="langfuse-loopback-server",
        daemon=True,
    )
    server_thread.start()

    runtime = ObservabilityRuntimeConfig(
        environment="test",
        release="langfuse-transport-test",
        langfuse_enabled=True,
        langfuse_public_key="{FAKE_PUBLIC_KEY}",
        langfuse_secret_key="{FAKE_SECRET_KEY}",
        langfuse_host=f"http://127.0.0.1:{{server.server_address[1]}}",
    )
    seen_handlers: list[CallbackHandler] = []

    def business(value: str, config: dict[str, Any]) -> dict[str, Any]:
        seen_handlers.extend(
            handler
            for handler in config["callbacks"].handlers
            if isinstance(handler, CallbackHandler)
        )
        return {{"terminal_status": "succeeded", "artifact": value}}

    runnable = RunnableBinding(
        bound=RunnableLambda(business),
        config_factories=[create_observability_config_factory(runtime)],
    )

    lifecycle: list[str] = []
    client = None
    try:
        outage_result = runnable.invoke(
            "artifact-during-503",
            config={{"metadata": {{"correlation_id": "transport-outage"}}}},
        )
        client = initialize_langfuse_client(runtime)
        client.flush()
        lifecycle.append("flush:outage")
        log_deadline = monotonic() + 3
        while not any(
            record["logger"].startswith(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter"
            )
            and record["level"] == "ERROR"
            and "503" in record["message"]
            for record in records
        ):
            if monotonic() >= log_deadline:
                raise RuntimeError("OTLP exporter did not report the injected 503")
            sleep(0.01)

        mode["value"] = "healthy"
        recovery_result = runnable.invoke(
            "artifact-after-recovery",
            config={{"metadata": {{"correlation_id": "transport-recovery"}}}},
        )
        client.flush()
        lifecycle.append("flush:recovery")
    finally:
        if client is not None:
            client.shutdown()
            lifecycle.append("shutdown")
        server.shutdown()
        server_thread.join()
        server.server_close()

    result = {{
        "outage_result": outage_result,
        "recovery_result": recovery_result,
        "handler_types": [
            f"{{type(handler).__module__}}.{{type(handler).__name__}}"
            for handler in seen_handlers
        ],
        "handler_trace_ids": [handler.last_trace_id for handler in seen_handlers],
        "lifecycle": lifecycle,
        "requests": requests,
        "logs": records,
        "server_stopped": not server_thread.is_alive(),
    }}
    print("{_RESULT_PREFIX}" + json.dumps(result, sort_keys=True))
    """
)


@pytest.fixture(scope="module")
def transport_probe() -> dict[str, Any]:
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(("LANGFUSE_", "OTEL_")) or key.upper() in {
            "ALL_PROXY",
            "HTTP_PROXY",
            "HTTPS_PROXY",
        }:
            env.pop(key)
    env.update(
        {
            "APP_ENVIRONMENT": "test",
            "LANGFUSE_MEDIA_UPLOAD_ENABLED": "false",
            "LANGFUSE_TIMEOUT": "1",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result_line = next(
        (
            line.removeprefix(_RESULT_PREFIX)
            for line in completed.stdout.splitlines()
            if line.startswith(_RESULT_PREFIX)
        ),
        None,
    )
    assert result_line is not None, completed.stdout
    return json.loads(result_line)


def test_official_callback_503_is_fail_open_and_reaches_loopback(
    transport_probe: dict[str, Any],
) -> None:
    assert transport_probe["outage_result"] == {
        "terminal_status": "succeeded",
        "artifact": "artifact-during-503",
    }
    assert transport_probe["handler_types"] == [
        "langfuse.langchain.CallbackHandler.LangchainCallbackHandler",
        "langfuse.langchain.CallbackHandler.LangchainCallbackHandler",
    ]
    assert all(transport_probe["handler_trace_ids"])
    assert (
        transport_probe["handler_trace_ids"][0]
        != transport_probe["handler_trace_ids"][1]
    )

    outage_requests = [
        request
        for request in transport_probe["requests"]
        if request["mode"] == "outage"
    ]
    assert outage_requests
    assert all(
        request["path"] == "/api/public/otel/v1/traces"
        and request["content_type"] == "application/x-protobuf"
        and request["authorization_is_test_credential"] is True
        and request["body_size"] > 0
        and "business" in request["span_names"]
        and transport_probe["handler_trace_ids"][0] in request["trace_ids"]
        for request in outage_requests
    )

    transport_errors = [
        record
        for record in transport_probe["logs"]
        if record["logger"].startswith(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
        and record["level"] == "ERROR"
    ]
    assert any("503" in record["message"] for record in transport_errors)


def test_official_transport_failure_logs_are_redacted(
    transport_probe: dict[str, Any],
) -> None:
    rendered_logs = json.dumps(transport_probe["logs"], sort_keys=True)

    assert FAKE_PUBLIC_KEY not in rendered_logs
    assert FAKE_SECRET_KEY not in rendered_logs
    assert RESPONSE_SECRET not in rendered_logs
    assert "Authorization: [REDACTED]" in rendered_logs
    assert "Masking error" not in rendered_logs


def test_official_callback_delivers_next_trace_after_2xx_recovery(
    transport_probe: dict[str, Any],
) -> None:
    assert transport_probe["recovery_result"] == {
        "terminal_status": "succeeded",
        "artifact": "artifact-after-recovery",
    }
    healthy_requests = [
        request
        for request in transport_probe["requests"]
        if request["mode"] == "healthy"
    ]
    assert healthy_requests
    assert all(
        request["path"] == "/api/public/otel/v1/traces"
        and request["authorization_is_test_credential"] is True
        and "business" in request["span_names"]
        and transport_probe["handler_trace_ids"][1] in request["trace_ids"]
        for request in healthy_requests
    )
    assert transport_probe["lifecycle"] == [
        "flush:outage",
        "flush:recovery",
        "shutdown",
    ]
    assert transport_probe["server_stopped"] is True
