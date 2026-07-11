# Deployment Guide

## 部署边界

Compose 交付面包含三个服务：

- `manual-alert`：scheduler/CLI 运行面，用于后台轮询、`run-once`、`collect-outcomes` 和运维命令；它在 `scheduler` profile 下显式启动，默认 `up` 优先启动人工工作台。
- `api`：FastAPI 工作台后端，默认暴露宿主机 `${API_PORT:-8010}`，承载 `POST /api/runs/manual`、运行详情、配置就绪检查和 Eval 查询。
- `frontend`：Next.js 工作台前端，默认暴露宿主机 `${FRONTEND_PORT:-3001}`，面向人工触发、提醒详情、质量复盘和配置检查。

安全边界：

- 不自动下单。
- 不接 OKX Trade Key。
- Web 端口只暴露人工工作台和 API，不暴露任何交易、撤单或提现接口。
- 不写固定 `container_name`。
- 不加入已有 compose 网络。
- 使用独立 Compose 项目名，避免和服务器已有服务冲突。
- 当前生产最终输入默认仍是 `decision.final_input_mode=legacy_prompt`；Agent Swarm/Skill/DecisionInput 仍是 shadow audit、candidate/replay 和评测路径，不是自动生产切换。
- 当前交付方向以 `docs/formal/37-真实多Agent对抗审查与交付方向裁决.md` 和本部署手册的 manual-alert 主流程为准；后续 Swarm/candidate 切换必须有单独 release review artifact、回滚方案和人工批准。

## 准备服务器目录

```bash
mkdir -p /opt/crypto-manual-alert
cd /opt/crypto-manual-alert
```

把项目文件放到该目录后，可以先不创建 `.env`，直接用默认 `SHADOW` + fixture 配置渲染 compose 和启动工作台。需要覆盖端口、接入真实模型/行情/Bark，或运行严格 `prod_actionable` 门禁时，再创建 `.env`：

```bash
cp .env.example .env
chmod 600 .env
```

如果目标是生产意图工作台，不要从安全默认模板手拼 overlay。使用仓库里的生产模板复制成 `.env`，再填写真实 OpenAI-compatible、Bark 和 `no_active_event` 操作员断言值：

```bash
cp .env.production.example .env
chmod 600 .env
```

`.env.production.example` 会显式声明：

- `CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml`
- `APP_MODE=MANUAL_ALERT`
- `AUTO_ORDER_ENABLED=false`
- `DIAGNOSTIC_ROUTES_ENABLED=false`
- `SCHEDULER_ENABLED=false`
- `MARKET_DATA_PROVIDER=okx_public`
- `MARKET_DATA_HTTP_TRUST_ENV=false`
- `MARKET_DATA_HTTP_PROXY=`
- `DECISION_ENGINE=openai_compatible`
- `NOTIFICATION_ENABLED=true`
- `MACRO_EVENT_PROVIDER=no_active_event`
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010`
- `API_INTERNAL_BASE_URL=http://api:8010`

模板不包含 OKX trade/withdraw key，也不改变 manual-only 边界。

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

### 受限网络或私有镜像源

如果目标运行环境无法直连 `https://www.okx.com`，但运维已经提供受控 HTTP 代理，有两种明确配置方式：

```env
# 方式一：允许 OKX httpx 客户端继承 HTTP_PROXY / HTTPS_PROXY / NO_PROXY。
MARKET_DATA_HTTP_TRUST_ENV=true
HTTPS_PROXY=http://proxy.internal:8888
NO_PROXY=127.0.0.1,localhost,api
```

```env
# 方式二：只给 OKX public 行情客户端配置显式代理。
MARKET_DATA_HTTP_TRUST_ENV=false
MARKET_DATA_HTTP_PROXY=http://proxy.internal:8888
```

默认仍是 `MARKET_DATA_HTTP_TRUST_ENV=false` 且 `MARKET_DATA_HTTP_PROXY=`，避免本地 mock、fixture 和 CI 被宿主机代理静默劫持。显式代理值可能包含凭证，因此 `/api/system/config` 只返回 `<redacted>` / `<unset>` 与 `http_proxy_set`，不会回显 URL。两种方式都只改变到真实 `https://www.okx.com` 的网络出口，不能把搜索、fixture、本地 OKX mock 或代理自身响应当作 exchange-native 生产证据；严格 smoke 仍必须核对实际 OKX evidence source、freshness 和执行事实完整度。

如果部署环境无法稳定访问 Docker Hub，`docker compose up -d --build api frontend` 可能在解析 `python:3.12-slim` 或 `node:22-alpine` metadata 时超时。此时不要把 Compose config 渲染成功当成 runtime smoke 成功；应先把基础镜像同步到可访问的私有镜像源，或在目标机器预拉取等价镜像，然后通过 `.env` 覆盖构建基础镜像：

```env
PYTHON_BASE_IMAGE=registry.example.com/library/python:3.12-slim
NODE_BASE_IMAGE=registry.example.com/library/node:22-alpine
```

覆盖后重新渲染并构建：

```bash
docker compose -p crypto-alert-prod --env-file .env config
docker compose -p crypto-alert-prod --env-file .env up -d --build api frontend
```

这只解决容器构建来源问题，不改变产品安全边界，也不能替代 `prod-actionable` 严格生产门禁。容器 healthy 仍只证明 hosted workbench runtime 可用；生产提醒成功还必须单独看到真实 LLM、真实 OKX public 行情、Bark `sent`、`MACRO_EVENT_PROVIDER=no_active_event` 及完整人工断言元数据、`allowed=true`。

## 机器可读证据阶梯

发布记录和迁移 checkpoint 需要先统一证据口径，再选择要运行的 gate。当前机器可读索引是：

```bash
python3 tools/deployment/proof_ladder.py
```

输出的 `schema_version` 是 `2026-07-09.main-flow-proof-ladder`。它列出 manual-alert 主路径、definition of done，以及这些 gate 的证明边界：`local_no_secret_matrix`、`strict_local_prod_actionable_guard`、`docker_hosted_runtime`、`hosted_prod_config`、`hosted_prod_actionable`、`hosted_prod_actionable_visual`、`hosted_real_outcome`。

Important: `tools/deployment/proof_ladder.py` does not run the gates. It only defines proof levels and the commands that must be run. Passing `local_no_secret_matrix`、`docker_hosted_runtime` 或默认 Playwright negative guard 仍然不是生产成功；只有 hosted `hosted_prod_actionable` 和同环境 `hosted_prod_actionable_visual` 通过后，才能记录真实生产可复核提醒链路。`hosted_real_outcome` 是 horizon 成熟后的复盘证据，也不能替代 fresh prod-actionable run。

## 风控门禁与可执行提醒（facts_gate）

`facts_gate` 在产出可执行开仓动作（opening/trigger/flip）前要求两类事实齐备：

