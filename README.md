# crypto-manual-alert

AI-assisted crypto manual alert and evaluation workbench.

本项目定位是“人工确认的加密货币操作提醒”，不是自动交易系统。系统可以抓取行情、调用固定 crypto skill、生成操作计划、记录 trace，并通过 Bark 强提醒用户手动核对；当前手动提醒阶段明确不提供下单、撤单、提现能力。

## 技术栈

- Python 3.11+：FastAPI、Agent workflow、skill 调用、行情、LLM、Bark、Trace/Eval。
- TypeScript / Next.js：本地工作台、手动 query、Runs/Trace 查看、后续 Eval/Candidates 页面。
- SQLite：默认本地存储，不依赖 Redis、队列、Temporal、向量库或外部 LLMOps 服务。

## 当前能力

- `GET /api/system/health`：API 健康检查。
- `POST /api/runs/manual`：提交一次手动分析，返回 `trace_id`、计划摘要和风控结论。
- `GET /api/runs`：查询最近运行记录。
- `GET /api/runs/{trace_id}`：查询 trace、span、LLM 摘要、badcase，默认隐藏原始 prompt/completion payload。
- CLI 手动入口：`crypto-alert run-once --symbol ETH-USDT-SWAP --query "评估 ETH 未来 6h 是否值得人工追多" --horizon 6h`。

`run-once --query` 当前承载 operator audit note：系统会保存这段手动查询上下文用于 trace、审计和前端展示；`--horizon` 当前是手动复核/后续采集上下文。现阶段生产规划仍由 symbol/config、行情事实、LLM 输出和风控门禁共同决定，不把自由文本查询或请求 horizon 直接当作可执行交易指令。CLI 输出会包含 `trace_id`、`business_summary`、`notification`、`result_review`、`requested_horizon` 和 `plan_horizon`，便于把一次手动触发与后续详情、通知状态、结果复盘串起来。

## 当前架构状态

当前生产决策链仍是 legacy prompt 主链，不是 Agent Swarm 接管。真实链路是 `RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> final LLM -> parser/gates -> journal/notification`。

仓库内已有 `agent_swarm/`、`lead/`、`artifacts/`、`decision/` 等受控 Agent Swarm 迁移模块，但目前默认只作为 shadow audit、candidate/replay 和结构化审计侧路使用；`DecisionInput` 仍不是生产 FinalDecisionAgent 的默认输入，`decision.final_input_mode` 默认仍是 `legacy_prompt`。当前交付方向以 `docs/formal/37-真实多Agent对抗审查与交付方向裁决.md` 为准：先跑通人工提醒主流程和真实 prod-actionable 证明，后续 Swarm/candidate 切换必须单独 release review；`31/32/34` 保留为历史计划和背景材料。

## 本地启动

```powershell
cd <repo-root>
python -m pip install -e .
python -m pytest
uvicorn crypto_manual_alert.api.app:app --reload
```

前端工作台位于 `frontend/`，启动前先设置：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
```

上面是手动开发启动方式，API 默认使用 `8000`。完整本地全链路 smoke 会使用隔离端口：API `8010`、前端 `3001`、mock OpenAI `8011`、mock OKX `8012`、Server Component fault API `8013`。

## 环境变量

复制 `.env.example` 后只在本地填写真实值，不要提交 `.env`。

生产工作台配置不要从空白 `.env` 手拼。先复制生产意图模板，再填写真实外部依赖和事件断言：

```bash
cp .env.production.example .env
chmod 600 .env
```

随后启动 hosted workbench 并跑严格配置 smoke：

```bash
docker compose -p crypto-alert-prod --env-file .env up -d --build api frontend
python3 tools/deployment/smoke_hosted_workbench.py \
  --api-base http://127.0.0.1:8010 \
  --frontend-base http://127.0.0.1:3001 \
  --symbol ETH-USDT-SWAP \
  --query "生产工作台配置 smoke：验证非 fixture 配置和人工提醒入口" \
  --horizon 6h \
  --require-prod-config
```

`smoke_hosted_workbench.py --require-prod-config` 只证明 hosted workbench 使用生产意图配置；真正 `prod-actionable` 成功还必须看到真实 LLM、真实 OKX public、Bark `sent`、完整 `no_active_event` 人工断言和 `allowed=true`。
严格配置 smoke 还会拒绝 `market_data.okx_base_url` 指向本地/mock endpoint 的配置；生产意图下该字段必须为空或 `https://www.okx.com`，且 `readiness.market_data.status=unsafe` 会失败，不能用 exchange-shaped mock OKX 冒充真实 OKX public。

