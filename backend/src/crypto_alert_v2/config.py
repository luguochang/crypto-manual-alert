"""应用配置 - 使用 pydantic-settings 从环境变量读取。

langgraph.json 的 "env": ".env" 让 Agent Server 加载 .env 到环境变量，
Settings 类再从环境变量读取。两步配合，不冲突。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 文件读取。

    所有字段都有默认值，确保在没有 .env 的环境下也能启动（Phase 0 骨架测试）。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 模型 ===
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o"

    # === LangSmith ===
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "crypto-alert-v2"

    # === Langfuse ===
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"

    # === Tavily（Web Search 降级方案）===
    tavily_api_key: str = ""

    # === OKX ===
    okx_base_url: str = "https://www.okx.com"

    # === Bark 通知 ===
    bark_key: str = ""

    # === PostgreSQL ===
    postgres_uri: str = "postgresql://agent:agent@localhost:5432/crypto_alert"

    # === Redis ===
    redis_uri: str = "redis://localhost:6379"

    # === Auth（Phase 0 开发模式，设计文档 9.1 节）===
    auth_mode: str = "development"
    dev_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"


# 单例：模块级导入即可使用
settings = Settings()
