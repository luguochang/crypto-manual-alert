from __future__ import annotations

from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4


class FakeAgentServer:
    """A loopback-only Agent Server with an explicit run-acceptance barrier."""

    def __init__(self) -> None:
        self.run_accepted = Event()
        self.release_run_response = Event()
        self.run_status_requested = Event()
        self.release_run_status = Event()
        self.block_run_status = False
        self.join_requested = Event()
        self._lock = Lock()
        self._counts: Counter[tuple[str, str]] = Counter()
        self._threads: set[str] = set()
        self._runs: dict[str, dict[str, dict[str, Any]]] = {}
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _RequestHandler)
        self._server.fake = self  # type: ignore[attr-defined]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self.release_run_response.set()
        self.release_run_status.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def count(self, method: str, endpoint: str) -> int:
        with self._lock:
            return self._counts[(method, endpoint)]

    def create_thread(self, payload: dict[str, Any]) -> dict[str, Any]:
        thread_id = str(payload.get("thread_id") or uuid4())
        with self._lock:
            self._counts[("POST", "/threads")] += 1
            self._threads.add(thread_id)
            self._runs.setdefault(thread_id, {})
        return {"thread_id": thread_id, "metadata": payload.get("metadata") or {}}

    def create_run(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(uuid4())
        assistant_id = str(payload.get("assistant_id") or "crypto_analysis")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        run = {
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "status": "success",
            # Discovery needs identity metadata. Headers and credentials are never stored.
            "metadata": {
                key: metadata[key]
                for key in (
                    "tenant_id",
                    "workspace_id",
                    "user_id",
                    "task_id",
                    "product_run_id",
                )
                if key in metadata
            },
        }
        with self._lock:
            self._counts[("POST", "/threads/{id}/runs")] += 1
            self._threads.add(thread_id)
            self._runs.setdefault(thread_id, {})[run_id] = run
        self.run_accepted.set()
        return run

    def list_runs(
        self, thread_id: str, *, offset: int, limit: int
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._counts[("GET", "/threads/{id}/runs")] += 1
            runs = list(self._runs.get(thread_id, {}).values())
        return runs[offset : offset + limit]

    def get_run(self, thread_id: str, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._counts[("GET", "/threads/{id}/runs/{run_id}")] += 1
            run = self._runs.get(thread_id, {}).get(run_id)
        if self.block_run_status:
            self.run_status_requested.set()
            self.release_run_status.wait(timeout=30)
        return run

    def get_state(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._counts[("GET", "/threads/{id}/state")] += 1
            runs = list(self._runs.get(thread_id, {}).values())
        if not runs:
            return None
        run_id = str(runs[-1]["run_id"])
        return {
            "values": {},
            "next": [],
            "checkpoint": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": f"checkpoint-{run_id}",
            },
            "metadata": {"run_id": run_id},
            "tasks": [],
        }

    def join(self, method: str, thread_id: str, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._counts[(method, "/threads/{id}/runs/{run_id}/join")] += 1
            run = self._runs.get(thread_id, {}).get(run_id)
        if run is None:
            return None
        self.join_requested.set()
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "controlled_process_recovery",
                    "error_type": "RecoveryHarness",
                    "retryable": False,
                }
            ],
        }

    def stream_exists(self, thread_id: str, run_id: str) -> bool:
        with self._lock:
            self._counts[("GET", "/threads/{id}/runs/{run_id}/stream")] += 1
            return run_id in self._runs.get(thread_id, {})


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def fake(self) -> FakeAgentServer:
        return self.server.fake  # type: ignore[attr-defined,no-any-return]

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        parts = path.strip("/").split("/")
        if path == "/threads":
            self._send_json(200, self.fake.create_thread(self._json_body()))
            return
        if len(parts) == 3 and parts[0] == "threads" and parts[2] == "runs":
            run = self.fake.create_run(parts[1], self._json_body())
            self.fake.release_run_response.wait(timeout=30)
            self._send_json(
                200,
                run,
                headers={
                    "Content-Location": (f"/threads/{parts[1]}/runs/{run['run_id']}")
                },
            )
            return
        if (
            len(parts) == 5
            and parts[0] == "threads"
            and parts[2] == "runs"
            and parts[4] == "join"
        ):
            self._send_join("POST", parts[1], parts[3])
            return
        self._send_json(404, {"detail": "not found"})

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "threads" and parts[2] == "runs":
            query = _query_values(parsed.query)
            runs = self.fake.list_runs(
                parts[1],
                offset=int(query.get("offset", "0")),
                limit=int(query.get("limit", "10")),
            )
            self._send_json(200, runs)
            return
        if len(parts) == 4 and parts[0] == "threads" and parts[2] == "runs":
            run = self.fake.get_run(parts[1], parts[3])
            self._send_json(
                200 if run is not None else 404, run or {"detail": "not found"}
            )
            return
        if len(parts) == 3 and parts[0] == "threads" and parts[2] == "state":
            state = self.fake.get_state(parts[1])
            self._send_json(
                200 if state is not None else 404,
                state or {"detail": "not found"},
            )
            return
        if (
            len(parts) == 5
            and parts[0] == "threads"
            and parts[2] == "runs"
            and parts[4] == "join"
        ):
            self._send_join("GET", parts[1], parts[3])
            return
        if (
            len(parts) == 5
            and parts[0] == "threads"
            and parts[2] == "runs"
            and parts[4] == "stream"
        ):
            if self.fake.stream_exists(parts[1], parts[3]):
                self._send_sse_end()
            else:
                self._send_json(404, {"detail": "not found"})
            return
        self._send_json(404, {"detail": "not found"})

    def _send_join(self, method: str, thread_id: str, run_id: str) -> None:
        output = self.fake.join(method, thread_id, run_id)
        self._send_json(
            200 if output is not None else 404,
            output or {"detail": "not found"},
        )

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    def _send_json(
        self,
        status: int,
        payload: Any,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_sse_end(self) -> None:
        encoded = b"event: end\ndata: null\n\n"
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _query_values(query: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in query.split("&"):
        key, separator, value = item.partition("=")
        if separator:
            values[key] = value
    return values


__all__ = ["FakeAgentServer"]
