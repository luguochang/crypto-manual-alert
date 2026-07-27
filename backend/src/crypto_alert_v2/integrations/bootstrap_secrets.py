from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from crypto_alert_v2.atomic_io import atomic_write_text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize local Compose integration secrets into a private volume"
    )
    parser.add_argument("directory", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    key = os.getenv("NOTIFICATION_CREDENTIAL_KEY", "").strip()
    if not key:
        raise SystemExit("NOTIFICATION_CREDENTIAL_KEY is required")
    atomic_write_text(
        directory / "notification_credential_key",
        key + "\n",
        mode=0o600,
        sync_directory=True,
    )
    decrypt_keys = os.getenv("NOTIFICATION_CREDENTIAL_DECRYPT_KEYS", "").strip()
    if decrypt_keys:
        atomic_write_text(
            directory / "notification_credential_decrypt_keys",
            decrypt_keys + "\n",
            mode=0o600,
            sync_directory=True,
        )
    else:
        stale = directory / "notification_credential_decrypt_keys"
        if stale.exists():
            stale.unlink()
    print(
        json.dumps(
            {
                "status": "ready",
                "secret_names": [
                    "notification_credential_key",
                    *( ["notification_credential_decrypt_keys"] if decrypt_keys else [] ),
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
