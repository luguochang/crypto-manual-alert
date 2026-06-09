from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceFreshness:
    """Classify whether a retrieved source is fresh enough for decision input."""

    retrieved_at: datetime | None
    now: datetime
    max_age_seconds: int

    @property
    def status(self) -> str:
        if self.retrieved_at is None:
            return "unknown"
        age_seconds = (self.now - self.retrieved_at).total_seconds()
        if age_seconds <= self.max_age_seconds:
            return "fresh"
        return "stale"

    def __post_init__(self) -> None:
        if type(self.max_age_seconds) is not int or self.max_age_seconds < 1:
            raise ValueError("max_age_seconds must be a positive integer")
