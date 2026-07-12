# V2 前端与配置管理实现细节

> 日期：2026-07-12
>
> 目的：提供前端组件接口、Custom Channel Schema、配置管理和数据生命周期策略

---

## 一、前端组件 Props 接口

### 1.1 核心类型定义

```typescript
// frontend/src/types/analysis.ts

import type { Message } from "@langchain/react";

/** 市场快照 */
export interface MarketSnapshot {
  symbol: string;
  ticker: {
    last: number;
    bid: number;
    ask: number;
    vol_24h: number;
  };
  mark_price: number;
  index_price: number;
  funding_rate: number;
  open_interest: number;
  order_book: {
    bids: [number, number][];  // [price, size]
    asks: [number, number][];
  };
  candles: Array<{
    ts: string;
    o: number;
    h: number;
    l: number;
    c: number;
    vol: number;
  }>;
  data_fetched_at: string;
  source_level: "exchange_native" | "web_derived";
  unavailable_fields: string[];
}

/** 分析结果 */
export interface AnalysisResult {
  main_action: "open_long" | "open_short" | "hold_long" | "hold_short" |
               "close_long" | "close_short" | "flip_long_to_short" |
               "flip_short_to_long" | "trigger_long" | "trigger_short" | "no_trade";
  direction: "long" | "short" | "neutral";
  symbol: string;
  horizon: string;
  reference_price: number;
  entry_trigger: number | null;
  stop_price: number | null;
  target_1: number | null;
  target_2: number | null;
  probability: number;
  position_size_class: "light" | "standard" | "heavy";
  max_leverage: number;
  risk_pct: number;
  regime: "risk_on" | "risk_off" | "event_compression" | "surprise_repricing";
  factor_scores: Record<string, number>;
  total_score: number;
  root_cause_chain: string[];
  why_not_opposite: string;
  invalidation: string;
  unavailable_data: string[];
  manual_execution_required: boolean;
  expires_at: string;
}

/** 证据项 */
export interface EvidenceItem {
  source_type: "web_search" | "exchange_native" | "official";
  source_url: string | null;
  source_title: string | null;
  published_at: string | null;
  fetched_at: string;
  summary: string;
  relevance_score: number;
  symbol: string | null;
}

/** 风险门禁结果 */
export interface RiskVerdict {
  allowed: boolean;
  blocked_reasons: string[];
  warnings: string[];
  confidence_cap: number;
}

/** HITL 中断数据 */
export interface InterruptData {
  type: "analysis_confirmation" | "notification_approval";
  data: AnalysisResult;
}
```

### 1.2 组件 Props

```typescript
// frontend/src/components/AnalysisResultCard.tsx
export interface AnalysisResultCardProps {
  result: AnalysisResult;
  onApprove: () => void;
  onReject: () => void;
  onEdit: (edits: Partial<AnalysisResult>) => void;
  expiresAt: string;
  isExpired: boolean;
}

// frontend/src/components/EvidenceTimeline.tsx
export interface EvidenceTimelineProps {
  evidence: EvidenceItem[];
  onItemClick?: (item: EvidenceItem) => void;
  groupBy?: "source_type" | "symbol" | "time";
}

// frontend/src/components/RiskInspector.tsx
export interface RiskInspectorProps {
  verdict: RiskVerdict;
  ruleHits: Array<{
    rule_id: string;
    rule_type: "blocking" | "warn";
    reason: string;
    details: Record<string, any>;
  }>;
  expanded?: boolean;
}

// frontend/src/components/MarketSnapshot.tsx
export interface MarketSnapshotProps {
  snapshot: MarketSnapshot;
  showDetails?: boolean;
  onRefresh?: () => void;
}

// frontend/src/components/InterruptConfirmDialog.tsx
export interface InterruptConfirmDialogProps {
  interrupt: {
    id: string;
    value: InterruptData;
  };
  onRespond: (response: { action: string; edits?: any }) => void;
  onRespondAll?: (responses: Record<string, any>) => void;
}
```

---

## 二、Custom Channel Typed Schema

### 2.1 Channel 定义

