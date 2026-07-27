from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path

import httpx


async def _sample(
    *,
    target: str,
    output: Path,
    requests: int,
    interval: float,
) -> None:
    if not target.startswith("http://") or target.rstrip("/").endswith("/health"):
        raise ValueError("target must be an HTTP service root without /health")
    if requests <= 0 or interval <= 0:
        raise ValueError("requests and interval must be positive")
    started_at = datetime.now(UTC).isoformat()
    successes = 0
    failures = 0
    consecutive = 0
    max_consecutive = 0
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=0)
    async with httpx.AsyncClient(timeout=2.0, limits=limits) as client:
        for _ in range(requests):
            try:
                response = await client.get(
                    target.rstrip("/") + "/health",
                    headers={"connection": "close"},
                )
                response.raise_for_status()
                successes += 1
                consecutive = 0
            except httpx.HTTPError:
                failures += 1
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            await asyncio.sleep(interval)
    payload = {
        "schema_version": "1.0",
        "target": target,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "requests": requests,
        "successes": successes,
        "failures": failures,
        "max_consecutive_failures": max_consecutive,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise AssertionError(f"HA service discovery had {failures} failed request(s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=600)
    parser.add_argument("--interval", type=float, default=0.1)
    arguments = parser.parse_args()
    asyncio.run(
        _sample(
            target=arguments.target,
            output=arguments.output,
            requests=arguments.requests,
            interval=arguments.interval,
        )
    )


if __name__ == "__main__":
    main()
