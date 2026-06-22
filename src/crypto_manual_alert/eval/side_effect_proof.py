from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.hashing import stable_hash


PRODUCTION_SIDE_EFFECT_TABLES = (
    "plan_runs",
    "notifications",
    "manual_outcomes",
    "traces",
    "trace_spans",
    "llm_interactions",
)


def build_no_production_side_effect_proof(
    *,
    eval_run_id: str,
    before_counts: dict[str, Any],
    after_counts: dict[str, Any],
    before_fingerprints: dict[str, Any],
    after_fingerprints: dict[str, Any],
    checked_tables: tuple[str, ...] = PRODUCTION_SIDE_EFFECT_TABLES,
) -> dict[str, Any]:
    """Build an audit artifact proving eval did not mutate production journal tables."""

    clean_before = _counts_for_tables(before_counts, checked_tables)
    clean_after = _counts_for_tables(after_counts, checked_tables)
    clean_before_fingerprints = _fingerprints_for_tables(before_fingerprints, checked_tables)
    clean_after_fingerprints = _fingerprints_for_tables(after_fingerprints, checked_tables)
    deltas = {
        table: clean_after[table] - clean_before[table]
        for table in checked_tables
    }
    fingerprint_deltas = {
        table: True
        for table in checked_tables
        if clean_before_fingerprints[table] != clean_after_fingerprints[table]
    }
    delta_changed = any(delta != 0 for delta in deltas.values())
    fingerprint_changed = bool(fingerprint_deltas)
    passed = not delta_changed and not fingerprint_changed
    return {
        "schema_version": 1,
        "artifact_type": "no_production_side_effect_proof",
        "artifact_ref": f"eval:{eval_run_id}:no_production_side_effect_proof",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "live_order_input": False,
        "passed": passed,
        "checked_tables": list(checked_tables),
        "before_counts": clean_before,
        "after_counts": clean_after,
        "deltas": deltas,
        "before_fingerprints": clean_before_fingerprints,
        "after_fingerprints": clean_after_fingerprints,
        "fingerprint_deltas": fingerprint_deltas,
        "blocking_reasons": _blocking_reasons(
            delta_changed=delta_changed,
            fingerprint_changed=fingerprint_changed,
        ),
    }


def _counts_for_tables(counts: dict[str, Any], tables: tuple[str, ...]) -> dict[str, int]:
    return {table: _required_count(counts, table) for table in tables}


def _fingerprints_for_tables(fingerprints: dict[str, Any], tables: tuple[str, ...]) -> dict[str, str]:
    return {table: _required_fingerprint(fingerprints, table) for table in tables}


def _required_count(counts: dict[str, Any], table: str) -> int:
    if table not in counts:
        raise ValueError(f"missing side-effect count for {table}")
    value = counts[table]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid side-effect count for {table}")
    return value


def _required_fingerprint(fingerprints: dict[str, Any], table: str) -> str:
    if table not in fingerprints:
        raise ValueError(f"missing side-effect fingerprint for {table}")
    value = fingerprints[table]
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"invalid side-effect fingerprint for {table}")
    return value


def _safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def validate_no_production_side_effect_proof(
    artifact: dict[str, Any] | None,
    *,
    eval_run_id: str | None,
) -> tuple[bool, list[str]]:
    if not isinstance(artifact, dict):
        return False, ["no_production_side_effect_proof_missing"]
    if not eval_run_id:
        return False, ["no_production_side_effect_proof_failed"]
    expected_tables = list(PRODUCTION_SIDE_EFFECT_TABLES)
    if (
        artifact.get("schema_version") != 1
        or artifact.get("artifact_type") != "no_production_side_effect_proof"
        or artifact.get("artifact_ref") != f"eval:{eval_run_id}:no_production_side_effect_proof"
        or artifact.get("eval_run_id") != eval_run_id
        or artifact.get("decision_effect") != "none"
        or artifact.get("production_final_input") is not False
        or artifact.get("notification_input") is not False
        or artifact.get("live_order_input") is not False
        or artifact.get("passed") is not True
        or artifact.get("blocking_reasons") != []
        or artifact.get("checked_tables") != expected_tables
    ):
        return False, ["no_production_side_effect_proof_failed"]
    if not _valid_count_maps(artifact):
        return False, ["no_production_side_effect_proof_failed"]
    if not _valid_fingerprint_maps(artifact):
        return False, ["no_production_side_effect_proof_failed"]
    return True, []


def _valid_count_maps(artifact: dict[str, Any]) -> bool:
    before = artifact.get("before_counts")
    after = artifact.get("after_counts")
    deltas = artifact.get("deltas")
    if not isinstance(before, dict) or not isinstance(after, dict) or not isinstance(deltas, dict):
        return False
    for table in PRODUCTION_SIDE_EFFECT_TABLES:
        if table not in before or table not in after or table not in deltas:
            return False
        before_count = before.get(table)
        after_count = after.get(table)
        delta = deltas.get(table)
        if (
            isinstance(before_count, bool)
            or isinstance(after_count, bool)
            or isinstance(delta, bool)
            or not isinstance(before_count, int)
            or not isinstance(after_count, int)
            or not isinstance(delta, int)
            or before_count < 0
            or after_count < 0
            or delta != after_count - before_count
            or delta != 0
        ):
            return False
    return True


def _valid_fingerprint_maps(artifact: dict[str, Any]) -> bool:
    before = artifact.get("before_fingerprints")
    after = artifact.get("after_fingerprints")
    deltas = artifact.get("fingerprint_deltas")
    if not isinstance(before, dict) or not isinstance(after, dict) or not isinstance(deltas, dict):
        return False
    if deltas:
        return False
    for table in PRODUCTION_SIDE_EFFECT_TABLES:
        before_value = before.get(table)
        after_value = after.get(table)
        if (
            not isinstance(before_value, str)
            or not isinstance(after_value, str)
            or not before_value.startswith("sha256:")
            or before_value != after_value
        ):
            return False
    return True


def fingerprint_rows(rows: list[dict[str, Any]]) -> str:
    return f"sha256:{stable_hash(rows)}"


def _blocking_reasons(*, delta_changed: bool, fingerprint_changed: bool) -> list[str]:
    if delta_changed:
        return ["production_side_effect_delta_detected"]
    if fingerprint_changed:
        return ["production_side_effect_fingerprint_changed"]
    return []
