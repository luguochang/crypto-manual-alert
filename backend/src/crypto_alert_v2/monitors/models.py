from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _parse_uuid_reference(value: object) -> object:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError as exc:
            raise ValueError("monitor references must be UUIDs") from exc
    return value


class MonitorIngressRequest(BaseModel):
    """The complete data plane allowed to cross the Cron-to-Graph boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_type: Literal["monitor_ingress"] = "monitor_ingress"
    monitor_id: UUID
    schedule_version: int = Field(ge=1)
    cron_binding_id: UUID

    @field_validator("monitor_id", "cron_binding_id", mode="before")
    @classmethod
    def parse_uuid_references(cls, value: object) -> object:
        return _parse_uuid_reference(value)

    def reference_metadata(self) -> dict[str, str | int]:
        return {
            "monitor_id": str(self.monitor_id),
            "schedule_version": self.schedule_version,
            "cron_binding_id": str(self.cron_binding_id),
        }


class MonitorCronSpec(BaseModel):
    """Product-owned scheduling references needed by the official Cron API."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    monitor_id: UUID
    schedule_version: int = Field(ge=1)
    cron_binding_id: UUID
    schedule: str = Field(min_length=1, max_length=128)
    timezone: str = Field(min_length=1, max_length=64)
    end_time: datetime | None = None

    @field_validator("monitor_id", "cron_binding_id", mode="before")
    @classmethod
    def parse_uuid_references(cls, value: object) -> object:
        return _parse_uuid_reference(value)

    @field_validator("schedule", "timezone")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "Cron schedule and timezone cannot contain outer whitespace"
            )
        return value

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA zone") from exc
        return value

    @field_validator("end_time")
    @classmethod
    def require_aware_end_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("end_time must be timezone-aware")
        return value

    def ingress_request(self) -> MonitorIngressRequest:
        return MonitorIngressRequest(
            monitor_id=self.monitor_id,
            schedule_version=self.schedule_version,
            cron_binding_id=self.cron_binding_id,
        )

    def cron_input(self) -> dict[str, dict[str, str | int]]:
        return {
            "request": self.ingress_request().model_dump(mode="json"),
        }

    def reference_metadata(self) -> dict[str, str | int]:
        return self.ingress_request().reference_metadata()


__all__ = ["MonitorCronSpec", "MonitorIngressRequest"]
