# Deployment Guide

## 部署边界

首版是 `MANUAL_ALERT` 服务：

- 不自动下单。
- 不接 OKX Trade Key。
- 不暴露 Web 端口。
- 不写固定 `container_name`。
- 不加入已有 compose 网络。
- 使用独立 Compose 项目名，避免和服务器已有服务冲突。
- 当前生产最终输入默认仍是 `decision.final_input_mode=legacy_prompt`；Agent Swarm/Skill/DecisionInput 仍是 shadow audit、candidate/replay 和评测路径，不是自动生产切换。
- 后续生产候选 Agent Swarm 收敛以 `docs/formal/34-生产级AgentSwarm优化目标与执行计划.md` 为当前执行入口。

## 准备服务器目录

```bash
mkdir -p /opt/crypto-manual-alert
cd /opt/crypto-manual-alert
```

把项目文件放到该目录后，创建 `.env`：

```bash
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

```env
APP_MODE=SHADOW
AUTO_ORDER_ENABLED=false
MARKET_DATA_PROVIDER=fixture
DECISION_ENGINE=fixture
NOTIFICATION_ENABLED=false
BARK_DEVICE_KEY=你的BarkKey
```

先用 `SHADOW` + fixture 跑通容器和日志。确认稳定后，再接入真实模型和公开行情：

```env
APP_MODE=MANUAL_ALERT
MARKET_DATA_PROVIDER=okx_public
DECISION_ENGINE=openai_compatible
OPENAI_BASE_URL=https://你的中转站域名
OPENAI_MODEL=你的模型名
OPENAI_API_KEY=你的Key
RESEARCH_ENABLED=true
RESEARCH_PLANNER=llm
RESEARCH_LEADER_MODE=llm
RESEARCH_SEARCH_PROVIDER=responses_web_search
NOTIFICATION_ENABLED=true
```

即使切到 `MANUAL_ALERT`，也必须保持 `decision.final_input_mode=legacy_prompt`，除非后续有单独的人工 release review artifact 和回滚方案批准切换。

`DECISION_ENGINE=command` 在当前手动提醒阶段已禁用，避免外部命令绕过配置、审计和风控边界。

## 风控门禁与可执行提醒（facts_gate）

`facts_gate` 在产出可执行开仓动作（opening/trigger/flip）前要求两类事实齐备：

1. **执行事实** `mark`/`index`/`order_book`：必须来自 exchange-native 行情源。`market_data.provider=okx_public` 时由 OKX 公开接口提供（source `okx_public` 映射为 `source_type=exchange_native`）。`fixture` 行情 source 为 `fixture`，不满足执行事实。
2. **事件事实** `active_event_status`：必须来自 event_pool/official 源。当前由 `macro_event.provider` 控制：
   - `disabled`（默认）：不提供该点 → 开仓动作被门禁阻断（安全默认）。
   - `no_active_event`：操作员断言"当前无影响该 symbol horizon 的活跃宏观事件"，写入 source=`event_pool` 的事件状态点 → 满足门禁，放行开仓动作。仅在操作员确认无活跃事件时启用，断言记入审计轨迹。

因此：

- **默认配置**（`config/default.yaml` 单独使用：fixture 行情 + macro_event disabled）：开仓/触发/翻转动作被门禁阻断，系统只产出 `no trade`/`hold` 类提醒。这是有意的安全默认。
- **可执行提醒路径**（`--config config/default.yaml --config config/staging.yaml`）：`okx_public` 行情 + `no_active_event` 断言 → 开仓动作放行，产出可执行提醒。
- **生产交付**：在 staging 基础上叠加 `config/prod.yaml`（`openai_compatible` 真实 LLM + Bark 通知）。

```bash
# 本地/ staging 验证（fixture 决策引擎，无 LLM/网络，需 mock 或真实 OKX）
crypto-alert --config config/default.yaml --config config/staging.yaml run-once --symbol ETH-USDT-SWAP

# 生产交付（真实 LLM + Bark + 可执行开仓）
crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml run-once --symbol ETH-USDT-SWAP
```

`MACRO_EVENT_PROVIDER` 环境变量可覆盖（值为 `disabled` 或 `no_active_event`）。详见 `docs/formal/37-真实多Agent对抗审查与交付方向裁决.md` §5.2 H1 与 `docs/migration/2026-07-06-checkpoint-execution-fact-unblock.md`。

## 启动

推荐显式指定 project name：

```bash
docker compose -p crypto-alert-prod --env-file .env config
docker compose -p crypto-alert-prod --env-file .env up -d --build
```

这个 compose 文件没有发布宿主机端口，不应和已有服务抢端口。

## 查看状态

```bash
docker compose -p crypto-alert-prod ps
docker compose -p crypto-alert-prod logs -f manual-alert
```

## 手动触发一次计划

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml run-once --symbol ETH-USDT-SWAP
```

## 暂停和恢复

暂停：

```bash
docker compose -p crypto-alert-prod stop manual-alert
```

恢复：

```bash
docker compose -p crypto-alert-prod up -d
```

## 数据持久化

业务数据在：

```text
./data/crypto-alert.db
```

备份：

```bash
mkdir -p backups
cp data/crypto-alert.db backups/crypto-alert-$(date +%F-%H%M%S).db
```

## 升级

1. 备份 `.env` 和 `data/crypto-alert.db`。
2. 拉取新代码或替换项目文件。
3. 先校验配置：

```bash
docker compose -p crypto-alert-prod --env-file .env config
```

4. 重建并启动：

```bash
docker compose -p crypto-alert-prod --env-file .env up -d --build
```

5. 先用 `SHADOW` 跑一轮，再切 `MANUAL_ALERT`。

## 故障排查

- 容器起不来：检查 `.env`、volume 权限、compose project name。
- 重复提醒：检查是否同时启用了宿主机 cron 和容器内 scheduler。
- 没收到 Bark：检查 `BARK_DEVICE_KEY`、iPhone 通知权限、勿扰模式、网络。
- 计划过期：检查模型耗时、Bark 延迟、`PLAN_TTL_SECONDS`。
- 磁盘满：清理 Docker logs、旧镜像和备份。
- API 成本异常：检查调度频率、失败重试、是否重复部署多个 compose project。
