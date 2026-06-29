# Deployment Guide

## 部署边界

首版是 `MANUAL_ALERT` 服务：

- 不自动下单。
- 不接 OKX Trade Key。
- 不暴露 Web 端口。
- 不写固定 `container_name`。
- 不加入已有 compose 网络。
- 使用独立 Compose 项目名，避免和服务器已有服务冲突。

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

`DECISION_ENGINE=command` 在 manual-alert v1 中已禁用，避免外部命令绕过配置、审计和风控边界。

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