```typescript
// frontend/src/types/channels.ts

/** 任务进度 */
export interface TaskProgress {
  stage: "validate_request" | "collect_market_snapshot" | "research_events" |
         "analyze_market" | "validate_evidence" | "apply_risk_policy" |
         "build_final_result" | "confirm_analysis" | "commit_final_artifact" | "complete_run";
  status: "pending" | "running" | "completed" | "failed";
  message: string;
  progress_pct: number;  // 0-100
  ts: string;
}

/** 证据事件 */
export interface EvidenceEvent {
  event_type: "evidence_collected" | "evidence_validated";
  evidence: EvidenceItem;
  ts: string;
}

/** Artifact 事件 */
export interface ArtifactEvent {
  artifact_type: "market_snapshot" | "analysis_result" | "risk_verdict";
  artifact_id: string;
  summary: string;
  ts: string;
}

/** 风险门禁事件 */
export interface RiskVerdictEvent {
  verdict: RiskVerdict;
  rule_hits: Array<{
    rule_id: string;
    rule_type: "blocking" | "warn";
    reason: string;
  }>;
  ts: string;
}

/** 使用量事件 */
export interface UsageEvent {
  usage_type: "model_call" | "tool_call" | "search_call";
  count: number;
  cumulative: number;
  limit: number;
  ts: string;
}

/** Custom Channel 联合类型 */
export type CustomChannelData =
  | { channel: "custom:task_progress"; data: TaskProgress }
  | { channel: "custom:evidence"; data: EvidenceEvent }
  | { channel: "custom:artifact"; data: ArtifactEvent }
  | { channel: "custom:risk_verdict"; data: RiskVerdictEvent }
  | { channel: "custom:usage"; data: UsageEvent };
```

### 2.2 Channel Hooks

```typescript
// frontend/src/hooks/useCustomChannels.ts
import { useExtension, useChannel, useChannelEffect } from "@langchain/react";

export function useTaskProgress() {
  return useExtension<TaskProgress>("custom:task_progress");
}

export function useEvidenceLog() {
  return useChannel<EvidenceEvent>("custom:evidence");
}

export function useRiskVerdict() {
  return useExtension<RiskVerdictEvent>("custom:risk_verdict");
}

export function useUsageTracking(onLimitWarning?: (usage: UsageEvent) => void) {
  useChannelEffect("custom:usage", (event) => {
    if (event.cumulative / event.limit > 0.8 && onLimitWarning) {
      onLimitWarning(event);
    }
  });

  return useExtension<UsageEvent>("custom:usage");
}
```

### 2.3 后端 Channel 写入

```python
# backend/src/crypto_alert_v2/graph/nodes.py
from langgraph.types import StreamWriter

async def collect_market_snapshot(state: AnalysisState, writer: StreamWriter):
    """采集市场快照节点"""

    # 写入进度
    await writer("custom:task_progress", {
        "stage": "collect_market_snapshot",
        "status": "running",
        "message": "正在采集行情数据...",
        "progress_pct": 20,
        "ts": datetime.utcnow().isoformat(),
    })

    # 获取数据
    snapshot = await fetch_market_data(state["symbol"], ...)

    # 写入 artifact 事件
    await writer("custom:artifact", {
        "artifact_type": "market_snapshot",
        "artifact_id": str(uuid.uuid4()),
        "summary": f"{state['symbol']} 行情快照: ${snapshot['ticker']['last']}",
        "ts": datetime.utcnow().isoformat(),
    })

    # 写入进度完成
    await writer("custom:task_progress", {
        "stage": "collect_market_snapshot",
        "status": "completed",
        "message": "行情数据采集完成",
        "progress_pct": 30,
        "ts": datetime.utcnow().isoformat(),
    })

    return {"market_snapshot": snapshot}
```

---

## 三、配置管理策略

### 3.1 环境分层

```
config/
  ├── base.yaml              # 所有环境共享的基础配置
  ├── development.yaml       # 开发环境
  ├── staging.yaml           # 预发环境
  ├── production.yaml        # 生产环境
  └── secrets/               # secrets（不入 git）
      ├── .env.development
      ├── .env.staging
      └── .env.production
```

### 3.2 base.yaml

