from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from crypto_manual_alert.storage.journal import Journal


logger = logging.getLogger(__name__)


class JobLock:
    def __init__(self, journal: Journal, name: str, ttl: timedelta):
        self.journal = journal
        self.name = name
        self.ttl = ttl

    def acquire(self) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = now + self.ttl
        with self.journal.connect() as conn:
            existing = conn.execute("SELECT expires_at FROM job_locks WHERE name = ?", (self.name,)).fetchone()
            if existing:
                existing_expiry = datetime.fromisoformat(existing["expires_at"])
                if existing_expiry > now:
                    return False
            conn.execute(
                """
                INSERT OR REPLACE INTO job_locks (name, acquired_at, expires_at)
                VALUES (?, ?, ?)
                """,
                (self.name, now.isoformat(), expires_at.isoformat()),
            )
            return True

    def release(self) -> None:
        with self.journal.connect() as conn:
            conn.execute("DELETE FROM job_locks WHERE name = ?", (self.name,))


def run_scheduler(
    interval_seconds: int,
    lock: JobLock,
    job: Callable[[], None],
    run_on_start: bool = True,
    max_iterations: int = 0,
) -> None:
    iterations = 0
    if not run_on_start:
        time.sleep(interval_seconds)
    while True:
        if lock.acquire():
            try:
                job()
            except Exception:  # noqa: BLE001 - 定时器不能因单次任务失败而停止后续巡检
                logger.exception("scheduled job failed")
            finally:
                lock.release()
        iterations += 1
        if max_iterations and iterations >= max_iterations:
            return
        time.sleep(interval_seconds)
