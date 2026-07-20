from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


SCHEMA_VERSION = "2026-07-18.local-product-slo-observation.v1"
FORMAL_SLO_METRIC_NAMES = (
    "api_agent_availability_rate",
    "request_confirmation_p95_ms",
    "first_visible_stage_event_p95_ms",
    "market_analysis_p95_ms",
    "market_analysis_max_ms",
    "reconnect_success_rate",
    "duplicate_product_event_rate",
    "structured_output_success_rate",
    "allowed_evidence_reference_completeness_rate",
    "checkpoint_recovery_success_rate",
    "cross_tenant_leak_count",
    "secret_leak_count",
)
PROGRESSIVE_STAGE_EVENT_TYPES = frozenset(
    {
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
    }
)
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "blocked", "failed", "cancelled"})
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

RUNS_QUERY_ID = "product-slo.initial-runs.v1"
EVENTS_QUERY_ID = "product-slo.domain-events.v1"
PROJECTIONS_QUERY_ID = "product-slo.projection-integrity.v1"

RUNS_QUERY = """
SELECT
    r.id::text AS run_id,
    t.id::text AS task_id,
    t.created_at AS task_created_at,
    r.created_at AS run_created_at,
    r.started_at,
    r.finished_at,
    r.status,
    r.failure_code
FROM app.tasks AS t
JOIN app.runs AS r
  ON r.tenant_id = t.tenant_id
 AND r.workspace_id = t.workspace_id
 AND r.owner_user_id = t.owner_user_id
 AND r.task_id = t.id
WHERE t.tenant_id = CAST(:tenant_id AS uuid)
  AND t.workspace_id = CAST(:workspace_id AS uuid)
  AND t.created_at >= :window_started_at
  AND t.created_at < :window_finished_at
  AND r.attempt = 1
  AND r.resume_of_run_id IS NULL
  AND r.retry_of_run_id IS NULL
  AND r.forked_from_run_id IS NULL
ORDER BY t.created_at, r.id
LIMIT :row_limit
"""

EVENTS_QUERY = """
WITH cohort AS (
    SELECT r.id
    FROM app.tasks AS t
    JOIN app.runs AS r
      ON r.tenant_id = t.tenant_id
     AND r.workspace_id = t.workspace_id
     AND r.owner_user_id = t.owner_user_id
     AND r.task_id = t.id
    WHERE t.tenant_id = CAST(:tenant_id AS uuid)
      AND t.workspace_id = CAST(:workspace_id AS uuid)
      AND t.created_at >= :window_started_at
      AND t.created_at < :window_finished_at
      AND r.attempt = 1
      AND r.resume_of_run_id IS NULL
      AND r.retry_of_run_id IS NULL
      AND r.forked_from_run_id IS NULL
)
SELECT
    de.run_id::text AS run_id,
    de.event_type,
    de.payload_hash,
    de.created_at
FROM cohort AS c
JOIN app.domain_events AS de
  ON de.run_id = c.id
 AND de.tenant_id = CAST(:tenant_id AS uuid)
 AND de.workspace_id = CAST(:workspace_id AS uuid)
ORDER BY de.run_id, de.sequence
"""

PROJECTIONS_QUERY = """
WITH cohort AS (
    SELECT
        r.id,
        r.tenant_id,
        r.workspace_id,
        r.owner_user_id,
        r.task_id
    FROM app.tasks AS t
    JOIN app.runs AS r
      ON r.tenant_id = t.tenant_id
     AND r.workspace_id = t.workspace_id
     AND r.owner_user_id = t.owner_user_id
     AND r.task_id = t.id
    WHERE t.tenant_id = CAST(:tenant_id AS uuid)
      AND t.workspace_id = CAST(:workspace_id AS uuid)
      AND t.created_at >= :window_started_at
      AND t.created_at < :window_finished_at
      AND r.attempt = 1
      AND r.resume_of_run_id IS NULL
      AND r.retry_of_run_id IS NULL
      AND r.forked_from_run_id IS NULL
)
SELECT
    c.id::text AS run_id,
    (
        SELECT count(*)
        FROM app.artifact_versions AS av
        WHERE av.tenant_id = c.tenant_id
          AND av.workspace_id = c.workspace_id
          AND av.owner_user_id = c.owner_user_id
          AND av.task_id = c.task_id
          AND av.run_id = c.id
          AND av.status = 'committed'
    ) AS artifact_version_count,
    (
        SELECT count(*)
        FROM app.decisions AS d
        WHERE d.tenant_id = c.tenant_id
          AND d.workspace_id = c.workspace_id
          AND d.owner_user_id = c.owner_user_id
          AND d.task_id = c.task_id
          AND d.run_id = c.id
    ) AS decision_count,
    (
        SELECT count(*)
        FROM app.web_evidence AS we
        WHERE we.tenant_id = c.tenant_id
          AND we.workspace_id = c.workspace_id
          AND we.owner_user_id = c.owner_user_id
          AND we.task_id = c.task_id
          AND we.run_id = c.id
    ) AS web_evidence_count
FROM cohort AS c
ORDER BY c.id
"""


