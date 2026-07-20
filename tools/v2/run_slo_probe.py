from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Literal


SCHEMA_VERSION = "2026-07-18.slo-contract-evaluation.v1"
MEASUREMENT_SCHEMA_VERSION = "2026-07-18.slo-measurements.v1"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class MetricSpec:
    unit: str
    comparator: Literal["max", "max_exclusive", "min", "measured"]
    threshold: float | None


METRICS = {
    "api_agent_availability_rate": MetricSpec("ratio", "measured", None),
    "request_confirmation_p95_ms": MetricSpec("ms", "max", 1_000),
    "first_visible_stage_event_p95_ms": MetricSpec("ms", "max", 3_000),
    "market_analysis_p95_ms": MetricSpec("ms", "max", 150_000),
    "market_analysis_max_ms": MetricSpec("ms", "max", 180_000),
    "reconnect_success_rate": MetricSpec("ratio", "min", 0.98),
    "duplicate_product_event_rate": MetricSpec("ratio", "max_exclusive", 0.001),
    "structured_output_success_rate": MetricSpec("ratio", "min", 0.97),
    "allowed_evidence_reference_completeness_rate": MetricSpec("ratio", "min", 1.0),
    "checkpoint_recovery_success_rate": MetricSpec("ratio", "min", 0.95),
    "cross_tenant_leak_count": MetricSpec("count", "max", 0),
    "secret_leak_count": MetricSpec("count", "max", 0),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a complete Internal Alpha SLO measurement manifest"
    )
    parser.add_argument(
        "--profile",
        choices=("local-rehearsal", "hosted-production"),
        default="local-rehearsal",
    )
    parser.add_argument("--release-tier", choices=("internal_alpha",), required=True)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _load_json(path: Path) -> tuple[dict[str, object], str]:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("SLO measurements must be an absolute regular file")
    payload = path.read_bytes()
    if len(payload) > 1_000_000:
        raise ValueError("SLO measurements exceed the size limit")
    try:
        parsed = json.loads(
            payload,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non-finite JSON value")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("SLO measurements must contain valid JSON") from None
    if not isinstance(parsed, dict):
        raise ValueError("SLO measurements must be a JSON object")
    return parsed, sha256(payload).hexdigest()


def _timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"SLO {field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"SLO {field} must be an ISO timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError(f"SLO {field} must be timezone-aware")
    return parsed


def _metric_verdict(value: float, spec: MetricSpec) -> bool | None:
    if spec.comparator == "measured":
        return None
    assert spec.threshold is not None
    if spec.comparator == "max":
        return value <= spec.threshold
    if spec.comparator == "max_exclusive":
        return value < spec.threshold
    return value >= spec.threshold


def evaluate(
    manifest: dict[str, object],
    *,
    input_sha256: str,
    profile: str,
    release_tier: str,
) -> dict[str, object]:
    if profile != "local-rehearsal":
        raise RuntimeError("hosted SLO acceptance is not implemented")
    expected_top_level = {
        "schema_version",
        "profile",
        "release_tier",
        "measurement_source",
        "window",
        "measurements",
    }
    if set(manifest) != expected_top_level:
        raise ValueError("SLO measurement manifest fields are incomplete or unknown")
    if manifest["schema_version"] != MEASUREMENT_SCHEMA_VERSION:
        raise ValueError("SLO measurement schema version is unsupported")
    if manifest["profile"] != profile or manifest["release_tier"] != release_tier:
        raise ValueError("SLO profile or release tier does not match the invocation")
    measurement_source = manifest["measurement_source"]
    if measurement_source != "synthetic-contract":
        raise ValueError("SLO measurement source is unsupported")

    window = manifest["window"]
    if not isinstance(window, dict) or set(window) != {"started_at", "finished_at"}:
        raise ValueError("SLO measurement window is invalid")
    started_at = _timestamp(window["started_at"], field="started_at")
    finished_at = _timestamp(window["finished_at"], field="finished_at")
    if finished_at <= started_at:
        raise ValueError("SLO measurement window must have positive duration")

    measurements = manifest["measurements"]
    if not isinstance(measurements, dict) or set(measurements) != set(METRICS):
        raise ValueError(
            "SLO measurements must contain every required metric exactly once"
        )

    verdicts: dict[str, dict[str, object]] = {}
    all_passed = True
    for name, spec in METRICS.items():
        measurement = measurements[name]
        if not isinstance(measurement, dict) or set(measurement) != {
            "value",
            "sample_count",
            "query_id",
        }:
            raise ValueError("SLO metric fields are incomplete or unknown")
        value = measurement["value"]
        sample_count = measurement["sample_count"]
        query_id = measurement["query_id"]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError("SLO metric value must be a finite non-negative number")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count < 1
        ):
            raise ValueError("SLO metric sample_count must be a positive integer")
        if not isinstance(query_id, str) or SAFE_IDENTIFIER.fullmatch(query_id) is None:
            raise ValueError("SLO metric query_id is invalid")
        numeric_value = float(value)
        if spec.unit == "ratio" and numeric_value > 1:
            raise ValueError("SLO ratio metric must be between zero and one")
        if spec.unit == "count" and not numeric_value.is_integer():
            raise ValueError("SLO count metric must be an integer")
        passed = _metric_verdict(numeric_value, spec)
        all_passed = all_passed and passed is not False
        verdicts[name] = {
            "value": numeric_value,
            "sample_count": sample_count,
            "unit": spec.unit,
            "comparator": spec.comparator,
            "threshold": spec.threshold,
            "passed": passed,
            "query_id": query_id,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed" if all_passed else "failed",
        "proof_level": "synthetic-source-candidate-slo-contract",
        "profile": profile,
        "release_tier": release_tier,
        "measurement_source": measurement_source,
        "measurement_manifest_sha256": input_sha256,
        "window": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        },
        "metrics": verdicts,
        "does_not_prove": [
            "runtime_measurement_provenance",
            "hosted_measurement_provenance",
            "monthly_hosted_availability_window",
            "production_alert_receipts",
            "production_release_attestation",
        ],
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    if not path.is_absolute():
        raise ValueError("SLO output path must be absolute")
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
        manifest, input_sha256 = _load_json(args.measurements)
        report = evaluate(
            manifest,
            input_sha256=input_sha256,
            profile=args.profile,
            release_tier=args.release_tier,
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
