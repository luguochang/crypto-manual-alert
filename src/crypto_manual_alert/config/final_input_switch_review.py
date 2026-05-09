from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crypto_manual_alert.config.models import ConfigError


def validate_final_input_switch_review_path(path: str) -> None:
    if not path.strip():
        raise ConfigError(
            "decision.final_input_mode=decision_input requires final_input_mode_switch_review_path"
        )
    review_path = Path(path)
    if not review_path.exists():
        raise ConfigError("final_input_mode_switch_review_path does not exist")
    try:
        artifact = json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError("final_input_mode_switch_review_path must contain JSON") from exc
    validate_final_input_switch_review_artifact(artifact)


def validate_final_input_switch_review_artifact(artifact: Any) -> None:
    if not isinstance(artifact, dict):
        raise ConfigError("final input switch review artifact must be a mapping")
    expected_fields = {
        "schema_version": 1,
        "artifact_type": "final_input_mode_switch_review",
        "decision_effect": "none",
        "allowed_to_change_production_final_input": True,
        "baseline_final_input_mode": "legacy_prompt",
        "target_final_input_mode": "decision_input",
        "release_gate_status": "ready",
        "promotion_review_status": "config_change_review_approved",
        "fallback_behavior": "legacy_prompt_on_candidate_failure",
        "manual_execution_required": True,
        "auto_order_enabled": False,
    }
    for field_name, expected in expected_fields.items():
        if artifact.get(field_name) != expected:
            raise ConfigError(f"final input switch review {field_name} is invalid")
    eval_run_id = artifact.get("eval_run_id")
    if not _non_empty(eval_run_id):
        raise ConfigError("final input switch review eval_run_id is required")
    artifact_ref = artifact.get("artifact_ref")
    if artifact_ref != f"eval:{eval_run_id}:final_input_mode_switch_review":
        raise ConfigError("final input switch review artifact_ref is invalid")
    for field_name in (
        "release_gate_ref",
        "config_change_review_approval_ref",
        "config_change_review_request_ref",
        "manual_release_decision_ref",
        "candidate_input_ref",
        "rollback_plan_ref",
        "rollback_target",
    ):
        if not _non_empty(artifact.get(field_name)):
            raise ConfigError(f"final input switch review {field_name} is required")
    for field_name in (
        "release_gate_hash",
        "config_change_review_approval_hash",
        "config_change_review_request_hash",
        "manual_release_decision_hash",
        "candidate_input_hash",
        "config_hash",
        "rollback_plan_hash",
    ):
        if not _hash_like(artifact.get(field_name)):
            raise ConfigError(f"final input switch review {field_name} is required")
    if artifact.get("rollback_target") != "config:decision.final_input_mode=legacy_prompt":
        raise ConfigError("final input switch review rollback_target is invalid")
    rollback_steps = artifact.get("rollback_steps")
    if not isinstance(rollback_steps, list) or not any(_non_empty(step) for step in rollback_steps):
        raise ConfigError("final input switch review rollback_steps are required")


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _hash_like(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and bool(value.removeprefix("sha256:").strip())