1. **执行事实** `mark`/`index`/`order_book`：必须来自 exchange-native 行情源。`market_data.provider=okx_public` 时由 OKX 公开接口提供（source `okx_public` 映射为 `source_type=exchange_native`）。`fixture` 行情 source 为 `fixture`，不满足执行事实。
2. **事件事实** `active_event_status`：必须来自 event_pool/official 源。当前由 `macro_event.provider` 控制：
   - `disabled`（默认）：不提供该点 → 开仓动作被门禁阻断（安全默认）。
    - `no_active_event`：操作员断言"当前无影响该 symbol horizon 的活跃宏观事件"，写入 source=`event_pool` 的事件状态点 → 满足门禁，放行开仓动作。仅在操作员确认无活跃事件时启用，断言记入审计轨迹。

Web search / Responses web search 的职责是补充新闻、宏观事件、研究证据和审计上下文。搜索结果可能有缓存、转述、时间延迟和来源歧义，所以不能代替 OKX 原生 `mark`、`index`、`order_book`，也不能让 `execution_facts_ready` 从 `false` 变为 `true`。

`no_active_event` 在本地/staging profile 中可作为 wiring 证明；生产 `prod-actionable` 门禁还要求同步记录人工断言元数据，否则只能算缺 readiness：

- `MACRO_EVENT_OPERATOR_REF`：确认人或值班角色，例如 `ops:macro-desk`。
- `MACRO_EVENT_CONFIRMED_AT`：带时区 ISO 时间，例如 `2026-07-09T09:30:00+08:00`。
- `MACRO_EVENT_SOURCE_REF`：确认依据，例如宏观日历/事件池链接、工单或公告引用。
- `MACRO_EVENT_ASSERTION_HORIZON`：本次断言适用窗口，例如 `6h`。
- `MACRO_EVENT_VALID_UNTIL`：带时区 ISO 时间，必须晚于确认时间。

因此：

- **默认配置**（`config/default.yaml` 单独使用：fixture 行情 + macro_event disabled）：开仓/触发/翻转动作被门禁阻断，系统只产出 `no trade`/`hold` 类提醒。这是有意的安全默认。
- **可执行提醒路径**（`--config config/default.yaml --config config/staging.yaml`）：`okx_public` 行情 + `no_active_event` 断言 → 开仓动作放行，产出可执行提醒。
- **生产交付**：在 staging 基础上叠加 `config/prod.yaml`（`openai_compatible` 真实 LLM + Bark 通知）。

```bash
# 本地/ staging 验证（fixture 决策引擎，无 LLM/网络，需 mock 或真实 OKX）
crypto-alert --config config/default.yaml --config config/staging.yaml run-once --symbol ETH-USDT-SWAP --query "评估 ETH 未来 6h 是否值得人工追多" --horizon 6h

# 生产交付（真实 LLM + Bark + 可进入人工复核的开仓提醒）
crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml run-once --symbol ETH-USDT-SWAP --query "评估 ETH 未来 6h 是否值得人工追多" --horizon 6h
```

`run-once --query` 当前是 operator audit note：系统保存这段手动查询上下文用于 trace、审计和前端展示；`--horizon` 当前是手动复核/后续采集上下文。现阶段生产规划仍由 symbol/config、行情事实、LLM 输出和风控门禁共同决定，不把自由文本查询或请求 horizon 直接当作可执行交易指令。CLI 输出包含 `trace_id`、可读 `business_summary`、`notification` 摘要、`result_review` 状态、`requested_horizon` 和 `plan_horizon`；拿到 `trace_id` 后可用 `trace-show` 或 API 详情继续核对。

`MACRO_EVENT_PROVIDER` 环境变量可覆盖（值为 `disabled` 或 `no_active_event`）。详见 `docs/formal/37-真实多Agent对抗审查与交付方向裁决.md` §5.2 H1 与 `docs/migration/2026-07-06-checkpoint-execution-fact-unblock.md`。

## 本地全链路自测 Profile

本地 smoke 脚本会启动真实 API 和前端，并通过页面/API 走一遍 `新建提醒 -> 提醒详情 -> 提醒记录 -> 诊断视图`。这些 profile 的含义不同，不能互相替代；尤其不能把 mock 或 structured skip 当成生产成功。

运行前先确认端口没有被占用；这些脚本共享 `8010`、`3001`、`8011`、`8012`、`8013`，不要并行执行。`8013` 只在 opt-in Server Component fault API 场景启动，用于验证服务端渲染请求失败时的安全降级。

```bash
lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012 -ti tcp:8013 || true
```

### 0. No-secret local matrix

```bash
python3 tools/local_stack/run_local_checks.py
```

该入口顺序执行 Python 测试、前端类型检查、生产构建、Playwright 真实浏览器自测，以及 fixture / mock LLM / actionable staging / mocked outcome / collect-outcomes fixture smoke。它用于回答“本地无密钥主流程和模拟 profile 是否仍然闭环”，不会运行 `prod-actionable` 严格门禁，也不能作为生产成功证明。

非生产本地 smoke 会显式设置 `DIAGNOSTIC_ROUTES_ENABLED=true`，用于测试 raw payload
脱敏和工程诊断页面；`--prod-actionable` 使用生产默认关闭姿态。共享环境和生产部署应保持默认 `false`：API 在默认配置下会拒绝
`GET /api/runs/{trace_id}?include_payloads=true` 和 `POST /api/eval/runs`
的 `mode=judge_openai`，以及 `GET /api/eval/runs/{eval_run_id}` /
`GET /api/eval/runs/{eval_run_id}/promotion-artifacts`，避免前端 query string
或 eval replay 明细绕过产品边界。

真实生产门禁仍需单独运行：

```bash
python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip
```

缺少真实 Bark、OpenAI-compatible endpoint/model/key 或 `MACRO_EVENT_PROVIDER=no_active_event` 时，严格门禁非零退出是正确行为，表示生产证明未完成。

### 1. 默认 fixture profile

```bash
python3 tools/local_stack/smoke_local_stack.py
```

预期含义：

- 启动真实本地 API 和 Next.js 前端。
- 使用 `MARKET_DATA_PROVIDER=fixture`、`DECISION_ENGINE=fixture`、`NOTIFICATION_ENABLED=false`。
- 验证产品默认页可读，不需要打开 Raw/JSON 才能理解提醒。
- 验证安全默认：fixture 行情不会满足 exchange-native execution facts，开仓/触发/翻转动作应被阻断。

示例关键输出：

```json
{
  "ok": true,
  "smoke_profile": "fixture",
  "allowed": false,
  "decision_engine": "fixture",
  "market_provider": "fixture",
  "manual_execution_required": true,
  "auto_order_enabled": false
}
```

这个 profile 只能证明本地骨架和安全默认可用；它不是真实 LLM、真实 OKX、真实 Bark 的生产证明。

### 2. Mock LLM profile

```bash
python3 tools/local_stack/smoke_local_stack.py --with-mock-llm
```

预期含义：

