# V2 依赖清单与测试 Fixtures

> 日期：2026-07-12
>
> 目的：提供精确的依赖版本和测试 fixtures 设计，确保 AI 实现时不需要选择版本

---

## 一、backend/pyproject.toml

```toml
[project]
name = "crypto-alert-v2"
version = "2.0.0"
description = "Crypto Intelligence Agent - V2 Production"
requires-python = ">=3.12"
dependencies = [
    # === LangChain 生态 ===
    "langchain>=0.3.0,<0.4",                    # 核心框架
    "langchain-openai>=0.2.0,<0.3",            # OpenAI 集成
    "langgraph>=0.2.40,<0.3",                  # Agent 运行时
    "langgraph-sdk>=0.1.33,<0.2",              # 客户端 SDK
    "langsmith>=0.2.0,<0.3",                   # 追踪和评测

    # === Deep Agents (pre-1.0) ===
    "langchain-deepagents>=0.0.50,<0.1",       # 研究子图

    # === 数据库 ===
    "sqlalchemy>=2.0.35,<3.0",                 # ORM
    "alembic>=1.13.0,<2.0",                    # 迁移工具
    "asyncpg>=0.30.0,<1.0",                    # PostgreSQL async 驱动
    "psycopg2-binary>=2.9.9,<3.0",             # PostgreSQL sync 驱动

    # === 缓存 ===
    "redis>=5.0.0,<6.0",                       # Redis 客户端
    "hiredis>=2.3.0,<3.0",                     # 加速 Redis 解析

    # === Web 框架 ===
    "fastapi>=0.115.0,<1.0",                   # Web 框架
    "uvicorn[standard]>=0.32.0,<1.0",          # ASGI 服务器
    "httpx>=0.27.0,<1.0",                      # HTTP 客户端
    "pydantic>=2.9.0,<3.0",                    # 数据校验
    "pydantic-settings>=2.5.0,<3.0",           # 配置管理

    # === 工具 ===
    "tavily-python>=0.5.0,<1.0",               # Web 搜索

    # === 可观测性 ===
    "langfuse>=2.52.0,<3.0",                   # 生产追踪
    "structlog>=24.4.0,<25.0",                 # 结构化日志

    # === 其他 ===
    "python-dateutil>=2.9.0,<3.0",             # 日期处理
]

[project.optional-dependencies]
dev = [
    # === 测试 ===
    "pytest>=8.3.0,<9.0",
    "pytest-asyncio>=0.24.0,<1.0",
    "pytest-cov>=5.0.0,<6.0",
    "pytest-mock>=3.14.0,<4.0",
    "faker>=30.0.0,<31.0",                     # 生成测试数据

    # === 代码质量 ===
    "ruff>=0.7.0,<1.0",                        # Linter + Formatter
    "mypy>=1.13.0,<2.0",                       # 类型检查

    # === 调试 ===
    "ipython>=8.29.0,<9.0",
    "ipdb>=0.13.13,<1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = [
    "--cov=src/crypto_alert_v2",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-report=xml",
    "-v",
]
markers = [
    "unit: 领域单元测试（无网络、无DB、无模型）",
    "graph: Graph Contract 测试",
    "agent: Agent Contract 测试（使用 FakeChatModel）",
    "integration: 集成测试（需要 PostgreSQL/Redis）",
    "eval: 评测测试（需要 LangSmith Dataset）",
    "real_provider: 真实 Provider 测试（需要 API Key）",
    "slow: 慢速测试（>5s）",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]  # line-too-long（由 formatter 处理）

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

---

## 二、测试 Fixtures 设计

### 2.1 backend/tests/conftest.py

```python
"""全局测试 fixtures"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from faker import Faker
from httpx import AsyncClient
from langchain_core.language_models.fake_chat_models import FakeChatModel
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from crypto_alert_v2.domain.models import Base
from crypto_alert_v2.domain.state import AnalysisState

fake = Faker()

# === 数据库 Fixtures ===

@pytest.fixture(scope="session")
def test_db_url() -> str:
    """测试数据库 URL（每个 session 独立数据库）"""
    db_name = f"test_crypto_alert_{uuid.uuid4().hex[:8]}"
    return f"postgresql://agent:agent@localhost:5432/{db_name}"


@pytest.fixture(scope="session")
def test_engine(test_db_url):
    """同步测试引擎"""
    engine = create_engine(test_db_url, echo=False)

    # 创建数据库
    Base.metadata.create_all(engine)

    yield engine

    # 清理
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_async_engine(test_db_url):
    """异步测试引擎"""
    async_url = test_db_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(async_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def test_db(test_engine) -> Generator[Session, None, None]:
    """同步测试数据库会话（事务回滚）"""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest_asyncio.fixture
async def test_async_db(test_async_engine) -> AsyncGenerator[AsyncSession, None]:
    """异步测试数据库会话（事务回滚）"""
    async with test_async_engine.connect() as connection:
        async with connection.begin() as transaction:
            session = sessionmaker(
                bind=connection, class_=AsyncSession, expire_on_commit=False
            )()

            yield session

            await session.close()
            await transaction.rollback()


# === Mock Provider Fixtures ===

@pytest.fixture
def mock_okx_api(monkeypatch):
    """Mock OKX API 响应"""
    responses = {
        "ticker": {
            "code": "0",
            "data": [{
                "instId": "BTC-USDT-SWAP",
                "last": "67200.5",
                "bidPx": "67200.0",
                "askPx": "67201.0",
                "vol24h": "123456",
                "ts": "1720800000000",
            }]
        },
        "mark-price": {
            "code": "0",
            "data": [{
                "instId": "BTC-USDT-SWAP",
                "markPx": "67201.2",
                "ts": "1720800000000",
            }]
        },
        "funding-rate": {
            "code": "0",
            "data": [{
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "0.00012",
                "nextFundingRate": "0.00015",
                "fundingTime": "1720800000000",
            }]
        },
    }

    async def mock_get(url, **kwargs):
        class MockResponse:
            def __init__(self, json_data):
                self._json = json_data
                self.status_code = 200

            def json(self):
                return self._json

            def raise_for_status(self):
                pass

        # 根据 URL 返回对应数据
        for key in responses:
            if key in url:
                return MockResponse(responses[key])

        return MockResponse({"code": "0", "data": []})

    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
    return responses


@pytest.fixture
def mock_llm():
    """Mock LLM（FakeChatModel）"""
    return FakeChatModel(
        responses=[
            # 第一次调用返回分析结果
            '{"main_action": "open_long", "direction": "long", "entry_trigger": 67100.0, "stop_price": 66500.0, "target_1": 68500.0, "probability": 0.62, "factor_scores": {"btc_structure": 2, "macro_bridge": 1}, "total_score": 5}',
            # 第二次调用返回其他响应
            "Research completed",
        ]
    )


@pytest.fixture
def mock_tavily(monkeypatch):
    """Mock Tavily 搜索"""
    async def mock_search(query, **kwargs):
        return {
            "results": [
                {
                    "title": "BTC ETF Inflows Surge",
                    "url": "https://example.com/news1",
                    "content": "Bitcoin ETF saw $125M inflows...",
                    "score": 0.95,
                },
                {
                    "title": "Fed Minutes Released",
                    "url": "https://example.com/news2",
                    "content": "Federal Reserve minutes indicate...",
                    "score": 0.88,
                },
            ]
        }

    monkeypatch.setattr("tavily.TavilyClient.search", mock_search)


# === Sample Data Fixtures ===

@pytest.fixture
def sample_tenant_id() -> uuid.UUID:
    """样本租户 ID"""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """样本用户 ID"""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_thread_id() -> str:
    """样本 Thread ID"""
    return f"thread_{uuid.uuid4().hex[:16]}"


@pytest.fixture
def sample_run_id() -> uuid.UUID:
    """样本 Run ID"""
    return uuid.uuid4()


@pytest.fixture
def sample_market_snapshot() -> dict:
    """样本市场快照"""
    now = datetime.utcnow()
    return {
        "symbol": "BTC-USDT-SWAP",
        "ticker": {
            "last": 67200.5,
            "bid": 67200.0,
            "ask": 67201.0,
            "vol_24h": 123456.78,
        },
        "mark_price": 67201.2,
        "index_price": 67205.0,
        "funding_rate": 0.00012,
        "open_interest": 1234567890.0,
        "order_book": {
            "bids": [[67200.0, 10.5], [67199.5, 8.2]],
            "asks": [[67201.0, 12.3], [67201.5, 9.1]],
        },
        "candles": [
            {"ts": now - timedelta(hours=4), "o": 66800, "h": 67300, "l": 66700, "c": 67200, "vol": 50000},
            {"ts": now - timedelta(hours=3), "o": 67200, "h": 67400, "l": 67100, "c": 67250, "vol": 48000},
        ],
        "data_fetched_at": now,
        "source_level": "exchange_native",
        "unavailable_fields": [],
    }


@pytest.fixture
def sample_analysis_result() -> dict:
    """样本分析结果"""
    return {
        "main_action": "open_long",
        "direction": "long",
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "entry_trigger": 67100.0,
        "stop_price": 66500.0,
        "target_1": 68500.0,
        "target_2": 70000.0,
        "probability": 0.62,
        "position_size_class": "light",
        "max_leverage": 2,
        "risk_pct": 0.02,
        "regime": "risk_on",
        "factor_scores": {
            "btc_structure": 2,
            "macro_bridge": 1,
            "derivatives": 1,
        },
        "total_score": 5,
        "root_cause_chain": ["ETF inflows", "OI growth", "New leveraged longs"],
        "why_not_opposite": "Funding rate positive, invalidates if below 66500",
        "invalidation": "BTC breaks below 66500",
        "unavailable_data": [],
        "manual_execution_required": True,
        "expires_at": datetime.utcnow() + timedelta(seconds=90),
    }


@pytest.fixture
def sample_state(sample_thread_id, sample_user_id, sample_tenant_id) -> AnalysisState:
    """样本 Graph State"""
    return {
        "messages": [],
        "thread_id": sample_thread_id,
        "user_id": str(sample_user_id),
        "tenant_id": str(sample_tenant_id),
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "query_text": "分析 BTC 4h 趋势",
        "market_snapshot": None,
        "research_bundle": None,
        "decision_draft": None,
        "evidence_verdict": None,
        "risk_verdict": None,
        "final_result": None,
        "errors": [],
        "warnings": [],
    }


# === HTTP Client Fixture ===

@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """异步 HTTP 客户端"""
    async with AsyncClient(base_url="http://test", timeout=10.0) as client:
        yield client


# === Redis Mock Fixture ===

@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis 客户端"""
    cache = {}

    class MockRedis:
        async def get(self, key):
            return cache.get(key)

        async def set(self, key, value, ex=None):
            cache[key] = value

        async def delete(self, key):
            cache.pop(key, None)

        async def close(self):
            pass

    return MockRedis()
