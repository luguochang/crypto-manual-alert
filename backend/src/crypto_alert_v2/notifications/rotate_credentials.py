from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import tempfile

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.config import get_settings
from crypto_alert_v2.notifications.credentials import (
    notification_credential_cipher_from_environment,
)
from crypto_alert_v2.notifications.rotation import rotate_notification_credentials


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rewrap persisted notification credentials under the active key"
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=100_000)
    parser.add_argument("--inter-batch-delay-seconds", type=float, default=0)
    parser.add_argument("--output", type=Path)
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    credential_cipher = notification_credential_cipher_from_environment()
    if credential_cipher is None:
        raise ValueError("notification credential keyring is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        result = await rotate_notification_credentials(
            session_factory,
            credential_cipher=credential_cipher,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            inter_batch_delay_seconds=args.inter_batch_delay_seconds,
        )
    finally:
        await engine.dispose()
    return {
        "schema_version": "2026-07-17.notification-credential-rotation.v1",
        "status": "passed",
        "proof_level": "credential-rewrap-operation",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "active_key_version": result.active_key_version,
        "batches": result.batches,
        "scanned_rows": result.scanned_rows,
        "rewrapped_rows": result.rewrapped_rows,
        "remaining_old_version_rows": result.remaining_old_version_rows,
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    if not path.is_absolute():
        raise ValueError("rotation output path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    args = _parser().parse_args()
    try:
        report = asyncio.run(_run(args))
        if args.output is not None:
            _write_report(args.output, report)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": "2026-07-17.notification-credential-rotation.v1",
                    "status": "failed",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