- 启动本地 OpenAI-compatible mock server。
- 使用 `DECISION_ENGINE=openai_compatible`，但 `OPENAI_BASE_URL=http://127.0.0.1:8011`。
- 验证真实 LLM client 代码路径、LLM 交互记录、payload redaction、严格 JSON 解析。
- 仍使用 fixture 行情，所以可执行开仓动作应继续被阻断。

示例关键输出：

```json
{
  "ok": true,
  "smoke_profile": "mock_real_engine",
  "decision_engine": "openai_compatible",
  "decision_model": "mock-crypto-plan",
  "market_provider": "fixture",
  "allowed": false,
  "manual_execution_required": true,
  "auto_order_enabled": false
}
```

这个 profile 证明“LLM 代码路径可跑”，不是生产模型质量证明，也不是真实外部依赖成功。

### 3. Actionable staging profile

```bash
python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging
```

预期含义：

- 启动本地 OKX public mock server。
- 设置 `MARKET_DATA_PROVIDER=okx_public`、`MARKET_DATA_OKX_BASE_URL=http://127.0.0.1:8012`、`MACRO_EVENT_PROVIDER=no_active_event`。
- 用受控 exchange-native mark/index/order_book 和 no-active-event 断言证明 H1 facts gate 可以进入人工复核。
- 决策仍是 fixture，不调用真实 LLM，不发送 Bark。

示例关键输出：

```json
{
  "ok": true,
  "smoke_profile": "actionable_staging",
  "allowed": true,
  "decision_engine": "fixture",
  "market_provider": "okx_public",
  "macro_event_provider": "no_active_event",
  "manual_execution_required": true,
  "auto_order_enabled": false
}
```

这个 profile 证明“受控可执行提醒路径”可达；它不是 production success，因为 OKX 是本地 mock，LLM 也是 fixture，Bark 未发送。

### 4. Prod-actionable readiness / success profile

```bash
BARK_DEVICE_KEY=你的BarkKey \
OPENAI_BASE_URL=https://你的中转站域名 \
OPENAI_MODEL=你的模型名 \
OPENAI_API_KEY=你的Key \
MACRO_EVENT_PROVIDER=no_active_event \
MACRO_EVENT_OPERATOR_REF=ops:macro-desk \
MACRO_EVENT_CONFIRMED_AT=2026-07-09T09:30:00+08:00 \
MACRO_EVENT_SOURCE_REF=calendar:forexfactory:2026-07-09:no-high-impact \
MACRO_EVENT_ASSERTION_HORIZON=6h \
MACRO_EVENT_VALID_UNTIL=2026-07-09T15:30:00+08:00 \
python3 tools/local_stack/smoke_local_stack.py --prod-actionable
```

发布门禁必须使用严格模式。严格模式下，如果外部 readiness 不足导致 structured skip，命令会返回非零退出码，避免把 skip 误记成成功：

```bash
BARK_DEVICE_KEY=你的BarkKey \
OPENAI_BASE_URL=https://你的中转站域名 \
OPENAI_MODEL=你的模型名 \
OPENAI_API_KEY=你的Key \
MACRO_EVENT_PROVIDER=no_active_event \
MACRO_EVENT_OPERATOR_REF=ops:macro-desk \
MACRO_EVENT_CONFIRMED_AT=2026-07-09T09:30:00+08:00 \
MACRO_EVENT_SOURCE_REF=calendar:forexfactory:2026-07-09:no-high-impact \
MACRO_EVENT_ASSERTION_HORIZON=6h \
MACRO_EVENT_VALID_UNTIL=2026-07-09T15:30:00+08:00 \
python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip
```

这个 profile 不启动本地 OpenAI mock 或本地 OKX mock。它强制使用：

- `NOTIFICATION_ENABLED=true`
- `DECISION_ENGINE=openai_compatible`
- `MARKET_DATA_PROVIDER=okx_public`
- `MACRO_EVENT_PROVIDER=no_active_event`
- `MACRO_EVENT_OPERATOR_REF`
- `MACRO_EVENT_CONFIRMED_AT`
- `MACRO_EVENT_SOURCE_REF`
- `MACRO_EVENT_ASSERTION_HORIZON`
- `MACRO_EVENT_VALID_UNTIL`

当前实现只支持 `disabled` 与 `no_active_event`。真实事件池或自动宏观事件 provider 尚未接入；在它们落地到 config loader、event provider 和测试前，`operator_assertion` / `event_pool` 这类未来值不能作为当前 release readiness。

缺少 readiness 时，默认命令会返回退出码 `0` 并输出 structured skip，便于本地无 secret 环境区分“外部依赖未配置”和“系统故障”。注意：structured skip is not production success。发布门禁必须加 `--fail-on-skip`，并要求 skip 返回非零。

示例 skip：

```json
{
  "ok": false,
  "smoke_profile": "prod_actionable",
  "skip_reason": "missing_readiness",
  "missing": [
    "BARK_DEVICE_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_API_KEY",
    "MACRO_EVENT_PROVIDER=no_active_event",
    "MACRO_EVENT_OPERATOR_REF",
    "MACRO_EVENT_CONFIRMED_AT",
    "MACRO_EVENT_SOURCE_REF",
    "MACRO_EVENT_ASSERTION_HORIZON",
    "MACRO_EVENT_VALID_UNTIL"
  ],
  "manual_execution_required": true,
  "auto_order_enabled": false,
  "exit_semantics": "skip_exit_0"
}
```

严格模式 skip 示例：

```json
{
  "ok": false,
  "smoke_profile": "prod_actionable",
  "skip_reason": "missing_readiness",
  "missing": ["BARK_DEVICE_KEY"],
  "manual_execution_required": true,
  "auto_order_enabled": false,
  "exit_semantics": "fail_on_skip"
}
```

本地 `--prod-actionable` 即使成功，也只说明本机 localhost 工作台完成了一次严格 readiness rehearsal；它必须带 `production_success=false` 和 `does_not_prove=hosted_prod_actionable`，不能替代 `tools/deployment/smoke_hosted_prod_actionable.py --api-base <public-https-api>`。只有 hosted run-level gate 和同环境 hosted visual gate 也通过后，才可以把这次链路记为真实生产可复核提醒证据。

本地 rehearsal 成功输出必须包含：

```json
{
  "ok": true,
  "smoke_profile": "prod_actionable",
  "proof_level": "local-prod-actionable-rehearsal",
  "production_success": false,
  "hosted_proof_required": true,
  "does_not_prove": "hosted_prod_actionable",
  "allowed": true,
  "decision_engine": "openai_compatible",
  "market_provider": "okx_public",
  "macro_event_provider": "no_active_event",
  "manual_execution_required": true,
  "auto_order_enabled": false,
  "notification": {
    "enabled": true,
    "status": "sent"
  }
}
```

同时必须在运行详情中看到真实 LLM interaction、exchange-native market evidence、Bark 发送状态。任何一种缺失都只能记录为“未完成生产证明”，不能用 fixture/mock/actionable staging 结果替代。