def _query_hash(query: str) -> str:
    return sha256(" ".join(query.split()).encode("utf-8")).hexdigest()


QUERY_PROVENANCE = {
    RUNS_QUERY_ID: _query_hash(RUNS_QUERY),
    EVENTS_QUERY_ID: _query_hash(EVENTS_QUERY),
    PROJECTIONS_QUERY_ID: _query_hash(PROJECTIONS_QUERY),
}


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    task_id: str
    task_created_at: datetime
    run_created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: str
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class EventRecord:
    run_id: str
    event_type: str
    payload_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectionIntegrityRecord:
    run_id: str
    artifact_version_count: int
    decision_count: int
    web_evidence_count: int


@dataclass(frozen=True, slots=True)
class CollectedProductData:
    observed_at: datetime
    snapshot_sha256: str
    migration_revision: str
    runs: tuple[RunRecord, ...]
    events: tuple[EventRecord, ...]
    projection_integrity: tuple[ProjectionIntegrityRecord, ...]


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one sample")
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    rank = math.ceil(percentile * len(ordered))
    return ordered[rank - 1]


def _milliseconds(start: datetime, finish: datetime) -> float:
    return round((finish - start).total_seconds() * 1000, 3)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _unavailable(unit: str, *reason_codes: str) -> dict[str, object]:
    return {
        "measurement_status": "unavailable",
        "value": None,
        "unit": unit,
        "sample_count": 0,
        "numerator": None,
        "denominator": None,
        "missing_count": 0,
        "censored_count": 0,
        "invalid_timestamp_count": 0,
        "reason_codes": list(reason_codes),
    }


def _proxy(
    *,
    value: float | None,
    unit: str,
    sample_count: int,
    numerator: int | None,
    denominator: int | None,
    missing_count: int,
    censored_count: int,
    invalid_timestamp_count: int,
    proxy_definition: str,
    query_ids: Sequence[str],
    limitation_codes: Sequence[str],
) -> dict[str, object]:
    return {
        "measurement_status": "proxy",
        "value": value,
        "unit": unit,
        "sample_count": sample_count,
        "numerator": numerator,
        "denominator": denominator,
        "missing_count": missing_count,
        "censored_count": censored_count,
        "invalid_timestamp_count": invalid_timestamp_count,
        "proxy_definition": proxy_definition,
        "query_ids": list(query_ids),
        "limitation_codes": list(limitation_codes),
    }


def _first_events(
    events: Iterable[EventRecord],
    *,
    event_types: frozenset[str],
) -> dict[str, EventRecord]:
    first: dict[str, EventRecord] = {}
    for event in events:
        if event.event_type not in event_types:
            continue
        existing = first.get(event.run_id)
        if existing is None or event.created_at < existing.created_at:
            first[event.run_id] = event
    return first


def _latency_samples(
    runs: Sequence[RunRecord],
    events: dict[str, EventRecord],
) -> tuple[list[float], int, int, int]:
    samples: list[float] = []
    eligible = 0
    missing = 0
    invalid = 0
    for run in runs:
        if run.started_at is None:
            continue
        eligible += 1
        event = events.get(run.run_id)
        if event is None:
            missing += 1
            continue
        duration = _milliseconds(run.started_at, event.created_at)
        if duration < 0:
            invalid += 1
            continue
        samples.append(duration)
    return samples, eligible, missing, invalid


def _execution_samples(
    runs: Sequence[RunRecord],
) -> tuple[list[float], int, int, int]:
    samples: list[float] = []
    eligible = 0
    censored = 0
    invalid = 0
    for run in runs:
        if run.started_at is None:
            continue
        eligible += 1
        if run.finished_at is None:
            censored += 1
            continue
        duration = _milliseconds(run.started_at, run.finished_at)
        if duration < 0:
            invalid += 1
            continue
        samples.append(duration)
    return samples, eligible, censored, invalid


def _duplicate_event_proxy(events: Sequence[EventRecord]) -> tuple[int, int]:
    identities = Counter(
        (event.run_id, event.event_type, event.payload_hash) for event in events
    )
    duplicates = sum(max(count - 1, 0) for count in identities.values())
    return duplicates, len(events)