```

---

## 三、版本锁定策略

### 3.1 uv.lock 生成

```bash
# 初始化项目
uv init

# 从 pyproject.toml 生成锁文件
uv lock

# 安装依赖
uv sync

# 安装开发依赖
uv sync --group dev
```

### 3.2 CI 中的依赖验证

```yaml
# .github/workflows/ci.yml 片段
- name: Install dependencies
  run: |
    pip install uv
    uv sync --frozen  # 严格按照 uv.lock 安装，版本不匹配则失败
```

---

## 四、依赖更新策略

| 场景 | 命令 | 说明 |
|------|------|------|
| 安全补丁 | `uv lock --upgrade-package package_name` | 只升级指定包 |
| 次版本升级 | `uv lock --upgrade` | 升级所有兼容版本 |
| 主版本升级 | 手动修改 pyproject.toml 后 `uv lock` | 需要回归测试 |
| 查看过期 | `uv pip list --outdated` | 检查可升级的包 |

---

## 五、特殊依赖说明

### 5.1 langchain-deepagents (pre-1.0)

Deep Agents 在 pre-1.0 阶段，API 可能变更。V2 通过 `ResearchBundle` 契约隔离依赖，即使 Deep Agents 升级导致 breaking change，只需修改研究子图，不影响主图。

**降级方案**：如果 Deep Agents 不可用，改用 `create_agent` + Tavily 直接搜索，不使用子代理委派。

### 5.2 asyncpg vs psycopg2-binary

- `asyncpg`：异步 PostgreSQL 驱动，用于 Agent Server 和 Graph 节点
- `psycopg2-binary`：同步驱动，用于 Alembic 迁移和测试

两者并存，各司其职。