### 部署成功不等于生产提醒成功

`docker compose ps` 健康、`docker compose config` 通过、容器 healthcheck 成功，只说明容器和配置可加载。当前 compose healthcheck 使用 `show-config`，不会证明真实 LLM、真实 OKX public、Bark、`allowed=true` 都已通过。

部署后验收记录必须至少包含：

- `trace_id`
- `"smoke_profile": "prod_actionable"`
- `"ok": true`
- `"allowed": true`
- `"decision_engine": "openai_compatible"`
- `"market_provider": "okx_public"`
- `macro_event_provider` 和操作员对 `MACRO_EVENT_PROVIDER=no_active_event` 的确认人、确认时间、依据、适用窗口和有效期
- `"manual_execution_required": true`
- `"auto_order_enabled": false`
- Bark 通知 `sent`
- 运行详情中的真实 LLM interaction 和 exchange-native market evidence

缺少任一项，都只能记录为“部署启动成功，但未完成生产提醒成功证明”。`allowed=true` 只表示可进入人工复核，不代表系统已下单。

### 失败与跳过判定

- `skip_reason=missing_readiness`：外部依赖未配置或事件 readiness 未确认；不是系统成功，也不是交易建议。
- `allowed=false`：风控或事实门禁阻断；不可作为操作依据。
- Bark `failed`：通知链路失败，不会改变风控结论；需要修通知后重跑。
- `fixture` / `mock_real_engine` / `actionable_staging`：只能作为本地或受控证明，不可写成生产成功。

## 启动

推荐显式指定 project name。没有 `.env` 的新 checkout 可以先渲染默认配置：

```bash
docker compose -p crypto-alert-prod config
docker compose -p crypto-alert-prod up -d --build api frontend
```

默认 `docker compose up` 只加载 `config/default.yaml`，也就是 `SHADOW` + fixture 安全工作台形态；它用于先验证 API、前端、日志和手动提醒页面能启动，不访问真实 LLM，不要求 Bark，也不把本地结果写成生产成功。

已有 `.env` 时再显式指定：

```bash
docker compose -p crypto-alert-prod --env-file .env config
docker compose -p crypto-alert-prod --env-file .env up -d --build api frontend
```

生产意图工作台建议从模板开始：

```bash
cp .env.production.example .env
$EDITOR .env
docker compose -p crypto-alert-prod --env-file .env config
docker compose -p crypto-alert-prod --env-file .env up -d --build api frontend
```

如果要让容器工作台加载真实生产/可执行提醒 overlay，需要在 `.env` 中显式设置：

```env
CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml
```

没有这行时，Compose API 不会默认叠加 `prod.yaml` 或 `staging.yaml`；这是为了避免无 secret 新部署在首次手动运行时误入真实 LLM/Bark readiness 缺失状态。

`CONFIG_PATHS` 中任何显式路径拼错或文件缺失都应视为部署错误。API、CLI 和容器 healthcheck 会 fail-fast，而不是把缺失 overlay 当作空配置继续启动。典型错误输出如下：

```text
CONFIG_ERROR: Config file does not exist: config/prod.yaml
```

看到 `Config file does not exist` 时，应修正挂载目录、工作目录或 `.env` 里的 `CONFIG_PATHS`；不要把这种启动失败降级成 fixture 工作台继续验收。

这个 compose 文件默认发布 API `8010` 和前端 `3001`；如服务器已有服务占用端口，通过 `.env` 覆盖 `API_PORT`、`FRONTEND_PORT` 和 `NEXT_PUBLIC_API_BASE_URL`。前端构建时会把 `NEXT_PUBLIC_API_BASE_URL` 注入浏览器 bundle，因此生产反代域名或端口改变后需要重新构建前端镜像。

前端有两个 API base URL，含义不能混用：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010
API_INTERNAL_BASE_URL=http://api:8010
```

- `NEXT_PUBLIC_API_BASE_URL` 给浏览器使用，默认指向宿主机映射出来的 API 端口。
- `API_INTERNAL_BASE_URL` 给 Next.js 服务端渲染和 frontend 容器 healthcheck 使用，默认通过 Compose DNS 访问 `api:8010`。

如果部署在反向代理后，可以把 `NEXT_PUBLIC_API_BASE_URL` 改成浏览器可访问的 HTTPS API 域名；通常不需要改 `API_INTERNAL_BASE_URL`，除非你改变了 Compose 服务名或网络。frontend healthcheck 会从 frontend 容器内请求 `${API_INTERNAL_BASE_URL}/api/system/health`，所以 Compose 显示 healthy 才代表前端服务端也能访问 API。

默认启动只包含人工工作台 API/frontend。需要后台轮询 scheduler 时，显式开启运维 profile：

```bash
docker compose -p crypto-alert-prod --profile scheduler up -d manual-alert
```

`manual-alert` 的 CLI 会尊重 `scheduler.enabled` 配置。生产模板默认 `SCHEDULER_ENABLED=false`，因此直接启动 scheduler profile 会被拒绝并输出 `SCHEDULER_DISABLED: scheduler.enabled=false`。只有在确实需要后台轮询时，先在生产环境变量或配置 overlay 中显式设置 `SCHEDULER_ENABLED=true` / `scheduler.enabled=true`，再启动 `manual-alert`。

后台轮询仍然只生成人工提醒，不自动下单；生产成功证明仍以 `prod_actionable` 严格门禁为准。

## 工作台服务验收

查看工作台服务：

```bash
docker compose -p crypto-alert-prod ps
docker compose -p crypto-alert-prod logs -f api
docker compose -p crypto-alert-prod logs -f frontend
```

API 健康检查：

```bash
curl -fsS http://127.0.0.1:8010/api/system/health
```

前端工作台：

```bash
open http://127.0.0.1:3001
```

手动触发 API 入口：

```bash
curl -fsS http://127.0.0.1:8010/api/runs/manual \
  -H 'content-type: application/json' \
  -d '{"symbol":"ETH-USDT-SWAP","query":"评估 ETH 未来 6h 是否值得人工追多","horizon":"6h","alert_channel":"bark"}'
```

建议把手工 curl 后再运行一次标准 hosted workbench smoke：

```bash
python3 tools/deployment/smoke_hosted_workbench.py \
  --api-base http://127.0.0.1:8010 \
  --frontend-base http://127.0.0.1:3001 \
  --symbol ETH-USDT-SWAP \
  --query "部署后工作台 smoke：验证人工提醒入口和详情页" \
  --horizon 6h
