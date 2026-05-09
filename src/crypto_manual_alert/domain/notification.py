from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None
