from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObservabilityRuntimeConfig:
    environment: str
    release: str
    langsmith_enabled: bool = False
    langsmith_api_key: str | None = field(default=None, repr=False)
    langsmith_project: str = "crypto-alert-v2"
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = field(default=None, repr=False)
    langfuse_host: str | None = None


def _secret_value(value: Any) -> str | None:
    if value is None:
        return None
    get_secret_value = getattr(value, "get_secret_value", None)
    if callable(get_secret_value):
        secret = get_secret_value()
        return secret if secret else None
    return str(value) or None


def runtime_config_from_settings(
    settings: Any,
    *,
    release: str,
) -> ObservabilityRuntimeConfig:
    return ObservabilityRuntimeConfig(
        environment=settings.app_environment,
        release=release,
        langsmith_enabled=settings.langsmith_tracing,
        langsmith_api_key=_secret_value(settings.langsmith_api_key),
        langsmith_project=settings.langsmith_project,
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_public_key=settings.langfuse_public_key,
        langfuse_secret_key=_secret_value(settings.langfuse_secret_key),
        langfuse_host=settings.langfuse_host,
    )
