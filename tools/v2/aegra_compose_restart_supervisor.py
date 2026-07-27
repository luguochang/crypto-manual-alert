from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import signal
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID


_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _docker(*arguments: str) -> str:
    completed = subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _inspect_container(
    container: str,
    *,
    expected_project: str,
    expected_service: str,
) -> dict[str, Any]:
    payload = json.loads(_docker("inspect", container))
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError("Docker inspect returned an invalid container envelope")
    record = payload[0]
    labels = record.get("Config", {}).get("Labels", {})
    if labels.get("com.docker.compose.project") != expected_project:
        raise RuntimeError("Docker container is outside the expected Compose project")
    if labels.get("com.docker.compose.service") != expected_service:
        raise RuntimeError("Docker container is not the expected Compose service")
    state = record.get("State", {})
    pid = state.get("Pid")
    if not isinstance(pid, int) or pid < 0:
        raise RuntimeError("Docker container state omitted its process identity")
    return {
        "container_id": record.get("Id"),
        "pid": pid,
        "started_at": state.get("StartedAt"),
        "status": state.get("Status"),
    }


def _health_available(url: str) -> bool:
    try:
        with urlopen(Request(url, method="GET"), timeout=2) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _wait_for_health(
    url: str,
    *,
    available: bool,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _health_available(url) is available:
            return True
        time.sleep(0.2)
    return False


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _required_uuid(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise ValueError(f"restart request omitted {name}")
    UUID(value)
    return value


def _load_request(path: Path, project: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ValueError("restart request has an invalid schema")
    if payload.get("project") != project:
        raise ValueError("restart request project does not match its filename")
    for name in (
        "task_id",
        "product_run_id",
        "assistant_id",
        "thread_id",
        "run_id",
        "pause_id",
    ):
        _required_uuid(payload, name)
    if payload.get("review_iteration") != 1:
        raise ValueError("restart request must target the first review")
    if not isinstance(payload.get("pause_version"), int) or payload["pause_version"] < 1:
        raise ValueError("restart request has an invalid pause_version")
    interrupt_ids = payload.get("interrupt_ids")
    if (
        not isinstance(interrupt_ids, list)
        or not interrupt_ids
        or any(not isinstance(value, str) or not value for value in interrupt_ids)
    ):
        raise ValueError("restart request has invalid interrupt_ids")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--expected-compose-project", required=True)
    parser.add_argument("--expected-compose-service", required=True)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--health-url", required=True)
    parser.add_argument("--startup-timeout", required=True, type=float)
    parser.add_argument("--project", action="append", required=True)
    args = parser.parse_args()
    if not _CONTAINER_NAME.fullmatch(args.container):
        parser.error("container must be a literal Docker container name")
    if len(set(args.project)) != len(args.project):
        parser.error("restart projects must be unique")
    return args


def main() -> None:
    args = _parse_args()
    evidence_dir = args.evidence_dir.resolve(strict=True)
    stopping = False
    container_stopped = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    initial = _inspect_container(
        args.container,
        expected_project=args.expected_compose_project,
        expected_service=args.expected_compose_service,
    )
    if initial["status"] != "running" or initial["pid"] < 2:
        raise RuntimeError("Expected Aegra Compose container is not running")
    completed: set[str] = set()
    try:
        while not stopping and len(completed) < len(args.project):
            for project in args.project:
                if project in completed:
                    continue
                request_path = evidence_dir / f"aegra-restart-request-{project}.json"
                if not request_path.is_file():
                    continue
                request_payload = _load_request(request_path, project)
                before = _inspect_container(
                    args.container,
                    expected_project=args.expected_compose_project,
                    expected_service=args.expected_compose_service,
                )
                _docker("stop", "--time", "0", args.container)
                container_stopped = True
                unavailable = _wait_for_health(
                    args.health_url,
                    available=False,
                    timeout_seconds=20,
                )
                if not unavailable:
                    raise RuntimeError("Aegra Compose URL did not become unavailable")
                _docker("start", args.container)
                container_stopped = False
                recovered = _wait_for_health(
                    args.health_url,
                    available=True,
                    timeout_seconds=args.startup_timeout,
                )
                if not recovered:
                    raise RuntimeError("Aegra Compose URL did not recover")
                after = _inspect_container(
                    args.container,
                    expected_project=args.expected_compose_project,
                    expected_service=args.expected_compose_service,
                )
                if before["pid"] == after["pid"]:
                    raise RuntimeError("Aegra Compose process identity did not change")
                receipt = {
                    "schema_version": "1.0",
                    "project": project,
                    "request": request_payload,
                    "generation_before": before,
                    "generation_after": after,
                    "target_unavailable_observed": True,
                    "target_recovered_observed": True,
                    "restart_operation": "docker-stop-start",
                }
                _atomic_json(
                    evidence_dir / f"aegra-restart-receipt-{project}.json",
                    receipt,
                )
                _atomic_json(
                    evidence_dir / f"aegra-restart-complete-{project}.json",
                    receipt,
                )
                completed.add(project)
                print(f"Aegra Compose restart completed for {project}", flush=True)
            time.sleep(0.2)
    finally:
        if container_stopped:
            _docker("start", args.container)


if __name__ == "__main__":
    main()