```yaml
# config/base.yaml
app:
  name: crypto-alert-v2
  version: 2.0.0

graph:
  recursion_limit: 30
  max_execution_time: 180  # seconds

model:
  # 开发/预发/生产会 override
  name: gpt-4o
  temperature: 0
  max_tokens: 4096
  timeout: 30

middleware:
  model_retry:
    max_retries: 2
  model_call_limit:
    max_calls: 6
  tool_call_limit:
    max_calls: 15

tools:
  okx:
    base_url: https://www.okx.com
    timeout: 10
    max_concurrent: 5
  tavily:
    timeout: 15
    max_results: 5

cache:
  ttl:
    ticker: 5
    mark: 10
    funding_rate: 60
    open_interest: 30
    order_book: 5
    candles: 60

notification:
  channels:
    - inbox
    - bark
  frequency:
    allowed: immediate
    blocked: none
    no_trade: none

observability:
  langsmith:
    enabled: true
    project: crypto-alert-v2
  langfuse:
    enabled: true
```

### 3.3 development.yaml

```yaml
# config/development.yaml
extends: base.yaml

environment: development

auth:
  mode: development
  dev_tenant_id: "00000000-0000-0000-0000-000000000001"
  dev_user_id: "00000000-0000-0000-0000-000000000001"

database:
  pool_size: 5
  max_overflow: 10
  echo: true  # 打印 SQL

cache:
  enabled: false  # 开发环境不缓存，方便调试

observability:
  langsmith:
    sampling_rate: 1.0  # 全量追踪
  langfuse:
    sampling_rate: 1.0

logging:
  level: DEBUG
  structlog_dev_mode: true
```

### 3.4 production.yaml

```yaml
# config/production.yaml
extends: base.yaml

environment: production

auth:
  mode: production
  # 实际 auth handler 从 secrets 读取

database:
  pool_size: 20
  max_overflow: 40
  echo: false

cache:
  enabled: true

observability:
  langsmith:
    sampling_rate: 0.1  # 采样 10%
  langfuse:
    sampling_rate: 1.0  # 成本追踪全量

logging:
  level: INFO
  structlog_dev_mode: false

rate_limit:
  enabled: true
  per_user_per_hour: 20
```

### 3.5 配置加载代码

```python
# backend/src/crypto_alert_v2/config.py
from pathlib import Path
from pydantic_settings import BaseSettings
import yaml

class Settings(BaseSettings):
    environment: str = "development"

    # 从环境变量覆盖
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    postgres_uri: str
    redis_uri: str
    langsmith_api_key: str
    langfuse_public_key: str
    langfuse_secret_key: str

    # 从 yaml 加载的配置
    config: dict = {}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @classmethod
    def load(cls):
        env = os.getenv("ENVIRONMENT", "development")

        # 加载 base.yaml
        base_path = Path("config/base.yaml")
        with base_path.open() as f:
            base_config = yaml.safe_load(f)

        # 加载环境特定配置
        env_path = Path(f"config/{env}.yaml")
        with env_path.open() as f:
            env_config = yaml.safe_load(f)

        # 合并配置
        config = {**base_config, **env_config}

        # 创建 Settings 实例
        settings = cls(environment=env, config=config)
        return settings

settings = Settings.load()
```

### 3.6 Feature Flags

```python
# backend/src/crypto_alert_v2/feature_flags.py
from enum import Enum

class FeatureFlag(str, Enum):
    COINGLASS_INTEGRATION = "coinglass_integration"
    DEEP_AGENTS_RESEARCH = "deep_agents_research"
    OUTCOME_TRACKING = "outcome_tracking"
    WEB_PUSH_NOTIFICATIONS = "web_push_notifications"

FEATURE_FLAGS = {
    "development": {
        FeatureFlag.COINGLASS_INTEGRATION: False,
        FeatureFlag.DEEP_AGENTS_RESEARCH: True,
        FeatureFlag.OUTCOME_TRACKING: True,
        FeatureFlag.WEB_PUSH_NOTIFICATIONS: False,
    },
    "staging": {
        FeatureFlag.COINGLASS_INTEGRATION: True,
        FeatureFlag.DEEP_AGENTS_RESEARCH: True,
        FeatureFlag.OUTCOME_TRACKING: True,
        FeatureFlag.WEB_PUSH_NOTIFICATIONS: False,
    },
    "production": {
        FeatureFlag.COINGLASS_INTEGRATION: True,
        FeatureFlag.DEEP_AGENTS_RESEARCH: True,
        FeatureFlag.OUTCOME_TRACKING: True,
        FeatureFlag.WEB_PUSH_NOTIFICATIONS: False,
    },
}

def is_enabled(flag: FeatureFlag, environment: str = None) -> bool:
    env = environment or settings.environment
    return FEATURE_FLAGS.get(env, {}).get(flag, False)
```

---

