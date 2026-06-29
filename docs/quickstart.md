# 傻瓜式操作和部署文档

> 首版只做“操作计划 + Bark 提醒 + 用户手动去 OKX 操作”。它不会自动下单，不需要 OKX Trade Key。

## 0. 先记住边界

首版默认是安全模式：

- 不自动下单。
- 不接 OKX Trade Key。
- 不接 OKX Withdraw Key。
- 默认不发 Bark。
- 默认用测试行情和测试计划，先验证服务能跑。

真正上线顺序是：

1. 先跑通 Docker。
2. 再测试 Bark。
3. 再打开 OKX 公共行情。
4. 最后再接模型命令生成真实计划。
5. 收到提醒后，用户自己打开 OKX App 手动操作。

## 1. 本地先自测

在 Windows 本机：

```powershell
cd <repo-root>
pytest -q
$env:PYTHONPATH="src"
python -m crypto_manual_alert.cli show-config
python -m crypto_manual_alert.cli run-once --symbol ETH-USDT-SWAP
```

看到 `allowed: true/false`、`manual_execution_required: true` 就说明服务流程能跑。

## 2. 上传到海外服务器

服务器建议目录：

```bash
mkdir -p /opt/crypto-manual-alert
```

把整个 `project/crypto-manual-alert` 目录上传到服务器的：

```text
/opt/crypto-manual-alert
```

进入目录：

```bash
cd /opt/crypto-manual-alert
```

## 3. 创建 .env

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

第一阶段先这样填：

```env
APP_MODE=SHADOW
AUTO_ORDER_ENABLED=false
MARKET_DATA_PROVIDER=fixture
DECISION_ENGINE=fixture
NOTIFICATION_ENABLED=false
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_SECONDS=1800
SCHEDULER_JOB_TIMEOUT_SECONDS=1800
BARK_DEVICE_KEY=
DECISION_COMMAND=
# DECISION_ENGINE=command 在 v1 禁用，保留该字段仅为后续兼容。
OPENAI_BASE_URL=
OPENAI_MODEL=
OPENAI_API_KEY=
```

这一步不会发通知，也不会用真实行情，只验证服务能稳定跑。

## 4. 第一次启动

先检查 compose 配置：

```bash
docker compose -p crypto-alert-prod --env-file .env config
```

启动：

```bash
docker compose -p crypto-alert-prod --env-file .env up -d --build
```

查看状态：

```bash
docker compose -p crypto-alert-prod ps
docker compose -p crypto-alert-prod logs -f manual-alert
```

这个 compose 不暴露端口，不写固定容器名，不会抢你服务器上已有服务的端口。

## 5. 手动跑一次测试计划

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml run-once --symbol ETH-USDT-SWAP
```

如果输出 JSON，说明基础流程正常。

## 6. 测试 Bark

手机安装 Bark，拿到 Bark key。

编辑 `.env`：

```env
BARK_DEVICE_KEY=你的BarkKey
NOTIFICATION_ENABLED=false
```

先只测 Bark，不打开正式通知：

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml test-bark
```

手机收到测试推送后，再进入下一步。

## 7. 打开 Bark 通知

编辑 `.env`：

```env
NOTIFICATION_ENABLED=true
```

重启：

```bash
docker compose -p crypto-alert-prod --env-file .env up -d
```

此时仍然是 fixture 测试计划，不是真实行情。

## 8. 打开 OKX 公共行情

编辑 `.env`：

```env
MARKET_DATA_PROVIDER=okx_public
```

重启：

```bash
docker compose -p crypto-alert-prod --env-file .env up -d
```

注意：OKX 公共行情不需要 OKX Key。

## 9. 接入真实模型/Skill 分析

当前服务推荐使用 OpenAI 兼容接口接入真实模型。

方式 A：OpenAI 兼容接口，推荐先用这个。

编辑 `.env`：

```env
DECISION_ENGINE=openai_compatible
OPENAI_BASE_URL=https://你的中转站域名
OPENAI_MODEL=你的模型名
OPENAI_API_KEY=你的Key
DECISION_TIMEOUT_SECONDS=1200
RESEARCH_ENABLED=true
RESEARCH_PLANNER=llm
RESEARCH_LEADER_MODE=llm
RESEARCH_SEARCH_PROVIDER=responses_web_search
RESEARCH_MAX_QUERIES=2
RESEARCH_MAX_WORKERS=2
RESEARCH_REQUEST_TIMEOUT_SECONDS=300
SCHEDULER_JOB_TIMEOUT_SECONDS=1800
```

