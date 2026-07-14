from functools import lru_cache
from pathlib import Path
from typing import Literal

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
        "builtin_web_search", "tavily", "duckduckgo"
    ] = "builtin_web_search"
    market_data_http_proxy: str | None = None
    search_http_proxy: str | None = None
    product_database_url: str = "postgresql+asyncpg:///crypto_alert_v2"
    agent_server_url: str = "http://127.0.0.1:8123"
    agent_assistant_id: str = "crypto_analysis"
    agent_server_local_token: SecretStr | None = None
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
    development_bootstrap_tenant_id: str = ""
    development_bootstrap_workspace_id: str = ""
    development_bootstrap_roles: tuple[str, ...] = ()
    development_bootstrap_permissions: tuple[str, ...] = ()
    agent_healthcheck_subject: str = ""
    agent_healthcheck_tenant_id: str = ""
    agent_healthcheck_workspace_id: str = ""
    agent_healthcheck_roles: tuple[str, ...] = ()
    agent_healthcheck_permissions: tuple[str, ...] = ()
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None

    @field_validator("app_environment", mode="before")
    @classmethod
    def normalize_app_environment(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def load_internal_jwt_key_files(self) -> "Settings":
        if self.internal_jwt_private_key_file:
            self.internal_jwt_private_key = SecretStr(
                _read_key_file(self.internal_jwt_private_key_file)
            )
        if self.internal_jwt_public_key_file:
            if not self.internal_jwt_key_id:
                raise ValueError("INTERNAL_JWT_KID is required with a public key file")
            self.internal_jwt_public_keys = {
                self.internal_jwt_key_id: _read_key_file(
                    self.internal_jwt_public_key_file
                )
            }
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
    return Settings()
