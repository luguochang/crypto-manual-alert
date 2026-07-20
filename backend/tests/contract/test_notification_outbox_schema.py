from pathlib import Path

import pytest

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from crypto_alert_v2.persistence.models import NotificationAttempt, NotificationOutbox
from crypto_alert_v2.notifications.outbox import (
    SensitiveNotificationPayload,
    canonical_payload_hash,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_outbox_has_exact_logical_key_and_attempt_ledger() -> None:
    outbox = NotificationOutbox.__table__
    attempts = NotificationAttempt.__table__

    logical_keys = {
        tuple(constraint.columns.keys())
        for constraint in outbox.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert (
        "workspace_id",
        "task_id",
        "channel",
        "type",
        "decision_version",
    ) in logical_keys
    assert {"lease_owner", "lease_expires_at", "fence_token", "payload_hash"} <= set(
        outbox.columns.keys()
    )
    assert {
        "outbox_id",
        "attempt_number",
        "owner",
        "fence_token",
        "trigger",
        "reason",
        "delay_seconds",
        "retry_after_seconds",
        "cost_units",
        "result",
    } <= set(attempts.columns.keys())

    checks = {
        constraint.name
        for table in (outbox, attempts)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_notification_outbox_status" in checks
    assert "ck_notification_attempts_trigger" in checks
    assert "ck_notification_attempts_result" in checks

    outbox_foreign_keys = {
        constraint.name
        for constraint in outbox.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert {
        "fk_notification_outbox_task_scope",
        "fk_notification_outbox_run_scope",
        "fk_notification_outbox_artifact_scope",
        "fk_notification_outbox_artifact_version_scope",
        "fk_notification_outbox_decision_scope",
    } <= outbox_foreign_keys
    attempt_foreign_keys = {
        constraint.name
        for constraint in attempts.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert "fk_notification_attempts_outbox_scope" in attempt_foreign_keys


def test_notification_outbox_migration_is_next_revision() -> None:
    migration = (
        BACKEND_ROOT / "alembic" / "versions" / "0010_notification_outbox.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "0010_notification_outbox"' in migration
    assert 'down_revision = "0009_run_fork_lineage"' in migration
    assert '"notification_outbox"' in migration
    assert '"notification_attempts"' in migration


@pytest.mark.parametrize(
    "value",
    [
        "Authorization: Bearer secret-value",
        "api_key=secret-value",
        "bark_key=secret-value",
        "https://api.day.app/device-secret-value",
        "sk-provider-secret-value",
    ],
)
def test_notification_payload_rejects_secret_bearing_string_values(value: str) -> None:
    with pytest.raises(SensitiveNotificationPayload):
        canonical_payload_hash({"body": value})


def test_sensitive_payload_key_is_not_reflected_in_exception() -> None:
    canary = "api_key=must-never-be-reflected"

    with pytest.raises(SensitiveNotificationPayload) as captured:
        canonical_payload_hash({canary: "value"})

    assert canary not in str(captured.value)


def test_device_key_alias_is_rejected() -> None:
    with pytest.raises(SensitiveNotificationPayload):
        canonical_payload_hash({"device_key": "synthetic-device-secret"})
