from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
    child: subprocess.Popen[bytes] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if child is not None and available and child.poll() is not None:
            return False
        if _health_available(url) is available:
            return True
        time.sleep(0.2)
    return False


def _stop_child(child: subprocess.Popen[bytes], timeout_seconds: float = 15) -> None:
    if child.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(child.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    elif hasattr(os, "killpg"):
        os.killpg(child.pid, signal.SIGTERM)
    else:
        child.terminate()
    try:
        child.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        elif hasattr(os, "killpg"):
            os.killpg(child.pid, signal.SIGKILL)
        else:
            child.kill()
        child.wait(timeout=5)


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
    parser.add_argument("--working-directory", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--health-url", required=True)
    parser.add_argument("--startup-timeout", required=True, type=float)
    parser.add_argument("--project", action="append", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("an owned Aegra command is required after --")
    if len(set(args.project)) != len(args.project):
        parser.error("restart projects must be unique")
    return args


def main() -> None:
    args = _parse_args()
    working_directory = args.working_directory.resolve(strict=True)
    evidence_dir = args.evidence_dir.resolve(strict=True)
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    child_options: dict[str, Any] = {
        "cwd": working_directory,
        "start_new_session": True,
    }
    if os.name == "nt":
        child_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    child = subprocess.Popen(args.command, **child_options)
    completed: set[str] = set()
    try:
        while not stopping:
            if child.poll() is not None:
                raise RuntimeError("owned Aegra process exited unexpectedly")
            for project in args.project:
                if project in completed:
                    continue
                request_path = evidence_dir / f"aegra-restart-request-{project}.json"
                if not request_path.is_file():
                    continue
                request_payload = _load_request(request_path, project)
                before = {
                    "pid": child.pid,
                    "observed_at": _timestamp(),
                }
                _stop_child(child)
                unavailable = _wait_for_health(
                    args.health_url,
                    available=False,
                    timeout_seconds=15,
                )
                if not unavailable:
                    raise RuntimeError("Aegra URL did not become unavailable")
                child = subprocess.Popen(args.command, **child_options)
                recovered = _wait_for_health(
                    args.health_url,
                    available=True,
                    timeout_seconds=args.startup_timeout,
                    child=child,
                )
                if not recovered:
                    raise RuntimeError("Aegra URL did not recover")
                receipt = {
                    "schema_version": "1.0",
                    "project": project,
                    "request": request_payload,
                    "generation_before": before,
                    "generation_after": {
                        "pid": child.pid,
                        "observed_at": _timestamp(),
                    },
                    "target_unavailable_observed": True,
                    "target_recovered_observed": True,
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
                print(f"Aegra restart completed for {project}", flush=True)
            time.sleep(0.2)
    finally:
        _stop_child(child)


if __name__ == "__main__":
    main()