```

成功输出会包含 `"smoke_profile": "hosted_workbench"`、`trace_id`、`manual_execution_required=true`、`auto_order_enabled=false`、`production_config_required=false`、`production_config_ready=<API readiness>` 和 `hosted_runtime_only_not_prod_actionable=true`。该脚本只连接已经启动的 API/frontend，不启动容器、不拉镜像、不发送真实交易指令；它会检查：

- `GET /api/system/health`
- `GET /api/system/config`
- 前端首页返回 HTML
- `POST /api/runs/manual`
- `GET /api/runs/{trace_id}` 的 `business_summary` 与 `result_review`
- 前端 `/runs/{trace_id}` 返回 HTML

这一步只证明 hosted API/frontend 入口和产品投影闭环可达，不是 `prod-actionable` 成功。默认 `docker compose up` 的 `config/default.yaml` fixture 工作台可以通过这个 runtime smoke，但不能被描述成生产配置。

如果要把“真实 Docker compose build/up + hosted smoke + cleanup”作为可重复 gate，而不是手工执行多条命令，可以使用封装脚本：

```bash
python3 tools/deployment/smoke_docker_hosted_runtime.py
```

默认模式会：

- 使用隔离端口 `18010/13001`。
- 使用可覆盖的 ECR base image 默认值，降低 Docker Hub metadata 超时影响。
- 执行 `docker compose -p crypto-alert-runtime-smoke up -d --build api frontend`。
- 调用 `tools/deployment/smoke_hosted_workbench.py` 证明 API/frontend/manual-run/detail projection 可达。
- 再调用 `tools/deployment/smoke_hosted_workbench.py --require-prod-config`，并期望默认 fixture 工作台被拒绝。
- 最后执行 `docker compose -p crypto-alert-runtime-smoke down --remove-orphans`。

默认输出的 proof level 是 `hosted-runtime`，并带 `hosted_runtime_only_not_prod_actionable=true`。如果 strict negative 没有拒绝 fixture config，脚本会失败，避免把默认容器误写成 `prod-config`。

需要生产意图容器验收时，应先用 `.env.production.example` 填好真实 readiness 并启动目标容器，然后使用 `smoke_hosted_workbench.py --require-prod-config`、`smoke_hosted_prod_actionable.py`，以及 horizon 成熟后的 `smoke_hosted_real_outcome_collection.py`；不要把默认 `smoke_docker_hosted_runtime.py` 的 fixture proof 写成生产成功。`smoke_local_stack.py --prod-actionable --fail-on-skip` 只作为本地严格 readiness rehearsal，不替代 hosted 证据。

如果这次验收要用“生产工作台配置”的口径，必须加严格配置断言：

```bash
python3 tools/deployment/smoke_hosted_workbench.py \
  --api-base http://127.0.0.1:8010 \
  --frontend-base http://127.0.0.1:3001 \
  --symbol ETH-USDT-SWAP \
  --query "生产工作台配置 smoke：验证非 fixture 配置和人工提醒入口" \
  --horizon 6h \
  --require-prod-config
```

`--require-prod-config` 会在发起手动提醒前读取 `/api/system/config` 并拒绝以下情况：

- `decision.engine` 不是 `openai_compatible`
- `decision.final_input_mode` 不是 `legacy_prompt`
- `decision.candidate_sidecar_mode` 不是 `disabled`
- `market_data.provider` 不是 `okx_public`
- `market_data.okx_base_url` 不是空值或 `https://www.okx.com`
- `readiness.market_data.status` 是 `unsafe`（生产要求 `readiness.market_data.status!=unsafe`）
- `notification.enabled` 不是 `true`
- `macro_event.provider` 不是 `no_active_event`
- `workflow.execution_mode` 不是 `legacy_baseline`
- `readiness.prod_actionable.status` 不是 `ready`

严格配置通过时，输出会包含 `"production_config_required": true` 和 `"production_config_ready": true`。如果默认 fixture 工作台、缺少生产 overlay、或者 `okx_public` 指向本地 mock/unsafe readiness 被拿来做生产配置验收，脚本会非零退出；不要把这种失败改写成“工作台已生产可用”。是否能称为真实生产可执行提醒，仍必须满足后文 `prod_actionable` 成功契约：真实外部 LLM、真实 OKX public（`market_data.okx_base_url` 为空或 `https://www.okx.com` 且不是 `readiness.market_data.status=unsafe`）、`MACRO_EVENT_PROVIDER=no_active_event`、Bark `sent`、`allowed=true`，并保持 `manual_execution_required=true` 和 `auto_order_enabled=false`。

严格配置通过后，还要跑 hosted run-level production proof：

```bash
python3 tools/deployment/smoke_hosted_prod_actionable.py \
  --api-base <public-https-api> \
  --symbol ETH-USDT-SWAP \
  --query "Hosted prod-actionable smoke：验证真实人工提醒证据链" \
  --horizon 6h \
  --proof-output hosted-prod-actionable-proof.json
```

该脚本会提交一笔 hosted manual run，并要求 `--api-base` 是 public HTTPS API base；localhost、内网/私网 IP 和非 HTTPS URL 默认会被拒绝，不能用本地可达性冒充 hosted production 证据。详情页 API 还必须证明：

- `trace.allowed=true` 与 `plan_run.verdict.allowed=true`
- `parsed_plan.manual_execution_required=true`
- `agent_audit_view.input_lineage.production_final_input_mode=legacy_prompt`
- `query_semantics.drives_final_input=false`
- `llm_interactions` 中存在 `component=decision.final`、`provider=openai_compatible`、`status=ok` 的真实模型调用记录
- `agent_audit_view.evidence_sources` 或 `source_freshness` 中存在 `exchange_native + fresh + can_satisfy_execution_fact`
- `notification_history` 或 `business_summary.notification` 证明 Bark `sent`

这一步通过才是 hosted run-level `prod-actionable` 证据。它仍不会下单，只证明可进入人工复核的提醒已经由真实外部依赖和通知链路完成。

通过时，`--proof-output` 会写出 `hosted-prod-actionable-proof.json`。该文件记录 `schema_version=2026-07-09.hosted-prod-actionable-proof.v1`、`trace_id`、`api_base_url`、`config_digest`、`run_detail_digest`、`run_detail_summary`、`prod_actionable_proven=true` 和 `does_not_prove=hosted_real_outcome`。manifest 只保存摘要和 digest，不保存 raw prompt、raw response、Bark device key 或 secret；它是 API run-level 生产证据，应与后续 hosted visual manifest 一起归档，但不能替代 horizon 成熟后的 real-outcome gate。

严格 API 证据通过后，还要跑同一 hosted trace 的前端真实渲染 gate：

```bash
PLAYWRIGHT_REUSE_EXISTING_STACK=true \
PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true \
PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> \
PLAYWRIGHT_API_BASE_URL=<public-https-api> \
npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts

PLAYWRIGHT_REUSE_EXISTING_STACK=true \
PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true \
PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> \
PLAYWRIGHT_API_BASE_URL=<public-https-api> \
npm --prefix frontend run e2e -- --project=chromium-mobile hosted-prod-actionable-visual.spec.ts
```

该 Playwright gate 不启动本地 fixture 栈，而是复用已经运行的生产意图 hosted API/frontend。desktop and mobile 两个 project 都必须通过，才能作为 hosted-positive visual proof。它会：