注意：`OPENAI_BASE_URL` 不要在末尾写 `/v1`，程序会自动请求 `/v1/chat/completions`。
这个流程不是 60 秒任务；多 agent / 根因链 / web search 合起来跑 10 到十几分钟是正常的。`RESEARCH_REQUEST_TIMEOUT_SECONDS` 限制单个研究请求，`DECISION_TIMEOUT_SECONDS` 限制最终决策模型单次请求，`SCHEDULER_JOB_TIMEOUT_SECONDS` 是整轮任务预算。

例如中转站是 `https://example.com/` 时：

```env
DECISION_ENGINE=openai_compatible
OPENAI_BASE_URL=https://example.com
OPENAI_MODEL=gpt-5.5
OPENAI_API_KEY=example-openai-api-key
DECISION_TIMEOUT_SECONDS=1200
RESEARCH_ENABLED=true
RESEARCH_PLANNER=llm
RESEARCH_LEADER_MODE=llm
RESEARCH_SEARCH_PROVIDER=responses_web_search
RESEARCH_REQUEST_TIMEOUT_SECONDS=300
```

方式 B：自定义命令。

该方式是后续兼容设计，manual-alert v1 当前已禁用 `DECISION_ENGINE=command`。首版不要启用它，避免外部命令绕过配置、审计和风控边界。真实模型分析请使用上面的 `openai_compatible` 方式。

## 10. 切到正式提醒模式

确认下面几项都正常：

- Docker 正常运行。
- Bark 能收到测试消息。
- OKX 公共行情能拉取。
- 模型命令能输出合规 JSON。
- 日志没有密钥。

然后编辑 `.env`：

```env
APP_MODE=MANUAL_ALERT
```

重启：

```bash
docker compose -p crypto-alert-prod --env-file .env up -d
```

从这一步开始，收到 Bark 后你要自己打开 OKX App 手动核对和操作。

## 11. 日常怎么用

看日志：

```bash
docker compose -p crypto-alert-prod logs -f manual-alert
```

手动生成一次计划：

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml run-once --symbol ETH-USDT-SWAP
```

记录手动执行结果：

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml record-outcome \
  --plan-id 你的plan_id \
  --outcome executed \
  --notes "OKX manual entry, stop set"
```

暂停服务：

```bash
docker compose -p crypto-alert-prod stop manual-alert
```

恢复服务：

```bash
docker compose -p crypto-alert-prod up -d
```

## 12. 备份

业务数据在：

```text
data/crypto-alert.db
```

备份：

```bash
mkdir -p backups
cp data/crypto-alert.db backups/crypto-alert-$(date +%F-%H%M%S).db
cp .env backups/env-$(date +%F-%H%M%S).bak
```

## 13. 升级

```bash
cd /opt/crypto-manual-alert
cp data/crypto-alert.db backups/crypto-alert-before-upgrade.db
cp .env backups/env-before-upgrade.bak
docker compose -p crypto-alert-prod --env-file .env config
docker compose -p crypto-alert-prod --env-file .env up -d --build
docker compose -p crypto-alert-prod logs -f manual-alert
```

升级后先用 `APP_MODE=SHADOW` 跑一轮，再切回 `MANUAL_ALERT`。

## 14. 常见问题

### 没收到 Bark

检查：

- `.env` 里的 `BARK_DEVICE_KEY`。
- `NOTIFICATION_ENABLED=true`。
- iPhone 是否开了 Bark 通知权限。
- iPhone 是否勿扰/离线/没电。

### 重复收到提醒

检查是否启动了多个项目：

```bash
docker ps
```

只保留一个：

```bash
docker compose -p crypto-alert-prod ps
```

不要再额外用宿主机 cron 同时触发。

### 容器起不来

先看配置：

```bash
docker compose -p crypto-alert-prod --env-file .env config
```

再看日志：

```bash
docker compose -p crypto-alert-prod logs manual-alert
```

### 提示计划过期

原因通常是：

- 模型分析太慢。
- Bark 延迟。
- `PLAN_TTL_SECONDS` 太短。

过期计划不要操作，重新生成。

## 15. 最重要的手动操作提醒

收到 Bark 后不要直接照抄下单，先在 OKX App 核对：

- 币种是否正确。
- 合约/现货是否正确。
- 多空方向是否正确。
- 当前价格是否仍接近计划价。
- 止损是否设置。
- 仓位是否过大。
- 杠杆是否不超过 2x。
- 计划是否过期。

任何一项不确定，默认不操作。
