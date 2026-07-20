from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import re
from typing import Any
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.persistence.models import NotificationAttempt, NotificationOutbox


_SENSITIVE_KEY_PARTS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bark_key",
        "barkkey",
        "cookie",
        "credential",
        "device_key",
        "devicekey",
        "password",
        "private_key",
        "secret",
        "token",
    }
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b(?:api[_ -]?key|access[_ -]?token|authorization|bark[_ -]?key|"
        r"client[_ -]?secret|cookie|device[_ -]?key|password|private[_ -]?key|"
        r"refresh[_ -]?token)"
        r"\b\s*[:=]\s*[\"']?[^\s\"',;}]+"
    ),
    re.compile(r"(?i)\b(?:sk|pk)-(?:lf-)?[a-z0-9_-]{8,}\b|\blsv2_[a-z0-9_-]{8,}\b"),
    re.compile(r"(?i)https?://api\.day\.app/(?!push(?:[/?#]|$))[^\s/?#]+"),
)


class NotificationPayloadConflict(RuntimeError):
    def __init__(
        self,
        *,
        notification_id: UUID,
        persisted_hash: str,
        attempted_hash: str,
    ) -> None:
        self.notification_id = notification_id
        self.persisted_hash = persisted_hash
        self.attempted_hash = attempted_hash
        super().__init__(
            "notification logical key already has a different payload hash"
        )


class SensitiveNotificationPayload(ValueError):
    pass


class NotificationLineageConflict(RuntimeError):
    def __init__(self, *, notification_id: UUID) -> None:
        self.notification_id = notification_id
        super().__init__(
            "notification logical key already has different immutable lineage"
        )


class NotificationNotResendable(RuntimeError):
    pass


class NotificationRetryBudgetExhausted(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NotificationPlan:
    notification: NotificationOutbox
    created: bool


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    _validate_payload(payload)
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("notification payload must be canonical JSON") from exc
    return sha256(encoded).hexdigest()


async def plan_notification(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    owner_user_id: UUID,
    task_id: UUID,
    run_id: UUID,
    artifact_id: UUID,
    artifact_version_id: UUID,
    decision_id: UUID,
    decision_version: int,
    destination_id: UUID | None = None,
    channel: str,
    notification_type: str,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> NotificationPlan:
    normalized_channel = _required_identifier(channel, name="channel", max_length=64)
    normalized_type = _required_identifier(
        notification_type, name="notification_type", max_length=128
    )
    if decision_version < 1:
        raise ValueError("decision_version must be positive")
    payload_copy = _json_copy(payload)
    payload_hash = canonical_payload_hash(payload_copy)
    planned_at = _aware_utc(now or datetime.now(UTC))
    notification_id = uuid4()
    values = {
        "id": notification_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "owner_user_id": owner_user_id,
        "task_id": task_id,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "artifact_version_id": artifact_version_id,
        "decision_id": decision_id,
        "decision_version": decision_version,
        "destination_id": destination_id,
        "channel": normalized_channel,
        "type": normalized_type,
        "payload": payload_copy,
        "payload_hash": payload_hash,
        "status": "planned",
        "available_at": planned_at,
        "attempt_count": 0,
        "fence_token": 0,
        "created_at": planned_at,
        "updated_at": planned_at,
    }
    inserted_id = await session.scalar(
        insert(NotificationOutbox)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[
                NotificationOutbox.workspace_id,
                NotificationOutbox.task_id,
                NotificationOutbox.channel,
                NotificationOutbox.type,
                NotificationOutbox.decision_version,
            ]
        )
        .returning(NotificationOutbox.id)
    )
    if inserted_id is not None:
        notification = await session.get(NotificationOutbox, inserted_id)
        if notification is None:
            raise RuntimeError("inserted notification could not be loaded")
        return NotificationPlan(notification=notification, created=True)

    notification = await session.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.workspace_id == workspace_id,
            NotificationOutbox.task_id == task_id,
            NotificationOutbox.channel == normalized_channel,
            NotificationOutbox.type == normalized_type,
            NotificationOutbox.decision_version == decision_version,
        )
    )
    if notification is None:
        raise RuntimeError("notification conflict row could not be loaded")
    attempted_lineage = {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "owner_user_id": owner_user_id,
        "task_id": task_id,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "artifact_version_id": artifact_version_id,
        "decision_id": decision_id,
        "decision_version": decision_version,
        "destination_id": destination_id,
    }
    if any(
        getattr(notification, field) != attempted
        for field, attempted in attempted_lineage.items()
    ):
        raise NotificationLineageConflict(notification_id=notification.id)
    if notification.payload_hash != payload_hash:
        raise NotificationPayloadConflict(
            notification_id=notification.id,
            persisted_hash=notification.payload_hash,
            attempted_hash=payload_hash,
        )
    return NotificationPlan(notification=notification, created=False)


