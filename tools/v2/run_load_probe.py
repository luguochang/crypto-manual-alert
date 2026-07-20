from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import socket
import sys
import tempfile
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


SCHEMA_VERSION = "2026-07-18.local-http-load-preflight.v1"
DEFAULT_PATH = "/app/api/v2/health"


@dataclass(frozen=True, slots=True)
class RequestResult:
    latency_ms: float
    outcome: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded, secret-safe local Product health load preflight"
    )
    parser.add_argument(
        "--profile",
        choices=("local-rehearsal", "hosted-production"),
        default="local-rehearsal",
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--release-tier", choices=("internal_alpha",), required=True)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _validated_target(base_url: str, path: str, *, profile: str) -> tuple[str, str]:
    if profile != "local-rehearsal":
        raise RuntimeError("hosted load acceptance is not implemented")
    parsed = urlsplit(base_url.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("load probe base URL must be a credential-free HTTP origin")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("local load probe requires a loopback base URL")
    if not path.startswith("/") or "?" in path or "#" in path or "\\" in path:
        raise ValueError("load probe path must be an absolute query-free HTTP path")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
    return origin, origin + path


def _validate_limits(
    *,
    request_count: int,
    concurrency: int,
    timeout_seconds: float,
) -> None:
    if request_count < 1 or request_count > 10_000:
        raise ValueError("load probe requests must be between 1 and 10000")
    if concurrency < 1 or concurrency > 200 or concurrency > request_count:
        raise ValueError(
            "load probe concurrency must be between 1 and 200 and not exceed requests"
        )
    if not math.isfinite(timeout_seconds) or not 0.1 <= timeout_seconds <= 60:
        raise ValueError("load probe timeout must be between 0.1 and 60 seconds")


def _request_once(url: str, timeout_seconds: float) -> RequestResult:
    started = perf_counter()
    outcome = "transport_error"
    try:
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "crypto-alert-v2-load-probe",
            },
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(4096)
            if response.status != 200:
                outcome = "unexpected_status"
            else:
                try:
                    parsed = json.loads(payload)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    outcome = "invalid_health_payload"
                else:
                    outcome = (
                        "succeeded"
                        if isinstance(parsed, dict)
                        and parsed.get("status") == "ok"
                        and parsed.get("version") == "2.0.0"
                        else "invalid_health_payload"
                    )
    except HTTPError:
        outcome = "unexpected_status"
    except (TimeoutError, socket.timeout):
        outcome = "timeout"
    except URLError as exc:
        outcome = (
            "timeout" if isinstance(exc.reason, socket.timeout) else "transport_error"
        )
    return RequestResult(
        latency_ms=round((perf_counter() - started) * 1000, 3),
        outcome=outcome,
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def run_probe(
    *,
    origin: str,
    target_url: str,
    path: str,
    release_tier: str,
    request_count: int,
    concurrency: int,
    timeout_seconds: float,
) -> dict[str, object]:
    started_at = datetime.now(UTC)
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(_request_once, target_url, timeout_seconds)
            for _ in range(request_count)
        ]
        results = [future.result() for future in as_completed(futures)]
    elapsed_seconds = max(perf_counter() - started, 0.000_001)
    finished_at = datetime.now(UTC)
    latencies = [result.latency_ms for result in results]
    outcomes: dict[str, int] = {}
    for result in results:
        outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1
    success_count = outcomes.get("succeeded", 0)
    failure_count = request_count - success_count
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed" if failure_count == 0 else "failed",
        "proof_level": "local-http-load-preflight",
        "profile": "local-rehearsal",
        "release_tier": release_tier,
        "window": {
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "finished_at": finished_at.isoformat().replace("+00:00", "Z"),
            "duration_seconds": round(elapsed_seconds, 6),
        },
        "target": {"origin": origin, "path": path},
        "load": {
            "request_count": request_count,
            "concurrency": concurrency,
            "success_count": success_count,
            "failure_count": failure_count,
            "outcomes": dict(sorted(outcomes.items())),
            "requests_per_second": round(request_count / elapsed_seconds, 3),
            "latency_ms": {
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "p99": _percentile(latencies, 0.99),
                "max": max(latencies, default=0.0),
            },
        },
        "slo_claims": [],
        "secret_scan": {"findings": 0},
        "does_not_prove": [
            "request_confirmation_p95",
            "first_visible_event_p95",
            "market_analysis_p95",
            "reconnect_success_rate",
            "duplicate_product_event_rate",
            "structured_output_success_rate",
            "evidence_reference_completeness",
            "checkpoint_recovery_success_rate",
            "hosted_production_slo",
        ],
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    if not path.is_absolute():
        raise ValueError("load probe output path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    args = _parser().parse_args()
    try:
        _validate_limits(
            request_count=args.requests,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout_seconds,
        )
        origin, target_url = _validated_target(
            args.base_url,
            args.path,
            profile=args.profile,
        )
        report = run_probe(
            origin=origin,
            target_url=target_url,
            path=args.path,
            release_tier=args.release_tier,
            request_count=args.requests,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout_seconds,
        )
        _write_report(args.output, report)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        raise SystemExit(0 if report["status"] == "passed" else 1)
    except SystemExit:
        raise
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(78 if args.profile == "hosted-production" else 1) from None


if __name__ == "__main__":
    main()