生产环境里，配置 strict smoke 之后还应跑 hosted run-level 证据 gate：

```bash
python3 tools/deployment/smoke_hosted_prod_actionable.py \
  --api-base <public-https-api> \
  --symbol ETH-USDT-SWAP \
  --query "Hosted prod-actionable smoke：验证真实人工提醒证据链" \
  --horizon 6h \
  --proof-output hosted-prod-actionable-proof.json
```

`smoke_hosted_prod_actionable.py` 会提交一笔 hosted manual run，并要求 `--api-base` 是 public HTTPS API base；localhost、内网/私网 IP 和非 HTTPS URL 默认会被拒绝，不能用本地可达性冒充生产证据。这一笔详情还必须同时满足 `allowed=true`、`decision.final` OpenAI-compatible `status=ok`、真实 OKX public 配置（`market_data.okx_base_url` 为空或 `https://www.okx.com`，且不是 `readiness.market_data.status=unsafe`）、exchange-native fresh execution evidence、Bark `sent`、`legacy_prompt` final input 和 manual-only safety。缺任一项都不能叫生产成功。
通过时，`--proof-output` 会写出 `hosted-prod-actionable-proof.json`，包含 `trace_id`、`api_base_url`、`config_digest`、`run_detail_digest`、`run_detail_summary` 和 `does_not_prove=hosted_real_outcome`。这个文件只保存摘要/digest，不保存 raw prompt、raw response、Bark device key 或 secret；它是 API run-level 生产证据，不替代后面的 visual gate 或 horizon 成熟后的 real-outcome gate。

同一生产环境还应跑前端真实渲染 gate，确保同一条 hosted trace 在页面上显示为可读提醒，而不是 raw JSON 或内部对象：

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

这个 Playwright gate 必须在 desktop and mobile 两个 project 上通过，才算 hosted-positive visual proof。每个 project 会提交一笔 hosted manual run，复查同一条 `/api/runs/{trace_id}`，再打开同一条 `/runs/{trace_id}` 页面。它不只看页面文本，还会同步执行严格证据谓词：真实 OKX public 配置（`market_data.okx_base_url` 为空或 `https://www.okx.com`，且不是 `readiness.market_data.status=unsafe`）、非 `mock/fixture/fake/stub/test/local` 模型名、exchange-native fresh execution evidence、同一 run 的 Bark `sent` row、HTTP 2xx `status_code`，且 Bark 时间戳不能早于本次 manual-run start。页面侧还要求 `模型审阅`、证据摘要、Bark 状态和深滚动布局可见，同时不得出现 raw JSON、`request_json`、`response_json`、secret、DOM overlap 或响应式布局缺陷。没有 `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` 时，它只做负向保护：证明默认 fixture/local stack 不能被误标成生产视觉验收。

`PLAYWRIGHT_FRONTEND_BASE_URL` 和 `PLAYWRIGHT_API_BASE_URL` 必须是 public HTTPS URL，并且 hosted-positive visual gate 会做 DNS 解析；任何解析到 local/private/reserved 地址的 hostname 都会被拒绝，不能用公网样式域名指向本地或内网来冒充 hosted production visual proof。

positive gate 通过时，Playwright output 目录会生成并 attach `hosted-prod-actionable-proof-manifest.json`。该 manifest 包含 `trace_id`、`frontend_base_url`、`api_base_url`、`config_digest`、`run_detail_digest`、`run_detail_summary`、`screenshot_path` 和 `does_not_prove=hosted_real_outcome`；它只保存摘要/digest 和 full-page screenshot 路径，不保存 raw prompt、raw response、Bark device key 或 secret。这个 manifest 证明同一 hosted trace 的 run-level 谓词和真实页面渲染通过，但仍不能替代 horizon 成熟后的 real-outcome gate。

等真实提醒 horizon 成熟后，再跑 hosted real-outcome collection gate：

```bash
python3 tools/deployment/smoke_hosted_real_outcome_collection.py \
  --api-base <public-https-api> \
  --symbol ETH-USDT-SWAP \
  --limit 50 \
  --min-count 1 \
  --same-host-data-dir-confirmed \
  --proof-output hosted-real-outcome-proof.json
```