## 四、数据生命周期策略

### 4.1 Checkpoint 保留策略

| 状态 | 保留期 | 清理策略 |
|------|--------|----------|
| 运行中 | 永久 | 不清理 |
| 成功完成 | 30 天 | 按 thread_id 聚合清理 |
| 失败 | 7 天 | 失败 checkpoint 可能用于调试 |
| 用户拒绝(blocked) | 7 天 | 用户主动拒绝的决策 |
| 已归档到 Product DB | 7 天 | Checkpoint 已投影到产品表 |

### 4.2 Event Projection 归档策略

```python
# Event projection 只保留最近，旧事件归档到冷存储
# backend/src/crypto_alert_v2/jobs/archive_events.py

async def archive_old_events():
    """归档 90 天前的 event projections 到冷存储"""
    cutoff = datetime.utcnow() - timedelta(days=90)

    # 导出到 S3/MinIO
    events = await db.query(ProductEventProjection).filter(
        ProductEventProjection.created_at < cutoff
    ).all()

    # 写入 Parquet 到对象存储
    df = pd.DataFrame([e.to_dict() for e in events])
    df.to_parquet(f"s3://archives/events/{cutoff.date()}.parquet")

    # 删除 PostgreSQL 中的旧数据
    await db.query(ProductEventProjection).filter(
        ProductEventProjection.created_at < cutoff
    ).delete()
```

### 4.3 Trace 数据保留期

| 追踪系统 | 保留期 | 成本考虑 |
|----------|--------|----------|
| LangSmith | 90 天 | Plus $39/月包含 50K traces |
| Langfuse | 365 天 | 自部署无限制 |
| 应用日志(structlog) | 30 天 | 日志量大，定期归档 |

### 4.4 Outcome 数据永久保留

Outcome 数据用于评测和金融质量门禁，永久保留：

```sql
-- outcomes 表不设置 TTL
-- 但可以按季度分区提升查询性能
CREATE TABLE outcomes_2026_q3 PARTITION OF outcomes
FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
```

### 4.5 清理 Job

```python
# backend/src/crypto_alert_v2/jobs/cleanup.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("cron", hour=3, minute=0)  # 每天凌晨 3 点
async def daily_cleanup():
    """每日清理任务"""
    await cleanup_old_checkpoints()
    await cleanup_stale_interrupts()
    await cleanup_failed_notifications()

@scheduler.scheduled_job("cron", day_of_week="sun", hour=2, minute=0)  # 每周日
async def weekly_archive():
    """每周归档任务"""
    await archive_old_events()
    await archive_old_logs()

@scheduler.scheduled_job("cron", day=1, hour=1, minute=0)  # 每月 1 日
async def monthly_report():
    """每月报告"""
    await generate_monthly_usage_report()
    await check_data_retention_compliance()
```

---

## 五、Secrets 管理

### 5.1 开发环境

```bash
# config/secrets/.env.development
OPENAI_API_KEY=sk-dev-...
LANGSMITH_API_KEY=lsv2-dev-...
LANGFUSE_PUBLIC_KEY=pk-lf-dev-...
LANGFUSE_SECRET_KEY=sk-lf-dev-...
TAVILY_API_KEY=tvly-dev-...
BARK_KEY=dev-bark-key
```

### 5.2 生产环境（推荐 Secret Manager）

```python
# backend/src/crypto_alert_v2/secrets.py
import os
from google.cloud import secretmanager  # 或 AWS Secrets Manager

def get_secret(secret_name: str) -> str:
    """从 Secret Manager 获取 secret"""
    if os.getenv("ENVIRONMENT") == "development":
        # 开发环境从 .env 读取
        return os.getenv(secret_name)

    # 生产环境从 Secret Manager 读取
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
```

---

## 六、配置热更新

某些配置（如 feature flags、rate limits）支持热更新，不需要重启服务：

```python
# backend/src/crypto_alert_v2/config_watcher.py
import asyncio
from watchfiles import awatch

async def watch_config():
    """监控配置文件变化并热重载"""
    async for changes in awatch("config/"):
        for change_type, file_path in changes:
            if file_path.endswith(".yaml"):
                print(f"Config changed: {file_path}, reloading...")
                settings.reload()
                # 通知其他组件配置已更新
                await notify_config_updated()
```

**注意**：只有非关键配置支持热更新。数据库连接、API Keys 等需要重启服务。