- 读取 `/api/system/config`，要求 `openai_compatible`、`legacy_prompt`、`okx_public`、Bark enabled、manual-only safety 和 `readiness.prod_actionable=ready`。
- 拒绝 `market_data.okx_base_url` 非空且不是 `https://www.okx.com`、拒绝 `readiness.market_data.status=unsafe`、拒绝 `mock/fixture/fake/stub/test/local` 等非生产模型名。
- 提交一笔 fresh hosted manual run。
- 读取同一条 `/api/runs/{trace_id}`，要求真实 `decision.final` LLM、exchange-native fresh execution evidence、同一 run 的 Bark `sent` row、HTTP 2xx `status_code`、Bark 时间戳不早于本次 manual-run start，以及 `allowed=true`。
- 打开同一条 `/runs/{trace_id}` 页面，要求 `模型审阅`、证据摘要、通知历史、后续复盘和深滚动布局健康。
- 拒绝 raw JSON、`request_json`、`response_json`、secret、DOM overlap、横向溢出和移动端响应式布局缺陷出现在默认产品详情页。
- 要求 `PLAYWRIGHT_FRONTEND_BASE_URL` 和 `PLAYWRIGHT_API_BASE_URL` 是 public HTTPS URL，并在 hosted-positive 模式下做 DNS 解析；解析到 local/private/reserved 地址的 hostname 会被拒绝，不能用公网样式域名指向本地或内网来冒充 hosted production visual proof。
- 在 Playwright output 目录写出 `hosted-prod-actionable-proof-manifest.json`，并 attach 到报告。该 manifest 记录 `trace_id`、`frontend_base_url`、`api_base_url`、`config_digest`、`run_detail_digest`、`run_detail_summary`、`screenshot_path` 和 `does_not_prove=hosted_real_outcome`，同时保留 full-page screenshot 作为页面证据。manifest 只保存摘要和 digest，不保存 raw prompt、raw response、device key 或 secret；它证明同一 hosted trace 的视觉和 run-level 谓词通过，但仍不能替代 horizon 成熟后的 real-outcome gate。

没有 `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` 时，`hosted-prod-actionable-visual.spec.ts` 只做负向保护：证明当前默认 fixture/local Playwright stack 不能被误标成 hosted prod-actionable visual proof。不要把这个负向通过写成生产视觉验收。

## 查看状态

```bash
docker compose -p crypto-alert-prod ps
docker compose -p crypto-alert-prod logs -f api
docker compose -p crypto-alert-prod logs -f frontend
```

## 手动触发一次计划

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml run-once --symbol ETH-USDT-SWAP --query "评估 ETH 未来 6h 是否值得人工追多" --horizon 6h
```

这条 CLI 手动入口与 API `POST /api/runs/manual` 的 query 语义一致：`--query` 是 operator audit note，当前不会直接驱动 facts requirement、worker selection 或 final input。`requested_horizon` 与 `plan_horizon` 可能不同；前者是请求/复核上下文，后者是本次生成计划自身的 horizon。

## Bark 通知排查

Bark 只负责把提醒推送到手机，不是授权、确认或自动下单通道。无论 Bark 成功还是失败，系统都必须保持：

- `manual_execution_required=true`
- `auto_order_enabled=false`
- 不接 OKX Trade Key
- 不执行自动下单、撤单、提现

### 1. 单独验证 Bark Key 和手机链路

这一步只证明 Bark device key、手机通知权限和网络可用，不证明真实 LLM、真实 OKX、风控放行或生产提醒成功：

```bash
BARK_DEVICE_KEY=你的BarkKey \
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml test-bark
```

如果这里失败，先处理 Bark 自身问题：

- `.env` 中 `BARK_DEVICE_KEY` 是否是 Bark App 里复制的完整 key。
- iPhone 是否允许 Bark 通知，是否开启了勿扰/专注模式。
- 服务器是否能访问 `notification.bark_base_url`。
- 自建 Bark Server 时，确认 HTTPS、反向代理、证书和访问日志。

### 2. 本地真实 API/前端链路发 Bark

这一步启动真实本地 API 和 Next.js 前端，通过 `POST /api/runs/manual` 触发一次手动提醒，并要求 journal 里出现 Bark `sent` 记录：

```bash
BARK_DEVICE_KEY=你的BarkKey \
python3 tools/local_stack/smoke_local_stack.py --with-bark
```

成功输出会包含：

```json
{
  "notification_enabled": true,
  "notification": {
    "enabled": true,
    "status": "sent"
  }
}
```

这个 profile 默认仍可能使用 fixture 行情/决策；它只证明“真实 API/manual-run -> notification sink -> journal -> 前端可见”链路，不是真实生产可执行提醒成功。

### 3. 在页面检查通知历史

任何带通知的 run 都应能在详情页看到通知历史：

1. 打开 `/runs/{trace_id}`。
2. 停留在默认 `建议摘要` 页。
3. 查看 `通知历史` 区域。

期望：

- 无通知：显示 `暂无通知记录` 和 `通知未启用`。
- 成功：显示 `Bark 已发送`、渠道 `Bark`、发送时间、`服务响应 200`。
- 失败：显示 `发送失败`、服务响应码和 `失败原因`。

页面不应显示 `notification_history`、raw 字段名 `status_code`、`plan_id`、`device_key`、`BARK_DEVICE_KEY`、Bark URL 或 raw payload。服务响应码应以 `服务响应 200` 这类产品文案展示。若出现这些字段，视为产品页泄漏工程/密钥语义，需要先修前端或 API 投影再发布。

## 诊断/raw 路由边界

默认产品路径不应要求用户阅读 JSON 或 raw prompt/completion。后端也不能只依赖前端隐藏：

- `GET /api/runs/{trace_id}` 默认不返回 `request_json` / `response_json`。
- `GET /api/runs/{trace_id}?include_payloads=true` 只有在
  `DIAGNOSTIC_ROUTES_ENABLED=true` 时允许，否则返回
  `403 diagnostic_routes_disabled`。
- `POST /api/eval/runs` 的 `mode=judge_openai` 同样只允许在诊断环境运行；
  `judge_only_fixture` 等本地评测模式不受影响。
- `GET /api/eval/runs/{eval_run_id}` 和
  `GET /api/eval/runs/{eval_run_id}/promotion-artifacts` 会返回 replay 详情或发布证据，
  也属于诊断路由；默认环境返回 `403 diagnostic_routes_disabled`。
- `POST /api/eval/runs` 的默认本地/规则模式仍可用于 sidecar 质量复盘，但默认响应和
  `GET /api/eval/runs` 只返回产品安全 metadata：当前仅保留 `financial_quality_gate`，
  不返回 report refs、promotion artifacts、release gate、replay 或 side-effect deltas。
- 非生产本地 smoke/Playwright 为了验证脱敏行为会显式打开诊断路由；`--prod-actionable`
  保持诊断关闭。这些工程测试环境不代表生产公开部署允许 raw payload。

共享用户环境发布前，仍应继续把 raw/matrix 诊断页做成“摘要优先、证据可展开”，并给
`JsonDetails` 增加前端防御性脱敏；后端 gate 解决的是绕过问题，不等于诊断页视觉和信息架构已经产品化。

### 4. Bark 失败如何处理

- `test-bark` 失败：Bark key、手机通知权限、Bark Server 或网络问题；不需要排查 LLM/OKX。
- `--with-bark` 失败但 `test-bark` 成功：检查 API 日志、`notifications` 表、`NOTIFICATION_ENABLED=true`、`notification.provider=bark`，以及 `BARK_DEVICE_KEY` 是否进入 API 进程环境。
- `prod-actionable` 中 Bark `failed`：不是生产成功；修复通知链路后重跑 `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`。
- Bark 成功但 `allowed=false`：说明通知触达了，但风控或事实门禁阻断；不得把提醒作为操作依据。
- Bark 成功且 `allowed=true`：仍只代表可进入人工复核，用户必须打开 OKX 手动核对价格、事件、仓位和风险。

## Outcome 收集与金融质量复盘

Outcome 只写 eval sidecar，不写生产提醒 journal，不发 Bark，不触发任何交易副作用。它用于回答“历史提醒在到期窗口后的市场结果是什么”，不能替代 prod-actionable smoke。

数据位置：

```text
./data/eval/crypto-outcomes.db
```

### 真实 outcome 收集

等提醒的 horizon 成熟后，运行：

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml collect-outcomes --limit 50
```

