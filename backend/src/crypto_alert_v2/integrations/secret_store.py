from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from typing import Mapping, Protocol

from pydantic import SecretStr


_SECRET_NAME = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


class SecretStore(Protocol):
    def get_secret(self, name: str) -> SecretStr | None: ...


def _validated_name(name: str) -> str:
    normalized = name.strip()
    if not _SECRET_NAME.fullmatch(normalized):
        raise ValueError("integration secret name is invalid")
    return normalized


class FileSecretStore:
    """Read deployment-managed secrets from one non-traversable directory."""

    def __init__(self, directory: Path, *, max_secret_bytes: int = 16_384) -> None:
        if max_secret_bytes < 1:
            raise ValueError("max_secret_bytes must be positive")
        self._directory = directory.resolve(strict=True)
        if not self._directory.is_dir():
            raise ValueError("integration secret directory is not a directory")
        self._max_secret_bytes = max_secret_bytes

    def get_secret(self, name: str) -> SecretStr | None:
        secret_name = _validated_name(name)
        path = self._directory / secret_name
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("integration secret must be a regular non-symlink file")
        if metadata.st_size < 1 or metadata.st_size > self._max_secret_bytes:
            raise ValueError("integration secret file size is invalid")
        resolved = path.resolve(strict=True)
        if resolved.parent != self._directory:
            raise ValueError("integration secret escaped its configured directory")
        try:
            value = resolved.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            raise ValueError("integration secret must be UTF-8 text") from None
        if not value:
            raise ValueError("integration secret is empty")
        return SecretStr(value)


class EnvironmentSecretStore:
    """Development-only adapter retained for local migration compatibility."""

    def __init__(self, variables: Mapping[str, str] | None = None) -> None:
        self._variables = dict(variables or os.environ)

    def get_secret(self, name: str) -> SecretStr | None:
        secret_name = _validated_name(name)
        variable = secret_name.upper()
        value = self._variables.get(variable, "").strip()
        return SecretStr(value) if value else None


def integration_secret_store_from_environment(
    *,
    app_environment: str,
) -> SecretStore:
    environment = app_environment.strip().lower()
    backend = os.getenv("INTEGRATION_SECRET_STORE", "").strip().lower()
    directory = os.getenv("INTEGRATION_SECRET_FILE_DIR", "").strip()
    if not backend:
        backend = "file" if directory else "environment"
    if backend == "file":
        if not directory:
            raise ValueError("INTEGRATION_SECRET_FILE_DIR is required for file secrets")
        return FileSecretStore(Path(directory))
    if backend == "environment":
        if environment in {"staging", "production"}:
            raise ValueError(
                "environment integration secrets are forbidden in staging and production"
            )
        return EnvironmentSecretStore()
    raise ValueError("INTEGRATION_SECRET_STORE must be file or environment")


__all__ = [
    "EnvironmentSecretStore",
    "FileSecretStore",
    "SecretStore",
    "integration_secret_store_from_environment",
]