def _cohort_fingerprint(runs: Sequence[RunRecord]) -> str:
    encoded = "\n".join(sorted(run.run_id for run in runs)).encode("utf-8")
    return sha256(encoded).hexdigest()


def _status_execution_diagnostics(
    runs: Sequence[RunRecord],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        if run.started_at is None or run.finished_at is None:
            continue
        duration = _milliseconds(run.started_at, run.finished_at)
        if duration >= 0:
            grouped[run.status].append(duration)
    return {
        status: {
            "sample_count": len(samples),
            "p95_ms": nearest_rank_percentile(samples, 0.95),
            "max_ms": max(samples),
        }
        for status, samples in sorted(grouped.items())
    }


def build_local_observation_report(
    collected: CollectedProductData,
    *,
    window_started_at: datetime,
    window_finished_at: datetime,
    scope_label: str,
    environment: str,
    traffic_class: str,
    source_identity: str,
    database_source_label: str,
) -> dict[str, object]:
    if window_finished_at <= window_started_at:
        raise ValueError("observation window must have positive duration")
    for value in (
        scope_label,
        environment,
        traffic_class,
        source_identity,
        database_source_label,
    ):
        if SAFE_LABEL.fullmatch(value) is None:
            raise ValueError("observation labels must use safe identifier characters")

    analysis_events = _first_events(
        collected.events,
        event_types=frozenset({"agent.output.committed"}),
    )
    analysis_samples, analysis_eligible, analysis_missing, analysis_invalid = (
        _latency_samples(collected.runs, analysis_events)
    )
    execution_samples, execution_eligible, execution_censored, execution_invalid = (
        _execution_samples(collected.runs)
    )
    duplicate_count, event_count = _duplicate_event_proxy(collected.events)

    metrics = {
        "api_agent_availability_rate": _unavailable(
            "ratio", "requires_hosted_scheduled_health_observations"
        ),
        "request_confirmation_p95_ms": _unavailable(
            "ms", "edge_request_and_ack_timestamps_absent"
        ),
        "first_visible_stage_event_p95_ms": _unavailable(
            "ms", "browser_render_timestamp_absent"
        ),
        "market_analysis_p95_ms": _proxy(
            value=(
                nearest_rank_percentile(analysis_samples, 0.95)
                if analysis_samples
                else None
            ),
            unit="ms",
            sample_count=len(analysis_samples),
            numerator=None,
            denominator=analysis_eligible,
            missing_count=analysis_missing,
            censored_count=0,
            invalid_timestamp_count=analysis_invalid,
            proxy_definition="run.started_at_to_first_persisted_agent_output",
            query_ids=(RUNS_QUERY_ID, EVENTS_QUERY_ID),
            limitation_codes=(
                "durable_request_ack_timestamp_absent",
                "missing_analysis_not_encoded_as_infinite_latency",
                "mixed_local_traffic_cohort_possible",
            ),
        ),
        "market_analysis_max_ms": _proxy(
            value=max(execution_samples) if execution_samples else None,
            unit="ms",
            sample_count=len(execution_samples),
            numerator=None,
            denominator=execution_eligible,
            missing_count=0,
            censored_count=execution_censored,
            invalid_timestamp_count=execution_invalid,
            proxy_definition="run.started_at_to_run.finished_at",
            query_ids=(RUNS_QUERY_ID,),
            limitation_codes=(
                "terminal_runtime_not_ack_to_analysis_deadline",
                "open_runs_reported_as_censored",
                "mixed_local_traffic_cohort_possible",
            ),
        ),
        "reconnect_success_rate": _unavailable(
            "ratio", "reconnect_attempt_ledger_absent"
        ),
        "duplicate_product_event_rate": _proxy(
            value=(duplicate_count / event_count if event_count else None),
            unit="ratio",
            sample_count=event_count,
            numerator=duplicate_count,
            denominator=event_count,
            missing_count=0,
            censored_count=0,
            invalid_timestamp_count=0,
            proxy_definition="extra_persisted_rows_per_run_type_payload_hash",
            query_ids=(EVENTS_QUERY_ID,),
            limitation_codes=(
                "consumer_delivery_attempts_absent",
                "write_time_deduplication_hides_replays",
            ),
        ),
        "structured_output_success_rate": _unavailable(
            "ratio", "structured_operation_attempt_ledger_absent"
        ),
        "allowed_evidence_reference_completeness_rate": _unavailable(
            "ratio", "claim_to_immutable_evidence_relation_absent"
        ),
        "checkpoint_recovery_success_rate": _unavailable(
            "ratio", "recovery_attempt_type_and_outcome_ledger_absent"
        ),
        "cross_tenant_leak_count": _unavailable(
            "count", "hosted_multisurface_security_observations_required"
        ),
        "secret_leak_count": _unavailable(
            "count", "live_canary_scan_artifact_required"
        ),
    }

    first_stage_events = _first_events(
        collected.events,
        event_types=PROGRESSIVE_STAGE_EVENT_TYPES,
    )
    (
        first_stage_samples,
        first_stage_eligible,
        first_stage_missing,
        first_stage_invalid,
    ) = _latency_samples(collected.runs, first_stage_events)
    successful_runs = {
        run.run_id for run in collected.runs if run.status == "succeeded"
    }
    projection_by_run = {item.run_id: item for item in collected.projection_integrity}
    complete_projection_count = sum(
        1
        for run_id in successful_runs
        if (record := projection_by_run.get(run_id)) is not None
        and record.artifact_version_count == 1
        and record.decision_count == 1
        and record.web_evidence_count >= 1
    )
    agent_output_run_count = len(
        {
            event.run_id
            for event in collected.events
            if event.event_type == "agent.output.committed"
        }
    )
    model_invalid_output_run_count = sum(
        run.failure_code == "model_invalid_output" for run in collected.runs
    )
    status_counts = Counter(run.status for run in collected.runs)

    diagnostics = {
        "run_started_to_first_persisted_stage_event_p95_ms": {
            "value": (
                nearest_rank_percentile(first_stage_samples, 0.95)
                if first_stage_samples
                else None
            ),
            "unit": "ms",
            "sample_count": len(first_stage_samples),
            "eligible_count": first_stage_eligible,
            "missing_count": first_stage_missing,
            "invalid_timestamp_count": first_stage_invalid,
            "not_equivalent_to": "first_visible_stage_event_p95_ms",
        },
        "successful_projection_chain_integrity_rate": {
            "value": (
                complete_projection_count / len(successful_runs)
                if successful_runs
                else None
            ),
            "unit": "ratio",
            "sample_count": len(successful_runs),
            "numerator": complete_projection_count,
            "denominator": len(successful_runs),
            "definition": (
                "one_committed_artifact_version_one_decision_and_web_evidence"
            ),
            "not_equivalent_to": ("allowed_evidence_reference_completeness_rate"),
        },
        "structured_output_outcome_proxy_counts": {
            "persisted_agent_output_runs": agent_output_run_count,
            "model_invalid_output_runs": model_invalid_output_run_count,
            "not_equivalent_to": "structured_output_success_rate",
        },
        "run_status_counts": dict(sorted(status_counts.items())),
        "execution_duration_by_terminal_status": _status_execution_diagnostics(
            collected.runs
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "proof_level": "local-product-database-observation",
        "formal_slo_coverage": {
            "measured": 0,
            "required": len(FORMAL_SLO_METRIC_NAMES),
            "production_acceptance": False,
        },
        "scope": {
            "scope_label": scope_label,
            "window_started_at": _iso(window_started_at),
            "window_finished_at": _iso(window_finished_at),
            "cohort_anchor": "task.created_at",
            "lineage": "initial",
            "cohort_run_count": len(collected.runs),
            "cohort_fingerprint_sha256": _cohort_fingerprint(collected.runs),
            "window_settled_for_180s": (
                collected.observed_at >= window_finished_at + timedelta(seconds=180)
            ),
        },
        "provenance": {
            "measurement_source": "local-observed",
            "environment": environment,
            "traffic_class": traffic_class,
            "source_identity": source_identity,
            "database_source_label": database_source_label,
            "database_schema_revision": collected.migration_revision,
            "database_snapshot_sha256": collected.snapshot_sha256,
            "collected_at": _iso(collected.observed_at),
            "transaction_isolation": "repeatable-read",
            "transaction_read_only": True,
            "payload_columns_read": False,
            "query_sha256": dict(sorted(QUERY_PROVENANCE.items())),
        },
        "metrics": metrics,
        "diagnostics": diagnostics,
        "does_not_prove": [
            "any_formal_adr_0006_slo",
            "hosted_measurement_provenance",
            "browser_visible_latency",
            "consumer_stream_delivery_quality",
            "monthly_hosted_availability_window",
            "cross_tenant_or_secret_leak_absence",
            "production_alert_receipts",
            "production_release_attestation",
        ],
    }


async def collect_product_data(
    connection: AsyncConnection,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    window_started_at: datetime,
    window_finished_at: datetime,
    max_runs: int,
) -> CollectedProductData:
    parameters = {
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        "window_started_at": window_started_at,
        "window_finished_at": window_finished_at,
        "row_limit": max_runs + 1,
    }
    snapshot_row = (
        await connection.execute(
            text(
                "SELECT transaction_timestamp() AS observed_at, "
                "pg_current_snapshot()::text AS snapshot"
            )
        )
    ).one()
    migration_revision = await connection.scalar(
        text("SELECT version_num FROM app.alembic_version")
    )
    if not isinstance(migration_revision, str):
        raise RuntimeError("Product database migration revision is unavailable")

    run_rows = (await connection.execute(text(RUNS_QUERY), parameters)).mappings().all()
    if len(run_rows) > max_runs:
        raise RuntimeError("Product SLO cohort exceeds max_runs; narrow the window")
    event_rows = (
        (await connection.execute(text(EVENTS_QUERY), parameters)).mappings().all()
    )
    projection_rows = (
        (await connection.execute(text(PROJECTIONS_QUERY), parameters)).mappings().all()
    )

    runs = tuple(
        RunRecord(
            run_id=str(row["run_id"]),
            task_id=str(row["task_id"]),
            task_created_at=row["task_created_at"],
            run_created_at=row["run_created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=str(row["status"]),
            failure_code=(
                str(row["failure_code"]) if row["failure_code"] is not None else None
            ),
        )
        for row in run_rows
    )
    events = tuple(
        EventRecord(
            run_id=str(row["run_id"]),
            event_type=str(row["event_type"]),
            payload_hash=str(row["payload_hash"]),
            created_at=row["created_at"],
        )
        for row in event_rows
    )
    projections = tuple(
        ProjectionIntegrityRecord(
            run_id=str(row["run_id"]),
            artifact_version_count=int(row["artifact_version_count"]),
            decision_count=int(row["decision_count"]),
            web_evidence_count=int(row["web_evidence_count"]),
        )
        for row in projection_rows
    )
    snapshot = str(snapshot_row.snapshot)
    return CollectedProductData(
        observed_at=snapshot_row.observed_at,
        snapshot_sha256=sha256(snapshot.encode("utf-8")).hexdigest(),
        migration_revision=migration_revision,
        runs=runs,
        events=events,
        projection_integrity=projections,
    )


def write_report(path: Path, report: dict[str, object]) -> None:
    if not path.is_absolute():
        raise ValueError("observation output path must be absolute")
    if path.is_symlink():
        raise ValueError("observation output path must not be a symlink")
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


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observation timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect non-acceptance Product DB SLO proxy observations"
    )
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--finished-at", required=True)
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--workspace-id", type=UUID, required=True)
    parser.add_argument("--scope-label", required=True)
    parser.add_argument(
        "--environment",
        choices=("development", "local", "test", "staging"),
        default="local",
    )
    parser.add_argument(
        "--traffic-class",
        choices=("user", "synthetic", "failure-injection", "unknown"),
        default="unknown",
    )
    parser.add_argument("--source-identity", default="dirty-working-tree")
    parser.add_argument("--database-source-label", default="local-product-postgres")
    parser.add_argument("--max-runs", type=int, default=10_000)
    parser.add_argument("--output", type=Path, required=True)
    return parser


async def _collect(args: argparse.Namespace) -> dict[str, object]:
    database_url = os.environ.get("PRODUCT_DATABASE_URL")
    if not database_url:
        raise RuntimeError("PRODUCT_DATABASE_URL is required")
    if not 1 <= args.max_runs <= 100_000:
        raise ValueError("max_runs must be between 1 and 100000")
    started_at = _timestamp(args.started_at)
    finished_at = _timestamp(args.finished_at)
    if finished_at <= started_at:
        raise ValueError("observation window must have positive duration")

    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"timeout": 10},
    )
    try:
        if engine.dialect.name != "postgresql":
            raise ValueError("Product SLO collector requires PostgreSQL")
        async with engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            collected = await collect_product_data(
                connection,
                tenant_id=args.tenant_id,
                workspace_id=args.workspace_id,
                window_started_at=started_at,
                window_finished_at=finished_at,
                max_runs=args.max_runs,
            )
    finally:
        await engine.dispose()
    return build_local_observation_report(
        collected,
        window_started_at=started_at,
        window_finished_at=finished_at,
        scope_label=args.scope_label,
        environment=args.environment,
        traffic_class=args.traffic_class,
        source_identity=args.source_identity,
        database_source_label=args.database_source_label,
    )


def main() -> None:
    args = _parser().parse_args()
    try:
        report = asyncio.run(_collect(args))
        write_report(args.output, report)
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "proof_level": report["proof_level"],
                    "formal_slo_measured": 0,
                    "output_written": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "error",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