可按交易对过滤：

```bash
docker compose -p crypto-alert-prod run --rm manual-alert \
  crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml collect-outcomes --symbol ETH-USDT-SWAP --limit 50
```

输出字段含义：

- `collected`：已写入 OutcomeStore 的成熟 outcome 数。
- `skipped`：未成熟、缺计划、失败 trace、无可评分目标位，或行情窗口不可用的数量。
- `errors`：拉取历史 K 线或构造 outcome 时的错误明细。

只有 `source_type=exchange_native`、`matured=true`、`can_score=true` 的 outcome 才能进入真实金融质量评分。样本数未达到配置阈值前，`Financial Quality` 仍只能作为 advisory，不得写成“策略有效已证明”。

### 真实 outcome 证据门禁

`collect-outcomes` 运行后，建议对已经启动的 API 再跑一次机器可读门禁，确认 eval sidecar 中确实出现至少一条真实、成熟、可评分的交易结果样本：

```bash
python3 tools/deployment/smoke_real_outcome_evidence.py \
  --api-base http://127.0.0.1:8010 \
  --symbol ETH-USDT-SWAP \
  --collected-after 2026-07-09T00:00:00+00:00
```

成功输出会包含：

```json
{
  "smoke_profile": "real_outcome_evidence",
  "real_exchange_native_matured_outcome_proven": true,
  "prod_actionable_alert_proven": false
}
```

这个门禁只接受满足以下条件的样本：

- `source_type=exchange_native`
- `matured=true`
- `can_score=true`
- `window.can_score_execution_outcome=true`
- 如果传了 `--symbol`，outcome 顶层 `symbol` 与 `window.symbol` 必须都是同一 symbol
- 如果传了 `--collected-after`，`window.collected_at` 必须是 timezone-aware ISO 时间，且不能早于该时间
- 建议动作是可评分交易动作，不是 `no trade`
- `entry_price`、`stop_price`、`target_1` 和窗口 OHLC 都存在

没有匹配样本时，脚本会以非零退出并输出 `real_exchange_native_matured_outcome_proven=false`。这一步证明“真实 outcome 证据已进入 API 可查询的 sidecar”，不是 prod-actionable 成功；它不证明 Bark 已发送，也不证明某一次手动提醒已经满足真实 LLM、真实 OKX public、`MACRO_EVENT_PROVIDER=no_active_event` 和 `allowed=true`。

### Hosted outcome 采集 + 证据闭环门禁

生产或预生产 hosted 环境不要只跑“已有 evidence 查询”。要证明本次运维动作不仅报告了 `collected>0`，而且后置 API 能看到新增或本轮更新的真实 outcome evidence，应在同一宿主机、同一 compose project、同一 `DATA_DIR`/volume 上运行：

```bash
python3 tools/deployment/smoke_hosted_real_outcome_collection.py \
  --api-base http://127.0.0.1:8010 \
  --symbol ETH-USDT-SWAP \
  --limit 50 \
  --min-count 1 \
  --same-host-data-dir-confirmed \
  --proof-output hosted-real-outcome-proof.json
```

该脚本默认执行：

1. 读取 `GET /api/system/config` 做 `api_config_preflight`。
2. collection 前先跑 `python3 tools/deployment/smoke_real_outcome_evidence.py --api-base ... --symbol ... --collected-after <gate_started_at> --min-count ...`，记录本轮 gate start 之后已有的同一 symbol matched refs；没有已有真实 outcome 时不会失败。
3. 运行 `docker compose -p crypto-alert-prod run --rm manual-alert crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml collect-outcomes --limit 50 ...`
4. collection 后再跑 `python3 tools/deployment/smoke_real_outcome_evidence.py --api-base ... --symbol ... --collected-after <gate_started_at> --min-count ...`

默认严格语义：

- 必须显式传入 `--same-host-data-dir-confirmed`，确认 collector 写入的 `./data/eval/crypto-outcomes.db` 与 hosted API 读取的是同一个 `DATA_DIR`/volume；缺少确认会以 exit `2` 返回 `same_host_data_dir_confirmation_required`。
- `api_config_preflight` 必须证明 outcome 相关生产意图：`manual_execution_required=true`、`auto_order_enabled=false`、`decision.engine=openai_compatible`、`decision.final_input_mode=legacy_prompt`、`decision.candidate_sidecar_mode=disabled`、`workflow.execution_mode=legacy_baseline`、`market_data.provider=okx_public`。
- `market_data.okx_base_url` 必须为空或 `https://www.okx.com`；`readiness.market_data.status=unsafe` 会被拒绝，避免本地 mock OKX 或 localhost endpoint 产出的 exchange-shaped outcome 被误写成 real-outcome proof。
- `collect-outcomes` 退出码非 0 时立即失败，不继续查 evidence。
- `collect-outcomes` stdout 必须是 JSON object，且 `collected` 必须是 integer；当 `collected>0` 时，还必须包含非空 `collected_refs`，每条 ref 至少包含 `decision_ref`、`evaluation_target`、`symbol`、`window_name` 和 timezone-aware `collected_at`。
- `collect-outcomes` JSON 默认必须没有 `errors`；输出中 `collection_errors_allowed=false`。只有排障时显式传 `--allow-collection-errors` 才会继续后置 evidence 检查。
- `collect-outcomes` 输出 `collected=0` 时返回 `no_new_outcome_collected`，不会用旧 outcome 或历史 sidecar 证据伪造成“本次 collection gate 成功”。
- 后置 evidence stdout 必须显式包含 `ok=true`、`smoke_profile=real_outcome_evidence`、`real_exchange_native_matured_outcome_proven=true`、`prod_actionable_alert_proven=false`。
- 前后两次 evidence gate 都限定同一 symbol，并且只接受 `window.collected_at >= gate_started_at` 的 matched outcome；其他交易对的并发样本或本轮之前的旧样本不能满足本次 proof。
- 后置 API evidence 必须相对 collection 前出现新增 matched ref，或同一 matched ref 的 `collected_at` 在本轮 gate 开始后更新；该 matched ref 还必须精确命中本次 `collect-outcomes` 输出的 `collected_refs` 中的 `(decision_ref, evaluation_target, symbol, window_name)`。同一交易对但不属于本次 `collected_refs` 的并发 outcome 也不能关闭本次 gate；否则返回 `real_outcome_evidence_not_linked_to_collection`。
- 后置 evidence gate 仍只接受 `source_type=exchange_native`、`matured=true`、`can_score=true`、`window.can_score_execution_outcome=true` 且价位/OHLC 齐备的交易动作样本。