async def request_manual_resend(
    session: AsyncSession,
    *,
    notification_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    owner_user_id: UUID,
    requested_by: str,
    reason: str,
    now: datetime | None = None,
) -> NotificationOutbox | None:
    actor = _required_text(requested_by, name="requested_by", max_length=255)
    normalized_reason = _required_text(reason, name="reason", max_length=500)
    requested_at = _aware_utc(now or datetime.now(UTC))
    notification = await session.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.id == notification_id,
            NotificationOutbox.tenant_id == tenant_id,
            NotificationOutbox.workspace_id == workspace_id,
            NotificationOutbox.owner_user_id == owner_user_id,
        )
        .with_for_update()
    )
    if notification is None:
        return None
    if notification.status not in {
        "unknown",
        "failed_retryable",
        "failed_terminal",
    }:
        raise NotificationNotResendable(
            f"notification status {notification.status!r} cannot be manually resent"
        )
    if notification.manual_resend_requested_at is not None:
        raise NotificationNotResendable(
            "notification already has a manual resend request"
        )
    prior_manual_attempt = await session.scalar(
        select(NotificationAttempt.id)
        .where(
            NotificationAttempt.outbox_id == notification.id,
            NotificationAttempt.trigger == "manual",
        )
        .limit(1)
    )
    if prior_manual_attempt is not None:
        raise NotificationNotResendable(
            "notification already used its one manual resend"
        )
    if (
        notification.attempt_count >= 5
        or notification.created_at <= requested_at - timedelta(hours=24)
    ):
        raise NotificationRetryBudgetExhausted(
            "notification reached the five-attempt or 24-hour retry limit"
        )
    notification.manual_resend_requested_at = requested_at
    notification.manual_resend_requested_by = actor
    notification.manual_resend_reason = normalized_reason
    notification.updated_at = requested_at
    await session.flush()
    return notification


def _validate_payload(value: Any, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, SecretStr):
        raise SensitiveNotificationPayload(
            f"SecretStr is forbidden in notification payload at {_path(path)}"
        )
    if isinstance(value, Mapping):
        for key, member in value.items():
            if not isinstance(key, str):
                raise ValueError("notification payload object keys must be strings")
            normalized_key = key.strip().lower().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                raise SensitiveNotificationPayload(
                    "sensitive field is forbidden in notification payload at "
                    f"{_path(path)}.<sensitive-field>"
                )
            _validate_payload(member, path=(*path, key))
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, member in enumerate(value):
            _validate_payload(member, path=(*path, str(index)))
        return
    if isinstance(value, str) and any(
        pattern.search(value) for pattern in _SENSITIVE_VALUE_PATTERNS
    ):
        raise SensitiveNotificationPayload(
            f"sensitive value is forbidden in notification payload at {_path(path)}"
        )


def _json_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    _validate_payload(payload)
    try:
        return json.loads(
            json.dumps(
                payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("notification payload must contain only JSON values") from exc


def _required_identifier(value: str, *, name: str, max_length: int) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{name} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{name} exceeds {max_length} characters")
    return normalized


def _required_text(value: str, *, name: str, max_length: int) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > max_length
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise ValueError(f"{name} is invalid")
    return normalized


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("notification timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _path(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "<root>"


__all__ = [
    "NotificationPayloadConflict",
    "NotificationLineageConflict",
    "NotificationNotResendable",
    "NotificationPlan",
    "NotificationRetryBudgetExhausted",
    "SensitiveNotificationPayload",
    "canonical_payload_hash",
    "plan_notification",
    "request_manual_resend",
]
