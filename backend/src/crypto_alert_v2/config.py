from functools import lru_cache
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


AppEnvironment = Literal[
    "development",
    "local",
    "test",
    "staging",
    "production",
]
STRICT_SEARCH_READINESS_ENVIRONMENTS = frozenset({"staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_environment: AppEnvironment
    model_name: str = "gpt-5.5"
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    tavily_api_key: SecretStr | None = None
    search_provider: Literal[
        "builtin_web_search",
        "tavily",
        "ddgs_metasearch",
    ] = "builtin_web_search"
    deep_research_harness_mode: Literal["deepagents", "langchain"] = "deepagents"
    market_data_http_proxy: str | None = None
    search_http_proxy: str | None = None
    product_database_url: str = "postgresql+asyncpg:///crypto_alert_v2"
    agent_server_url: str = "http://127.0.0.1:8123"
    agent_assistant_id: str = "crypto_analysis"
    worker_health_host: str = "127.0.0.1"
    worker_health_port: int = Field(default=9090, ge=1, le=65535)
    worker_readiness_failure_threshold: int = Field(default=3, ge=1, le=20)
    worker_readiness_stale_after_seconds: float = Field(default=30.0, gt=0, le=600)
    worker_readiness_url: str | None = None
    agent_readiness_url: str | None = None
    agent_readiness_host: str = "127.0.0.1"
    agent_readiness_port: int = Field(default=9091, ge=1, le=65535)
    agent_readiness_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    agent_readiness_probe_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    agent_readiness_failure_threshold: int = Field(default=3, ge=1, le=20)
    agent_readiness_stale_after_seconds: float = Field(default=30.0, gt=0, le=600)
    agent_server_local_token: SecretStr | None = None
    product_inbox_cursor_key: SecretStr | None = None
    product_inbox_cursor_key_file: str | None = None
    internal_jwt_public_keys: dict[str, str] = Field(default_factory=dict)
    internal_jwt_private_key: SecretStr | None = None
    internal_jwt_public_key_file: str | None = None
    internal_jwt_private_key_file: str | None = None
    internal_jwt_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_JWT_KID", "INTERNAL_JWT_KEY_ID"),
    )
    internal_jwt_issuer: str = "http://127.0.0.1:3103"
    internal_jwt_audience: str = "crypto-alert-product-api"
    agent_server_internal_jwt_audience: str = "crypto-alert-agent-server"
    internal_jwt_max_ttl_seconds: int = Field(default=60, ge=1, le=60)
    development_bootstrap_enabled: bool = False
    development_bootstrap_profile: str = ""
    development_bootstrap_subject: str = ""
    development_bootstrap_identity_issuer: str = "crypto-alert-v2-development"
    development_bootstrap_context_id: UUID | None = None
    development_bootstrap_tenant_id: str = ""
    development_bootstrap_workspace_id: str = ""
    development_bootstrap_roles: tuple[str, ...] = ()
    development_bootstrap_permissions: tuple[str, ...] = ()
    agent_healthcheck_subject: str = ""
    agent_healthcheck_tenant_id: str = ""
    agent_healthcheck_workspace_id: str = ""
    agent_healthcheck_roles: tuple[str, ...] = ()
    agent_healthcheck_permissions: tuple[str, ...] = ()

    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "crypto-alert-v2"
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None
    observability_verification_lease_seconds: int = Field(default=30, ge=3, le=300)
    observability_verification_deadline_seconds: int = Field(
        default=3_600,
        ge=30,
        le=86_400,
    )
    observability_verification_retry_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=300.0,
    )
    observability_verification_max_attempts: int = Field(default=30, ge=1, le=1000)

    monitor_cron_lease_seconds: int = Field(default=30, ge=3, le=300)
    monitor_cron_retry_seconds: float = Field(default=5.0, ge=0.1, le=300.0)
    monitor_cron_max_attempts: int = Field(default=10, ge=1, le=100)

    failure_injection_enabled: bool = False
    failure_injection_profile: Literal["", "task12"] = ""
    failure_injection_scenario_file: str | None = None
    failure_injection_control_token: SecretStr | None = None

    # Compatibility fields retained for staged provider and worker rollout.
    okx_base_url: str = "https://www.okx.com"
    bark_key: SecretStr | None = None
    postgres_uri: str | None = None
    redis_uri: str | None = None
    auth_mode: str | None = None
    dev_tenant_id: str | None = None
    dev_user_id: str | None = None

    @field_validator("app_environment", mode="before")
    @classmethod
    def normalize_app_environment(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "openai_base_url",
        "market_data_http_proxy",
        "search_http_proxy",
        "worker_readiness_url",
        "agent_readiness_url",
        "langfuse_host",
        "failure_injection_scenario_file",
        "postgres_uri",
        "redis_uri",
        "auth_mode",
        "dev_tenant_id",
        "dev_user_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_string(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator(
        "openai_api_key",
        "tavily_api_key",
        "agent_server_local_token",
        "product_inbox_cursor_key",
        "internal_jwt_private_key",
        "langsmith_api_key",
        "langfuse_secret_key",
        "failure_injection_control_token",
        "bark_key",
        mode="before",
    )
    @classmethod
    def normalize_optional_secret(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            normalized = value.get_secret_value().strip()
            return SecretStr(normalized) if normalized else None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_search_provider_environment(self) -> "Settings":
        if (
            self.app_environment in STRICT_SEARCH_READINESS_ENVIRONMENTS
            and self.search_provider == "ddgs_metasearch"
        ):
            raise ValueError(
                "SEARCH_PROVIDER=ddgs_metasearch is allowed only in "
                "development, local, and test"
            )
        if self.search_provider == "tavily" and self.tavily_api_key is None:
            raise ValueError("TAVILY_API_KEY is required when SEARCH_PROVIDER=tavily")
        return self

    @model_validator(mode="after")
    def load_internal_jwt_key_files(self) -> "Settings":
        if self.product_inbox_cursor_key_file:
            cursor_key = Path(self.product_inbox_cursor_key_file).read_text().strip()
            if not cursor_key:
                raise ValueError("Product Inbox cursor key file is empty")
            self.product_inbox_cursor_key = SecretStr(cursor_key)
        if self.internal_jwt_private_key_file:
            self.internal_jwt_private_key = SecretStr(
                _read_key_file(self.internal_jwt_private_key_file)
            )
        if self.internal_jwt_public_key_file:
            if not self.internal_jwt_key_id:
                raise ValueError("INTERNAL_JWT_KID is required with a public key file")
            file_key = _read_key_file(self.internal_jwt_public_key_file)
            configured_keys = dict(self.internal_jwt_public_keys)
            configured_key = configured_keys.get(self.internal_jwt_key_id)
            if configured_key is not None and configured_key != file_key:
                raise ValueError(
                    "INTERNAL_JWT_PUBLIC_KEYS contains conflicting key material "
                    f"for kid {self.internal_jwt_key_id!r}"
                )
            configured_keys[self.internal_jwt_key_id] = file_key
            self.internal_jwt_public_keys = configured_keys
        return self

    @model_validator(mode="after")
    def validate_failure_injection_profile(self) -> "Settings":
        if not self.failure_injection_enabled:
            return self
        if self.app_environment not in {"development", "local", "test"}:
            raise ValueError(
                "failure injection is allowed only in non-production local profiles"
            )
        if self.failure_injection_profile != "task12":
            raise ValueError("failure injection profile must be task12")
        if not self.failure_injection_scenario_file:
            raise ValueError("failure injection scenario file is required")
        if not Path(self.failure_injection_scenario_file).is_absolute():
            raise ValueError("failure injection scenario file must be absolute")
        if (
            self.failure_injection_control_token is None
            or not self.failure_injection_control_token.get_secret_value().strip()
        ):
            raise ValueError("failure injection control token is required")
        return self

    @model_validator(mode="after")
    def validate_observability_credentials(self) -> "Settings":
        if self.langsmith_tracing and self.langsmith_api_key is None:
            raise ValueError("LANGSMITH_API_KEY is required when tracing is enabled")
        if self.langfuse_enabled and (
            not self.langfuse_public_key or self.langfuse_secret_key is None
        ):
            raise ValueError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when "
                "Langfuse is enabled"
            )
        return self


def requires_search_readiness(environment: AppEnvironment) -> bool:
    return environment in STRICT_SEARCH_READINESS_ENVIRONMENTS


def _read_key_file(path: str) -> str:
    value = Path(path).read_text()
    if not value.strip():
        raise ValueError(f"internal JWT key file is empty: {path}")
    return value


@lru_cache
def get_settings() -> Settings:
    env_file = None if os.environ.get("CRYPTO_ALERT_DISABLE_DOTENV") == "1" else ".env"
    return Settings(_env_file=env_file)