成功输出会包含：

```json
{
  "smoke_profile": "hosted_real_outcome_collection",
  "proof_level": "real-outcome",
  "api_config_preflight": "production_outcome_config_ready",
  "real_exchange_native_matured_outcome_proven": true,
  "prod_actionable_alert_proven": false,
  "collection_errors_allowed": false,
  "new_refs_verified": true,
  "new_or_updated_ref_details": [
    {
      "decision_ref": "trace-real-1:legacy_final",
      "evaluation_target": "legacy_final",
      "symbol": "ETH-USDT-SWAP",
      "window_name": "ETH-USDT-SWAP:21600s"
    }
  ]
}
```

通过时，`--proof-output` 会写出 `hosted-real-outcome-proof.json`，包含 `schema_version=2026-07-09.hosted-real-outcome-proof.v1`、`collect_outcomes_digest`、`real_outcome_evidence_digest`、`outcome_summary`、`new_or_updated_refs`、`new_or_updated_ref_details` 和 `does_not_prove=hosted_prod_actionable`。这个 manifest 只保存 collection/evidence 摘要和 digest，不保存 raw prompt、raw response、Bark device key 或 secret。

这仍然不是 `prod-actionable` 成功；它不提交新的人工提醒，不证明 Bark `sent`，也不证明真实 LLM 决策链路。它只证明“操作员确认的同 DATA_DIR hosted collector 运维动作 + collection 前后 API matched refs 对比”形成了真实 outcome 证据闭环。

### 本地 outcome 采集闭环证明

为了防止 `collect-outcomes`、OKX 历史 K 线、OutcomeStore、API 和前端质量页之间再次断链，可以运行本地 collector wiring smoke：

```bash
python3 tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture
```

这个命令会：

- 启动真实本地 FastAPI 和前端。
- 启动本地 mock OKX，并覆盖 `/api/v5/market/history-candles`。
- 使用隔离的 `.tmp/smoke/data` 作为 API `DATA_DIR`。
- seed 一条已成熟的历史提醒 journal 记录，包含 `legacy_final` 和严格 audit-only `swarm_candidate_final`。
- 调用真实 CLI：`python -m crypto_manual_alert.cli --config <tmp-config> collect-outcomes --limit 5`。
- 校验 `/api/eval/outcomes` 出现 `legacy_final`、`swarm_candidate_final`、`hold_no_trade` 三个 outcome。
- 校验 `/eval?tab=quality` 用产品文案展示 `交易所原生样本`、`最终建议链路`、`候选建议链路`、`不操作基线`，且不泄漏 `exchange_native`、`legacy_final`、`swarm_candidate_final`、`hold_no_trade`、`decision_ref` 等内部字段。

预期输出包含：

```json
{
  "smoke_profile": "collect_outcomes_fixture",
  "mock_okx": "http://127.0.0.1:8012",
  "outcome_collection_profile": "local_mock_okx_collector_wiring_only",
  "collected_exchange_native_outcomes": 3,
  "real_financial_quality_proven": false
}
```

注意：这个 smoke 里的 `source_type=exchange_native` 是由本地 mock OKX 提供的历史 K 线形态，用来证明 collector wiring 和 UI 可见链路；它不是生产金融质量证明。真实金融质量仍必须来自真实 OKX public 历史行情、真实提醒、成熟观察窗口和足够样本量。

### 本地 mocked outcome 可视化证明

本地 Playwright/e2e 为了防止 Eval 页面退化为空壳，会通过 local stack seed 一条显式 mock outcome：

```bash
python3 tools/local_stack/start_local_stack.py --frontend-mode production --reset-data --seed-mock-outcome --keep-running
```

也可以直接运行 smoke 级门禁。这个命令会启动真实本地 API/Next.js 前端，使用隔离的 `.tmp/smoke/data` 作为 API `DATA_DIR`，seed mock outcome 后同时校验 `/api/eval/outcomes` 和 `/eval?tab=quality` 的可见文本：

```bash
python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome
```

API/smoke 输出中的原始样本字段为：

- `decision_ref=mocked-outcome-seed`
- `source_type=mocked_outcome`
- `can_score=false`
- `unscored_reason=price_source_not_exchange_native`

前端 `/eval?tab=quality` 的产品可见文本不应直接暴露这些内部 ID/枚举；页面应显示 `样本 1`、`本地展示样本`、`价格不是交易所原生样本`、`不可评分` 等可读说明。看到 `mocked-outcome-seed`、`mocked_outcome` 或 `price_source_not_exchange_native` 出现在产品页正文中，应视为 UI 回归。

smoke 输出会包含：

```json
{
  "mock_outcome_seeded": true,
  "mock_outcome_decision_ref": "mocked-outcome-seed",
  "mock_outcome_quality_scope": "visibility_only_not_financial_quality"
}
```

这只证明 OutcomeStore -> `/api/eval/outcomes` -> Eval 页面表格的可见链路；它不代表真实 OKX 历史行情、真实模型判断、真实 Bark 通知或真实金融质量。

## 暂停和恢复

暂停：

```bash
docker compose -p crypto-alert-prod --profile scheduler stop manual-alert
```

恢复：

```bash
docker compose -p crypto-alert-prod --profile scheduler up -d manual-alert
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

1. 备份 `.env`（如果已创建）和 `data/crypto-alert.db`。
2. 拉取新代码或替换项目文件。
3. 先校验配置：

```bash
docker compose -p crypto-alert-prod config
# 如果已创建 .env，也可以显式指定：
docker compose -p crypto-alert-prod --env-file .env config
```

4. 重建并启动：

```bash
docker compose -p crypto-alert-prod up -d --build
# 如果已创建 .env，也可以显式指定：
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