`smoke_hosted_real_outcome_collection.py` 是 outcome 复盘门禁，不是 prod-actionable 门禁。它必须在 collector 和 hosted API 共享同一 `DATA_DIR`/volume 的环境里运行；默认 `collection_errors_allowed=false`，且 `collect-outcomes` 返回 `collected=0` 时不会用旧样本冒充本次采集成功。`collect-outcomes` 在 `collected>0` 时必须输出 `collected_refs`，每条 ref 至少包含 `decision_ref`、`evaluation_target`、`symbol`、`window_name` 和 timezone-aware `collected_at`。脚本会在 collection 前后各跑一次 evidence 检查，要求后置 API 证据新增或更新的 matched ref 精确命中本次 `collected_refs` 中的 `(decision_ref, evaluation_target, symbol, window_name)`，并在成功输出里包含 `new_refs_verified=true`。
wrapper 会把同一 symbol 和本轮 gate start 自动传给底层 evidence gate：等价于要求 `tools/deployment/smoke_real_outcome_evidence.py --symbol ETH-USDT-SWAP --collected-after <gate_started_at>`。因此成功证据必须来自同一 symbol，且 matched outcome 的 `window.collected_at` 不能早于本次 collection gate；旧样本、并发的其他交易对样本，或同一交易对但不属于本次 `collected_refs` 的并发样本，都不能满足本次 real-outcome proof。
通过时，`--proof-output` 会写出 `hosted-real-outcome-proof.json`，包含 `schema_version=2026-07-09.hosted-real-outcome-proof.v1`、`collect_outcomes_digest`、`real_outcome_evidence_digest`、`outcome_summary`、`new_or_updated_refs`、`new_or_updated_ref_details` 和 `does_not_prove=hosted_prod_actionable`。这个文件只保存 collection/evidence 摘要和 digest，不保存 raw prompt、raw response、Bark device key 或 secret；它证明同一 symbol 且 exact `collected_refs` 绑定的 hosted real-outcome collection 闭环，不证明 prod-actionable、Bark sent 或 fresh LLM 决策链路。

如果只是要复现默认 Docker hosted-runtime proof，可用一条命令完成 compose build/up、hosted smoke、strict fixture rejection 和 cleanup：

```bash
python3 tools/deployment/smoke_docker_hosted_runtime.py
```

这个脚本默认使用 fixture 工作台并输出 `proof_level=hosted-runtime`，不是 `prod-config` 或 `prod-actionable`。生产意图容器环境仍需要 `.env.production.example` 填好后，再跑 `smoke_hosted_workbench.py --require-prod-config`、`smoke_hosted_prod_actionable.py`，以及 horizon 成熟后的 `smoke_hosted_real_outcome_collection.py`。

机器可读 proof ladder 用来统一 release 和迁移记录的证据口径：

```bash
python3 tools/deployment/proof_ladder.py
```

它输出 `schema_version=2026-07-09.main-flow-proof-ladder`，并列出 `local_no_secret_matrix`、`strict_local_prod_actionable_guard`、`docker_hosted_runtime`、`hosted_prod_config`、`hosted_prod_actionable`、`hosted_prod_actionable_visual`、`hosted_real_outcome` 的命令、证明范围和不能证明的内容。`tools/deployment/proof_ladder.py` does not run the gates；它只是防止把 fixture/mock/staging/hosted-runtime 或 negative visual guard 误写成生产成功。

- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`：仅在 `DECISION_ENGINE=openai_compatible` 时需要。
- `BARK_DEVICE_KEY`：仅在 `NOTIFICATION_ENABLED=true` 时需要。
- OKX 仅使用 public market data；v1 不接收 `OKX_API_KEY`、`OKX_API_SECRET`、`OKX_API_PASSPHRASE`、交易 key 或提现 key。

## 安全边界

- `AUTO_ORDER_ENABLED` 必须保持 `false`。
- `manual_execution_required` 必须保持 `true`。
- 不注册任何下单、撤单、提现工具。
- eval/replay 不允许发 Bark。
- 前端/API/日志不返回完整 secret。
- 默认不暴露 raw prompt、raw completion、LLM 原始请求/响应或 eval replay 工程明细；
  `include_payloads=true`、`mode=judge_openai`、eval run detail 和 promotion artifacts
  需要显式 `DIAGNOSTIC_ROUTES_ENABLED=true`，只能用于工程诊断环境。
- 默认 `POST /api/eval/runs` 和 `GET /api/eval/runs` 只返回产品安全 metadata
  （当前保留 `financial_quality_gate`），不返回 report refs、promotion artifacts、release gate 或 replay 细节。

## 测试

```powershell
python -m pytest
```

## 本地全链路自测

部署和 smoke profile 的完整说明见 `docs/deployment.md`。常用命令按证明强度分层：

```bash
# no-secret local matrix：pytest + typecheck/build + Playwright + fixture/mock/staging/outcome smoke。
python3 tools/local_stack/run_local_checks.py
```

`run_local_checks.py` 会顺序占用 `8010/3001/8011/8012/8013`，不要和其他本地栈并行运行。它证明本地/模拟/预发链路，不运行真实 `prod-actionable` release gate，也不能写成生产成功。

```bash
# fixture flow：本地 API/前端主流程和安全默认，预期 allowed=false。
python3 tools/local_stack/smoke_local_stack.py

# mock LLM flow：OpenAI-compatible client、telemetry、redaction、严格 JSON 解析；not production success。
python3 tools/local_stack/smoke_local_stack.py --with-mock-llm

# actionable staging flow：本地 OKX mock + no-active-event，证明人工复核 allowed 路径可达；not production success。
python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging

# prod-actionable readiness / real attempt：缺 readiness 会输出 ok=false + skip_reason，not production success。
python3 tools/local_stack/smoke_local_stack.py --prod-actionable

# release gate：缺 readiness 时非零退出，避免把 skip 当成功。
python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip
```

本地 `--prod-actionable` 即使跑到 `ok=true`，也必须输出 `proof_level=local-prod-actionable-rehearsal`、`production_success=false`、`hosted_proof_required=true`、`does_not_prove=hosted_prod_actionable`；它只是 localhost 严格演练，不能当成 hosted production proof。真实生产可执行提醒成功还必须通过 `smoke_hosted_prod_actionable.py --api-base <public-https-api>` 和同环境 hosted visual gate，并看到 `allowed=true`、真实 LLM interaction、`market_provider=okx_public`、`MACRO_EVENT_PROVIDER=no_active_event` 操作员断言及其元数据（`MACRO_EVENT_OPERATOR_REF`、`MACRO_EVENT_CONFIRMED_AT`、`MACRO_EVENT_SOURCE_REF`、`MACRO_EVENT_ASSERTION_HORIZON`、`MACRO_EVENT_VALID_UNTIL`）、Bark 通知已发送，并且始终保持 `manual_execution_required=true`、`auto_order_enabled=false`。当前尚未接入真实事件池 provider；`--prod-actionable` 的 structured skip 只是诚实报告缺少外部 readiness，不能当成生产成功。

公开仓库推送前至少检查：

```powershell
rg -n "sk-[A-Za-z0-9]{20,}|BARK_DEVICE_KEY=[A-Za-z0-9]{20,}|OKX_API_KEY=.+|OKX_API_SECRET=.+|OKX_API_PASSPHRASE=.+" . --glob "!data/**" --glob "!frontend/node_modules/**"
```

## 目录

```text
src/crypto_manual_alert/
  api/        FastAPI 路由和响应契约
  agent_swarm/  受控 worker、harness、shadow 编排运行时
  artifacts/    结构化证据、贡献和编排输入
  cli/        命令行入口和子命令装配
  config/     配置模型、加载和安全校验
  context/    DecisionRequest、DecisionRunContext 和 artifact store
  decision/   决策输入、解析、门禁和最终输入选择
  domain/     领域数据结构
  lead/       LeadAgent 规划与 synthesis
  market/     行情 provider
  notification/ Bark 等通知 sink
  research_pipeline/ 检索降级链路
  skills/     skill runtime 与决策引擎适配
  storage/    SQLite journal 和查询仓储
  telemetry/  trace、span、LLM telemetry
  workflow/   RunExecutor、legacy workflow shell 和步骤编排
tests/        按业务域归档的测试，根层不放散落 .py
tools/local_stack/ 本地启动和烟测脚本
frontend/     Next.js TypeScript 工作台
docs/formal/  正式设计文档
docs/migration/ 每轮开发迁移记录
```

`src/crypto_manual_alert/` 根包只保留包元信息；新增 Python 实现必须进入对应业务子包，不能直接平铺到根包。
