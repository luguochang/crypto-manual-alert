"""Verify that Product release governance events reject mutation in PostgreSQL."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from crypto_alert_v2.config import get_settings


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        event_id = await connection.scalar(
            text(
                "SELECT id FROM app.improvement_release_events "
                "ORDER BY created_at LIMIT 1"
            )
        )
        if event_id is None:
            raise RuntimeError("no improvement release event is available")
        await connection.rollback()
        blocked = False
        try:
            async with connection.begin():
                await connection.execute(
                    text(
                        "UPDATE app.improvement_release_events "
                        "SET reason = reason WHERE id = :event_id"
                    ),
                    {"event_id": event_id},
                )
        except DBAPIError:
            blocked = True
            await connection.rollback()
        count = await connection.scalar(
            text("SELECT count(*) FROM app.improvement_release_events")
        )
    print(json.dumps({"mutation_blocked": blocked, "event_count": count}))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
