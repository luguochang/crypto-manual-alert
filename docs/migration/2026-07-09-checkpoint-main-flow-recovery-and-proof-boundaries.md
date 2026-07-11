# Checkpoint: main-flow recovery and proof boundaries

日期：2026-07-09
对应：`docs/formal/37` §7 P0/P1、`docs/implementation/2026-07-08-production-main-flow-recovery-plan.md`

## 背景

本 checkpoint 记录一次用户要求的真实多 Agent 复核和主流程恢复收束。

用户反馈的核心问题是：前端曾经过度暴露 JSON/trace/eval 视图，看不到真正的提醒内容、大模型返回摘要和可读交互；后端和文档也持续朝 AgentSwarm/eval/观测平台扩张，导致主业务链路看起来没有跑通。

本轮复核后确认：

- 当前默认代码主线已经回到 `manual-only crypto alert workbench`，即 `manual request -> RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> parser/gates -> journal/notification projection -> result_review/outcome projection`。
- `production_candidate_swarm`、candidate final、eval 和 diagnostic raw/matrix 仍是旁路/审计/评测路径，不是生产 final input。
- `query_text` 仍是 `audit_note`，不驱动 facts/final input；如果以后要让自由文本驱动策略，需要单独 P1 设计和测试。
- 本地/fixture/mock/staging 验证已经很强，但仍不能证明生产成功。

## 为什么之前 migration 计划看起来没有实现主流程

问题不是完全没有实现，而是证明等级混在一起了：

- 多个 checkpoint 完成的是 sidecar、eval、trace、candidate、fixture 或 mock wiring，不能直接转化为用户可见的 manual alert 产品证据。
- `docs/formal/35/36` 的部分 `[x]` 容易被误读成 Agent 能力或生产能力完成，实际只完成字段、开关、audit 面板或评测旁路。
- outcome 相关 checkpoint 已把 collector wiring 和 baseline 写入打通，但本地 mock OKX 仍只能输出 `real_financial_quality_proven=false`，不能代表真实金融质量。
- hosted workbench smoke 能证明已启动 API/frontend 的 runtime 入口，但默认 fixture config 也能通过；因此必须用 `--require-prod-config` 防止把 runtime smoke 误称为生产配置验收。
- 之前缺少一份按证据等级排序的当前 checklist，导致后续容易继续补旁路细节，而不是补真实外部 `prod-actionable`、Bark `sent` 和真实 matured outcome。

后续 migration 必须写明证明等级：`local`、`fixture`、`mock`、`staging`、`hosted-runtime`、`prod-config`、`prod-actionable`、`real-outcome`。不得把低等级 proof 描述成生产完成。

## 本轮改动

### 多 Agent 结论收束

- 架构 Agent：确认 `docs/formal/00` 与 `docs/formal/37` 仍是方向权威；主链路已经收回 manual-only；真实生产仍缺外部成功证据。
- UI/UX Agent：确认默认 `/`、`/manual-run`、`/runs`、`/runs/{trace_id}`、`/config`、默认 `/eval` 不再 JSON-first；下一步 UX 风险是移动详情深滚动、长耗时异步状态、以及部分降级文案继续产品化。
- QA Agent：确认当前矩阵是真实 local stack + production Next + Chromium + SQLite + DOM/视觉扫描，不是纯静态检查；但所有 no-secret 成功仍是 local/mock/staging，严格 production gate 正确阻断。

### 用户复核后的三 Agent 再审计

用户再次指出：不能只看文档或局部测试，必须真实启动前后端、执行 `/docs/migration` 计划里的 runtime smoke，并把前端“JSON 堆叠/没有大模型交互内容”的问题和后端复杂度一起重新梳理。

本轮再次启动三个只读 Agent 后结论一致：

- 架构 Agent：当前代码没有完全偏离 `manual-only crypto alert workbench`。生产主链仍是 `POST /api/runs/manual -> RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> legacy_prompt final decision -> parser/gates -> journal/notification projection`；但后端概念面偏重，`agent_swarm`、`decision`、`eval`、`storage`、candidate sidecar、outcome collector 等模块共同存在，维护认知链路过长。P0 仍是外部生产证据链，不是再扩 sidecar。
- UI/UX Agent：默认 `/manual-run -> /runs -> /runs/{trace_id}` 已经不是 JSON-first；模型返回摘要、证据摘要、通知状态和后续复盘都有展示容器。用户看不到“真实大模型内容”的核心原因不是 UI 容器缺失，而是当前 no-secret/local profile 没有真实外部 LLM/Bark/OKX 证据进入这些位置。剩余前端风险是移动详情深滚动和长耗时异步状态证据不足。
- QA Agent：Playwright 当前确实启动真实 local FastAPI、production Next 和 Chromium，并覆盖 DOM/视觉扫描、桌面/移动、错误脱敏、部分截图基线；但 Docker/hosted runtime 和 strict `prod-actionable` 是另一层证据，不能由 local E2E 替代。

### Docker/hosted-runtime 实测结果

本轮按 migration P0 首次尝试真实 Compose runtime：

```bash
API_PORT=18010 \
FRONTEND_PORT=13001 \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18010 \
PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim \
NODE_BASE_IMAGE=public.ecr.aws/docker/library/node:22-alpine \
docker compose -p crypto-alert-runtime-smoke up -d --build api frontend
```

结果：

- Docker Hub / mirror 元数据超时后，ECR base images 可用。
- API 镜像构建成功。
- frontend 镜像构建成功，并完成 `next build` 生产构建。
- Compose 创建了 `crypto-alert-runtime-smoke-api-1` 和 `crypto-alert-runtime-smoke-frontend-1`。
- 但容器停留在 `Created`，没有进入 running/healthy。
- `docker start crypto-alert-runtime-smoke-api-1`、`docker inspect`、`docker compose down --remove-orphans`、`docker rm -f` 均在 Docker socket/start/stop/rm 层卡住或被中断。
- 最小诊断 `docker run --rm public.ecr.aws/docker/library/alpine:3.20 sh -c 'echo docker-minimal-ok'` 也停在 `Created`。

当时结论：这次不是应用 healthcheck 失败，也不是前后端代码已经通过 hosted smoke；它是本机 Docker Desktop/container runtime 在 container start 层的阻塞。`hosted_workbench` smoke 未能执行。

#### Docker runtime 恢复后的 hosted-runtime 证明

随后 Docker Desktop/container runtime 恢复。本轮继续执行同一层真实 runtime 验证，先确认 Docker daemon 和最小容器可用：

```bash
docker version
docker context ls
docker run --rm public.ecr.aws/docker/library/alpine:3.20 sh -c 'echo docker-minimal-ok'
```

结果：

- Docker client/server 均可响应，当前 context 为 `desktop-linux`。
- 最小 Alpine 容器输出 `docker-minimal-ok`。
- 这证明前一段 `Created` 阻塞是本机 Docker runtime 状态问题，不是应用容器 healthcheck 失败。

随后重新执行真实 Compose runtime：

```bash
API_PORT=18010 \
FRONTEND_PORT=13001 \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18010 \
PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim \
NODE_BASE_IMAGE=public.ecr.aws/docker/library/node:22-alpine \
docker compose -p crypto-alert-runtime-smoke up -d --build api frontend
```

结果：

- API 镜像构建成功。
- frontend 镜像构建成功，并完成 Next production build。
- `crypto-alert-runtime-smoke-api-1` 启动并进入 `healthy`。
- `crypto-alert-runtime-smoke-frontend-1` 启动并进入 `healthy`。
- 端口映射为 `18010->8010` 和 `13001->3001`。

基础 HTTP 证明：

```bash
curl -fsS http://127.0.0.1:18010/api/system/health
curl -fsS http://127.0.0.1:13001
```

结果：

- API health 返回 `ok=true`，`service=crypto-manual-alert`，`storage=sqlite`，`mode=SHADOW`。
- frontend 返回生产 HTML，包含 `提醒控制台` 和 manual workbench UI。

标准 hosted workbench smoke：

```bash
python3 tools/deployment/smoke_hosted_workbench.py \
  --api-base http://127.0.0.1:18010 \
  --frontend-base http://127.0.0.1:13001 \
  --symbol ETH-USDT-SWAP \
  --query "Docker hosted runtime smoke：验证容器工作台人工提醒入口" \
  --horizon 6h
```

结果：退出码 `0`，关键字段为：

```json
{
  "ok": true,
  "smoke_profile": "hosted_workbench",
  "hosted_runtime_only_not_prod_actionable": true,
  "decision_engine": "fixture",
  "market_provider": "fixture",
  "candidate_sidecar_mode": "same_engine",
  "decision_final_input_mode": "legacy_prompt",
  "manual_execution_required": true,
  "auto_order_enabled": false,
  "production_config_required": false,
  "prod_actionable_ready": false
}
```

严格 hosted production-config negative smoke：

```bash
python3 tools/deployment/smoke_hosted_workbench.py \
  --api-base http://127.0.0.1:18010 \
  --frontend-base http://127.0.0.1:13001 \
  --symbol ETH-USDT-SWAP \
  --query "Docker hosted runtime strict config negative smoke" \
  --horizon 6h \
  --require-prod-config
```

结果：退出码 `1`，关键字段为：

```json
{
  "ok": false,
  "production_config_required": true,
  "error": "production config requires decision.engine=openai_compatible",
  "hosted_runtime_only_not_prod_actionable": true
}
```

该 negative smoke 证明默认 Compose fixture 工作台不能被误标成 `prod-config` 或 `prod-actionable`。

最后清理 runtime：

```bash
API_PORT=18010 FRONTEND_PORT=13001 docker compose -p crypto-alert-runtime-smoke down --remove-orphans
docker ps -a --filter name=crypto-alert-runtime-smoke --format '{{.Names}}\t{{.Status}}'
lsof -ti tcp:18010 -ti tcp:13001 || true
```

结果：API/frontend 容器和 compose network 已移除，`18010/13001` 无残留监听。

结论：P0 中“真实 Docker/hosted runtime 能否启动并跑通默认 manual workbench smoke”的问题已关闭，证明等级是 `hosted-runtime`。它仍只使用 fixture provider，不能写成 `prod-config`、`prod-actionable` 或 `real-outcome`。如果要声称 production-intent hosted runtime，需要使用填写后的 `.env.production.example`，并同时通过 `smoke_hosted_workbench.py --require-prod-config` 与 `tools/deployment/smoke_hosted_prod_actionable.py`；本地 strict `--prod-actionable --fail-on-skip` 只是 rehearsal，不替代 hosted 证据。

#### 本轮最新复测与未闭环项

用户再次要求不要停在文档或局部测试后，本轮重新执行并确认：

- `python3 tools/local_stack/run_local_checks.py`
  - 首次复测失败在 `tests/api/test_system_routes.py` 的 3 个 readiness 测试：测试数据硬编码 `MACRO_EVENT_VALID_UNTIL=2026-07-09T15:30:00+08:00`，现在已经过期。
  - 修复方式是让测试 fixture 动态生成当前 UTC 的 `MACRO_EVENT_CONFIRMED_AT` 和未来 `MACRO_EVENT_VALID_UNTIL`，不放松生产规则。
  - 聚焦验证：3 个失败测试修复后 `3 passed`。
  - 完整复跑：Python full pytest `1084 passed, 2 warnings`；frontend typecheck passed；frontend production build passed；Playwright `48 passed, 8 skipped`；fixture、mock LLM、actionable staging、seeded mock outcome、collect-outcomes fixture smokes passed。
  - 证明等级仍是 `local-browser + fixture/mock/staging`，不是生产成功。
- `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - 退出码 `2`，`skip_reason=missing_readiness`。
  - 缺少 `BARK_DEVICE_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`、`MACRO_EVENT_PROVIDER=no_active_event`。
  - `manual_execution_required=true`、`auto_order_enabled=false` 仍保持安全边界。
- `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - 退出码 `0`，`proof_level=hosted-runtime`，`stage=complete`。
  - 默认 runtime 仍是 fixture：`decision_engine=fixture`、`market_provider=fixture`、`candidate_sidecar_mode=same_engine`、`hosted_runtime_only_not_prod_actionable=true`。
  - strict `--require-prod-config` negative check 正确拒绝 fixture runtime：`production config requires decision.engine=openai_compatible`。
  - 清理后 `8010/3001/8011/8012/8013/18010/13001` 无残留监听，`crypto-alert-runtime-smoke` 容器无残留。

所以 `/docs/migration` 计划目前的真实状态是：本地主流程、Playwright、Docker hosted-runtime、脚本门禁已经落地；未闭环的是 production-intent hosted runtime、真实 `prod-actionable`、hosted prod-actionable visual proof、以及 horizon 成熟后的 real outcome。

### 可读 fallback 与前端脱敏

此前 `POST /api/runs/manual` 的即时响应已经能在缺少 `business_summary` / `result_review` 时展示可读 fallback，但 `/runs/{trace_id}` 详情页 schema 仍把 `result_review` 当必填。混合版本或局部投影缺失时，详情页会退化成“提醒详情暂时无法加载”。

本轮改动：

- `frontend/src/lib/schemas/manual-run.ts`
  - 导出 `manualRunPlanSchema`、`manualRunVerdictSchema`、`safeBusinessSummary()`、`safeResultReview()`。
- `frontend/src/lib/schemas/runs.ts`
  - `runDetailSchema` 复用同一套 fallback。
  - 当 `trace`、`plan_run.parsed_plan` 和 `plan_run.verdict` 存在但 `plan_run.business_summary` 或 `result_review` 缺失时，仍生成可读摘要：
    - `摘要暂不可用`
    - `核心提醒已返回`
    - `模型返回摘要`
    - `证据摘要`
    - `结果尚未生成`
    - `通知状态未记录`
  - `/api/runs` 列表和 `/api/runs/{trace_id}` 详情对 optional projection 采用“能解析则净化，不能解析则置空或生成 fallback”的策略，坏投影不再拖垮整页。
  - `agent_audit_view`、`production_control_gate`、`facts_gate`、candidate comparison 等用户可见 reason 路径统一走安全 reason projection。
- `frontend/src/app/runs/[traceId]/cockpit-status-bar.tsx`
  - 阻断原因展示使用 `safeReasonBullets()`，不直接渲染 backend/raw reason。
- `frontend/src/app/runs/[traceId]/decision-summary-card.tsx`
  - 默认摘要里的阻断原因也使用同一套安全 reason projection。
- `tools/local_stack/mock_error_api_server.py`
  - 增加 `partial_run_detail_envelope()`，让 8013 internal fault API 可以模拟“核心详情存在但显示投影缺失”的 Server Component 场景。
- `frontend/tests/e2e/error-states.spec.ts`
  - 增加 `run detail partial projection keeps readable fallback`。
  - manual-run partial success 注入包含 SQLite、路径、Bark key、Bearer、api_key 等 unsafe token 的 reason，验证页面仍展示可读提醒和详情链接，并且不泄漏内部文本。
- `frontend/tests/e2e/product-copy.spec.ts`
  - 增加合法 `business_summary` 可见文本净化覆盖，防止完整投影里的 title/reason/risk/evidence/notification/result_review 文案直接泄漏内部路径、密钥、trace、原始 payload 或错误栈。
  - 增加 run list 坏 optional projection 容错覆盖，保证单条坏摘要不会隐藏整条 run。
  - 增加 agent audit product-visible reason 净化覆盖。
- `tests/local_stack/test_scripts.py`
  - 增加 `test_mock_error_api_server_returns_partial_run_detail_projection_fixture`，固定 fault fixture 的语义。

该 fallback 是用户体验降级路径，不代表后端可以停止生成当前 production contract。API/CLI 测试仍应在当前契约缺失 `business_summary` 或 `result_review` 时 fail loud。

### 生产门禁补强

本轮还补了两个容易把 staging/hosted-runtime 误读成 production 的门禁：

- `tools/deployment/smoke_hosted_workbench.py`
  - `--require-prod-config` 现在不仅要求 `decision.engine=openai_compatible`、`candidate_sidecar_mode=disabled`、`market_data.provider=okx_public`、`notification.enabled=true`、`macro_event.provider=no_active_event`、`workflow.execution_mode=legacy_baseline` 和 `readiness.prod_actionable.status=ready`，还要求 `decision.final_input_mode=legacy_prompt`。
  - 这样 hosted workbench strict smoke 只能证明“生产配置边界符合当前 MVP 主线”，不能把 candidate final / decision_input 旁路误当作 production final input。
- `src/crypto_manual_alert/config/loader.py`
  - `MACRO_EVENT_VALID_UNTIL` 支持 YAML 解析后的 datetime 或字符串输入。
  - 时间必须带 timezone，必须晚于 `MACRO_EVENT_CONFIRMED_AT`；当 `MACRO_EVENT_PROVIDER=no_active_event` 时，还必须晚于当前 UTC 时间。
- `tools/local_stack/smoke_local_stack.py`
  - `--prod-actionable` 对 `MACRO_EVENT_VALID_UNTIL` 做未来时间校验；过期的 no-active-event 人工断言会被判为 `unsafe_readiness`，不能继续冒充生产可行动。

这两个门禁都只提高 proof boundary，不改变产品边界：当前 final input 仍是 `legacy_prompt`，`production_candidate_swarm` 仍是 audit/sidecar，`no_active_event` 仍必须带完整人工断言元数据。

## 2026-07-11 增量 checkpoint：真实行情、模型返回与 fail-closed 收口

本轮补齐了此前 migration 计划里最关键但没有真实证明的主链部分：

- OKX 指数价不再错误依赖 `mark-price.idxPx`，而是独立调用 `/api/v5/market/index-tickers?instId=ETH-USDT`。
- 真实 OKX 通过显式本机代理返回了非空 mark、index、双边 20 档订单簿及其他公开行情，`unavailable=[]`。
- 真实 `gpt-5.5` 与真实 OKX 在同一手动运行中成功，trace 为 `af40d5dbe1b04044af35533738751498`。
- 模型安全摘录同时持久化到 `business_summary.generation_summary.raw_completion_excerpt` 与 `llm_interactions[].completion_excerpt`，普通产品页不暴露 raw request/response。
- 空值、非有限价格、空/畸形订单簿、空事件状态均改为 fail-closed；仅有 source/status 不再足以解除执行或事件门禁。
- 前端不再把 `index/mark/order_book` 过滤成通用占位，也不会在执行事实未就绪时宣称“生产可复核证据已记录”。

真实联合运行仍为 `allowed=false`，原因是 `active_event_status` 未配置且通知未启用。这是门禁正确工作，不是主链失败。

本 checkpoint 仍不关闭以下生产项：

- 公网 HTTPS hosted API/frontend；
- hosted 环境中的完整且未过期 `no_active_event` 人工断言或真实事件池；
- 同次运行 Bark 发送成功证据；
- 新闻、宏观和情绪研究所需的 web/Responses search；
- 观察窗口成熟后的真实 outcome collection 与质量门禁。

边界保持不变：web search 可以补充研究和事件上下文，但不能替代 OKX mark、index 或 order book；系统继续 `manual_execution_required=true`、`auto_order_enabled=false`。

### 生产 overlay 显式主链声明

用户再次要求先把主流程跑通并停止被旁路复杂度带偏后，本轮补齐了一个配置层歧义：`config/default.yaml` 虽然已经声明 manual-only 和 `legacy_prompt` 主链，但 `config/prod.yaml` 之前只覆盖 `openai_compatible`、`okx_public`、通知、调度和 research，生产 overlay 自身没有显式写出当前 MVP 的不可变边界。

本轮改动：

- `config/prod.yaml`
  - 显式声明 `trading.auto_order_enabled=false`。
  - 显式声明 `trading.manual_execution_required=true`。
  - 显式声明 `decision.final_input_mode=legacy_prompt`。
  - 继续声明 `decision.candidate_sidecar_mode=disabled`。
  - 显式声明 `workflow.execution_mode=legacy_baseline`。
- `tests/config/test_config.py`
  - 新增 `test_prod_config_declares_manual_only_legacy_main_path_explicitly`。
  - 测试直接读取 `config/prod.yaml`，防止这些字段只靠 default merge 间接存在。

红灯：

```bash
python3 -m pytest tests/config/test_config.py::test_prod_config_declares_manual_only_legacy_main_path_explicitly -q
```

失败表现：`KeyError: 'trading'`，证明 `prod.yaml` 自身缺少 manual-only 安全段。

绿灯：

```bash
python3 -m pytest tests/config/test_config.py::test_prod_config_declares_manual_only_legacy_main_path_explicitly -q
```

结果：`1 passed`。

相关配置/部署边界验证：

```bash
python3 -m pytest tests/config/test_config.py tests/deployment/test_hosted_workbench_smoke.py tests/deployment/test_container_config_commands.py -q
```

结果：`61 passed`。

证明等级：`prod-config`。这只证明生产配置意图和部署命令边界已显式对齐当前 manual-only legacy 主链；它仍不是 `prod-actionable`，也不是 `real-outcome`。

### 多 Agent 再审计后的模型审阅产品投影

本轮再次启动三个只读 Agent 后，结论收束如下：

- 架构 Agent：主链没有被 AgentSwarm、candidate final、DecisionInput、eval 或 raw diagnostic 接管。当前 production canonical path 仍是 manual-only alert workbench：`POST /api/runs/manual -> build_manual_decision_request -> RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> legacy_prompt final -> parser/gates/risk -> journal -> business_summary/result_review/notification projection`。默认 Docker hosted-runtime 已在后续重试中闭环；剩余 P0 是 `prod-actionable`、真实 matured outcome、以及使用真实 readiness 的 production-intent hosted runtime。
- QA Agent：Playwright 默认 E2E 确实启动真实 local FastAPI、production Next、Chromium desktop/mobile 和 SQLite，并做 DOM/视觉/runtime 扫描；但默认绿色矩阵仍是 no-secret 的 fixture/mock/staging。Docker hosted runtime 需要真实 `docker compose up -d --build api frontend` 后再跑 hosted smoke，静态 Compose/Dockerfile 测试不能算 runtime 成功。
- UI/UX Agent：默认 `/manual-run -> /runs -> /runs/{trace_id}` 已不是 JSON-first，但用户说“看不到真实内容/大模型交互内容”仍有依据：普通产品页只展示模型链路摘要，真正的 LLM request/response 正文仍在工程诊断/Raw 下钻；默认 fixture 路径也会明确显示“未产生真实模型返回”。

本轮先做最小产品修复，不改变后端决策、不把 Raw 搬到默认页：

- `frontend/src/app/shared/summary-projections.tsx`
  - 新增 `ModelReviewPanel`，默认产品页展示：
    - `用户关注点`：说明关注点已写入复核备注，模型输出只作为人工复核材料。
    - `模型结论摘录`：复用安全的 `generation_summary.response_summary`。
    - `引用与证据`：复用安全的 evidence bullets 或 generation detail bullets。
  - 明确默认产品页不展示原始请求、原始返回或密钥字段。
- `frontend/src/app/manual-run/run-form.tsx`
  - 手动生成成功面板新增 `aria-label="模型审阅"`。
- `frontend/src/app/runs/[traceId]/decision-summary-card.tsx`
  - 默认提醒详情摘要新增同一块 `模型审阅`。
- `frontend/tests/e2e/full-stack-visual.spec.ts`
  - `manual run async flow` 新增断言：manual-run 成功页和 run detail 默认摘要页都必须展示 `模型审阅`，包含 `用户关注点`、`模型结论摘录`、`引用与证据`，且不可见 `request_json`、`response_json`、`choices`、`chat.completion`、`Bearer`、`api_key`。

红灯：

```bash
PLAYWRIGHT_EXPECT_MOCK_LLM=true \
PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm" \
npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"
```

失败表现：manual-run success panel 找不到 `aria-label="模型审阅"`。

绿灯：

```bash
PLAYWRIGHT_EXPECT_MOCK_LLM=true \
PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm" \
npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"
```

结果：`1 passed`。

默认 fixture 分支和类型检查：

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"
```

结果：typecheck passed，Playwright `1 passed`。

证明等级：`mock/local-browser` 和 `fixture/local-browser`。这只证明默认产品页能展示可读的模型审阅投影，并继续隐藏 raw JSON；它不是外部真实 LLM 成功，也不是 `prod-actionable`。

### Production-intent hosted workbench env template

QA Agent 指出：`docker-compose.yml` 的 `api` 服务默认仍是 `CONFIG_PATHS=${CONFIG_PATHS:-config/default.yaml}`。这是安全默认，可以用于新 checkout 先启动 fixture 工作台，但如果操作员忘记在 `.env` 中设置 production overlay，就会把 hosted runtime smoke 误读成 production-config smoke。

本轮不改变安全默认，而是补齐可审计的生产启动模板：

- `.env.production.example`
  - 明确 `CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml`。
  - 明确 `APP_MODE=MANUAL_ALERT`、`AUTO_ORDER_ENABLED=false`。
  - 明确 `DIAGNOSTIC_ROUTES_ENABLED=false`、`SCHEDULER_ENABLED=false`。
  - 明确 `MARKET_DATA_PROVIDER=okx_public`、`DECISION_ENGINE=openai_compatible`、`NOTIFICATION_ENABLED=true`、`MACRO_EVENT_PROVIDER=no_active_event`。
  - 保留 `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`、`BARK_DEVICE_KEY` 和 no-active-event 操作员断言元数据占位。
  - 不包含 OKX trade/withdraw key 字段。
- `.gitignore`
  - 继续忽略真实 `.env` / `.env.*`，但允许提交 `.env.production.example`。
- `README.md`
  - 增加 `cp .env.production.example .env`。
  - 增加 hosted workbench `--require-prod-config` smoke 和 strict `--prod-actionable --fail-on-skip` 的连续验收路径。
- `docs/deployment.md`
  - 把安全默认 `.env.example` 和 production-intent `.env.production.example` 分开说明。
  - 明确 production-intent 工作台必须先复制模板并填写真实 readiness，再 `docker compose ... up -d --build api frontend`。

红灯：

```bash
python3 -m pytest \
  tests/deployment/test_container_config_commands.py::test_prod_env_template_declares_hosted_workbench_production_intent \
  tests/deployment/test_container_config_commands.py::test_deployment_docs_reference_prod_env_template_and_strict_smokes \
  -q
```

失败表现：`.env.production.example` 不存在，README/deployment docs 没有引用该模板。

绿灯：

```bash
python3 -m pytest \
  tests/deployment/test_container_config_commands.py::test_prod_env_template_declares_hosted_workbench_production_intent \
  tests/deployment/test_container_config_commands.py::test_deployment_docs_reference_prod_env_template_and_strict_smokes \
  -q
```

结果：`2 passed`。

相关部署测试：

```bash
python3 -m pytest tests/deployment -q
```

结果：`29 passed`。

证明等级：`prod-config` runbook/template。它解决的是“生产意图配置如何进入 hosted workbench”的可审计性；它仍不是 Docker runtime smoke，也不是 `prod-actionable` 成功。

### Agent 复核后的 P1 闭环修复

本轮最终多 Agent 复核没有发现主链路被 AgentSwarm/candidate/eval 静默接管的 P0 问题，但发现两个会造成“正常页面泄漏内部文本”或“staging allowed 被误读成生产成功”的 P1 风险。

#### Eval 正常行内容脱敏

UI/UX Agent 发现 eval 诊断表格只脱敏加载失败错误文案，但正常 row data 仍可能直接渲染：

- candidate `expected_behavior` / `actual_behavior`
- candidate `category` / `eval_dataset_name`
- candidate `severity` / `status`
- judge `judge_name` / `judge_type` / `severity` / `failure_category`
- judge `reason_summary`
- judge `evidence_refs`
- replay result `final_action`
- observed trace `final_action` / `allowed`

修复：

- `frontend/src/app/shared/safe-error.ts`
  - 统一导出 `UNSAFE_DISPLAY_PATTERN`、`hasUnsafeDisplayText()`、`safeDisplayContent()`。
  - 危险文本规则新增 `/Users/...`、`/var/...`、Windows 路径、`Authorization: Basic/Bearer`。
- `frontend/src/lib/schemas/manual-run.ts`
  - 改为复用共享危险文本判断，避免 schema 和表格两套脱敏规则漂移。
- `frontend/src/app/eval/eval-format.ts`
  - 新增 `safeEvalText()` / `safeEvalLabel()`，`evidenceText()` / `observedText()` 使用安全投影和产品文案。
  - 常见 eval category、dataset、severity/status、judge name、judge type、judge severity、failure category 映射为中文产品标签；未知值走安全 fallback。
- `frontend/src/app/eval/eval-candidates-table.tsx`
  - candidate 期望/实际行为使用安全投影。
  - candidate category/dataset/severity/status 使用安全标签投影。
- `frontend/src/app/eval/eval-judge-scores-table.tsx`
  - judge reason/evidence 使用安全投影。
  - judge name/type/severity/failure category 使用安全标签投影，避免 LLM judge 返回的 `severity` / `failure_category` 直接出现在普通表格。
- `frontend/src/app/eval/eval-replay-table.tsx`
  - replay result action/allowed 使用安全投影和中文产品文案。
- `frontend/src/app/shared/safe-error.ts`
  - `token` unsafe 匹配收窄为 secret-shaped contexts（例如 `token=...`），不再把正常遥测文案 `321 tokens` 隐藏成异常。
- `frontend/tests/e2e/product-copy.spec.ts`
  - 新增 `eval diagnostic table row text hides backend internals`，覆盖 SQLite、`/Users/...`、`/var/...`、Windows 路径、`Authorization`、Bearer、Bark key、API key 等。
  - 覆盖 unsafe category、dataset、failure category 以及 `321 tokens` / `token=hidden` 的区分。

红灯：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text"
```

失败表现：row-text projection helper 不存在，表格仍直出原始 row 值。

绿灯：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text"
```

结果：`1 passed`。

最终审查补充红灯：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text|shared error copy"
```

失败表现：`evalCandidateCategoryText()` / `evalCandidateDatasetText()` / `evalJudgeFailureCategoryText()` 不存在，且 `safeDisplayError("321 tokens")` 被误判为 unsafe。

最终审查补充绿灯：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text|shared error copy"
```

结果：`2 passed`。

最终审查二次补充红灯：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text"
```

失败表现：新增 unsafe severity/status 覆盖后，`evalCandidateSeverityText()` 不存在，且 judge `severity` 仍可能裸渲染真实 LLM judge 返回值。

最终审查二次补充绿灯：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text"
```

结果：`1 passed`。`npm --prefix frontend run typecheck` 同步通过。

#### Staging allowed 的生产证明边界

架构 Agent 发现 `default+staging` 可以在缺少完整 no-active-event 断言元数据时得到 `allowed=true`。这是本地/预发 wiring proof 可以接受，但主摘要文案只写“人工复核门槛已满足”，容易被误读为生产成功。

最终 code-review 又发现：即使 no-active-event 元数据完整，旧 `_run_mode()` 仍可能只凭 config/gate 形状把 allowed run 归为 `actionable_manual_review`，没有要求持久化真实 LLM 成功、真实 OKX 证据、Bark `sent` 和严格 readiness。这会把“配置看起来像生产”误读成“生产证据已完成”。

修复：

- `src/crypto_manual_alert/storage/business_summary.py`
  - 当 `mode=actionable_manual_review` 且 `MACRO_EVENT_PROVIDER=no_active_event` 元数据不完整时，`mode_notice` 主文案显式包含 `本地/预发证明` 和 `不是生产成功`。
  - 新增 `actionable_local_proof` 投影模式：manual review gate 可以 allowed，但只要缺持久化真实 LLM `status=ok`、真实 OKX public 行情、完整且未过期 `no_active_event`、Bark `sent`、或 strict config readiness，就显示 `本地/预发证明（人工复核门槛）` 和 `不是生产成功`，并列出缺口。
  - 只有完整生产证据存在时，才允许 `actionable_manual_review` 主文案写“当前已满足人工复核门槛”。
- `src/crypto_manual_alert/storage/query_repository.py`
  - `JournalQueryRepository` 接受只读 `config`，用于 UI/API 投影。
- `src/crypto_manual_alert/storage/journal.py`
  - `list_traces()` / `get_trace_detail()` 接受可选 `projection_config`。
- `src/crypto_manual_alert/storage/journal_rows.py`
  - `plan_run_row()` 把 `config` 传入 `build_business_summary()`。
- `src/crypto_manual_alert/api/app.py`
  - API repository 使用当前 app config，所以 `POST /api/runs/manual` 即时响应、`GET /api/runs` 和 `GET /api/runs/{trace_id}` 的 persisted projection 一致。
- `src/crypto_manual_alert/cli/main.py`
  - `trace-show` / `run-once` 持久化详情回读也使用当前 config-aware projection。
- `tests/storage/test_business_summary.py`
  - builder 层锁定 staging/local proof-boundary 文案。
  - 新增 prod+staging complete config 但无 persisted `llm_summary`、LLM `status=error`、Bark `ok=false` 的回归测试，防止配置形状被误说成生产成功。
- `tests/api/test_runs_routes.py`
  - 真实 `POST /api/runs/manual` 和详情回读都必须包含 `本地/预发证明` / `不是生产成功`。

红灯：

```bash
python3 -m pytest tests/storage/test_business_summary.py::test_business_summary_labels_staging_actionable_result_as_manual_review -q
```

失败表现：builder 摘要只写“人工复核门槛已满足”，没有非生产边界。

第二个红灯：

```bash
python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_staging_actionable_path_allows_manual_review_without_auto_order -q
```

失败表现：builder 修复后，真实 API persisted projection 仍没有边界文案，证明 journal/repository 投影没有拿到当前 config。

绿灯：

```bash
python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_staging_actionable_path_allows_manual_review_without_auto_order -q
```

结果：`1 passed`。

最终审查补充红灯：

```bash
python3 -m pytest tests/storage/test_business_summary.py -q
```

失败表现：新增的 prod+staging/no-LLM、failed-LLM、failed-Bark cases 仍被过度归类为满足人工复核门槛。

最终审查补充绿灯：

```bash
python3 -m pytest tests/storage/test_business_summary.py -q
```

结果：`12 passed`。

该修复不改变 staging allowed 的本地证明价值；它只让 proof level 在产品主文案、API 和 CLI 输出里更诚实。

## 验收

红灯：

```bash
PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true \
PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" \
npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "run detail partial projection"
```

失败表现：详情页只显示 `提醒详情暂时无法加载`，没有 `提醒建议摘要`。

绿灯：

```bash
PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true \
PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" \
npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "run detail partial projection"
```

结果：`1 passed`。

聚焦 Server Component error-state 验收：

```bash
PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true \
PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" \
npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"
```

结果：`2 passed`。

结构测试：

```bash
python3 -m pytest \
  tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_unsafe_envelope_for_redaction_tests \
  tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_partial_run_detail_projection_fixture \
  -q
```

结果：`2 passed`。

长耗时异步与移动详情深滚动：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop async-and-mobile-depth.spec.ts -g "delayed responses"
```

红灯：首次运行失败在 `/manual-run` 长耗时提交只禁用了按钮并显示 `提交中`，但没有可见 `role=status` 进度区域。

修复后首次结果：`1 passed`。该用例现在覆盖：

- `/manual-run` 延迟响应期间显示 `提醒生成进度`。
- `/eval?tab=runs` 延迟响应期间显示 `复盘运行进度`。
- 两个提交按钮在 pending 期间 disabled，避免重复提交。
- pending 期间运行即时 DOM/视觉扫描，不等待 `networkidle`。

```bash
npm --prefix frontend run e2e -- --project=chromium-mobile async-and-mobile-depth.spec.ts -g "mobile run detail deep-scroll"
```

结果：`1 passed`。该用例通过真实 local `POST /api/runs/manual` 生成 trace，再在移动项目打开 `/runs/{trace_id}`，对 top/middle/bottom 滚动点和 `提醒建议摘要`、`模型返回摘要`、`证据摘要`、`复核状态摘要`、`后续复盘`、`通知历史` 做 DOM/视觉扫描。

默认前端 E2E 全套：

```bash
npm --prefix frontend run e2e
```

红灯：首次全套运行在 mobile delayed eval pending-state DOM scan 中发现 eval run 表格链接点击目标只有 `113x16`，低于移动端可用点击面积。

修复：`.table-wrap a` 增加 `min-height: 32px`，扩大表格内链接命中区。

结果：`44 passed, 4 skipped`。4 个 skipped 是默认 profile 下按设计跳过的 opt-in Server Component fault tests。

前端投影脱敏与容错：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts
```

结果：`11 passed`。

默认 error-state：

```bash
npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts
```

结果：`6 passed, 2 skipped`。2 个 skipped 是默认 profile 下按设计跳过的 opt-in Server Component fault tests。

生产配置与事件有效期门禁聚焦测试：

```bash
python3 -m pytest \
  tests/config/test_config.py \
  tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_partial_run_detail_projection_fixture \
  tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready \
  tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_expired_event_assertion \
  tests/deployment/test_hosted_workbench_smoke.py \
  -q
```

结果：`46 passed, 1 warning`。

类型检查：

```bash
npm --prefix frontend run typecheck
```

结果：通过。

最新 no-secret 全量矩阵：

```bash
python3 tools/local_stack/run_local_checks.py
```

结果：退出码 `0`，执行了：

- Python full pytest：`1054 passed, 2 warnings`
- frontend typecheck
- frontend production build
- Playwright：`46 passed, 4 skipped`
- fixture smoke
- mock LLM smoke
- actionable staging smoke
- seeded mock-outcome smoke
- collect-outcomes fixture smoke

补充 opt-in Server Component fault 验证：

```bash
PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true \
PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" \
npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"
```

结果：`2 passed`。

严格生产门禁：

```bash
python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip
```

结果：退出码 `2`，`skip_reason=missing_readiness`，缺少：

- `BARK_DEVICE_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_API_KEY`
- `MACRO_EVENT_PROVIDER=no_active_event`

这是正确阻断，不是生产成功。即使 local actionable staging 能得到 `allowed=true`，它仍使用本地 mock OKX / no-secret wiring，只能证明允许路径渲染和本地链路，不证明生产。

## 剩余 P0

- 真实外部 `prod-actionable` 成功：真实 public HTTPS OpenAI-compatible endpoint/model/key、真实 OKX public market data、Bark `sent`、完整 `no_active_event` 人工断言元数据且 `MACRO_EVENT_VALID_UNTIL` 未过期、`allowed=true`、`decision.final_input_mode=legacy_prompt`、`candidate_sidecar_mode=disabled`、`workflow.execution_mode=legacy_baseline`、`manual_execution_required=true`、`auto_order_enabled=false`。
- 至少一条真实 exchange-native matured outcome 进入 OutcomeStore，并通过 `tools/deployment/smoke_real_outcome_evidence.py`。
- Production-intent hosted runtime：使用填写后的 `.env.production.example` profile 启动容器，并通过 `tools/deployment/smoke_hosted_workbench.py --require-prod-config` 与 `tools/deployment/smoke_hosted_prod_actionable.py`。默认 fixture hosted-runtime smoke 已完成，本地 strict `--prod-actionable --fail-on-skip` 也不能替代 hosted run-level gate。

## 剩余 P1

- outcome collector 持续运维闭环：当前已有 CLI 和 local wiring proof，还没有生产定时/运维 runbook 成熟样本积累。
- query intent：继续诚实标注为 `audit_note`，或另起设计让它驱动 facts/final input。

## production main path 索引

为了避免后续继续在 AgentSwarm、candidate、eval 或 raw trace 旁路里迷路，当前可交付主线固定为以下 production main path。这里的 production 指“当前 MVP 生产提醒主链”，不等于已经证明真实外部 production success：

1. `src/crypto_manual_alert/api/routes_runs.py`
   - `POST /api/runs/manual` 是 Web 工作台手动提醒入口。
   - 它同步调用 executor，随后从 persisted detail 回读 `business_summary` 与 `result_review`，避免即时响应和详情页投影不一致。

2. `src/crypto_manual_alert/context/request.py`
   - `build_manual_decision_request()` 把用户输入规范化成 `DecisionRequest`。
   - `query_text` 当前仍是 operator audit note，不驱动 facts、worker selection 或 production final input。

3. `src/crypto_manual_alert/workflow/executor.py`
   - `RunExecutor.submit()` 创建 `DecisionRunContext`，按 `workflow.execution_mode` 选择决策步骤。
   - 当前默认生产主线必须保持 `legacy_baseline`；`controlled_shadow` / `production_candidate_swarm` 不得被解释成已接管生产 final decision。

4. `src/crypto_manual_alert/workflow/legacy_adapter.py`
   - `LegacyPlanRunnerAdapter` 是兼容壳，把 `DecisionRunContext` 交给 legacy PlanRunner。
   - 它的存在是为了隔离迁移边界，不是长期鼓励继续扩展旧 PlanRunner。

5. `src/crypto_manual_alert/workflow/legacy_decision_workflow.py`
   - 当前真实步骤序列：`market.fetch -> skill.load -> research_orchestration -> prompt.build -> input.freeze -> decision_input.pre_final -> decision.final -> parser.strict_json -> production_control.check -> risk.check`。
   - `decision_input.pre_final`、shadow swarm、candidate audit 都是 sidecar/audit/eval 证据，不写入 production final input。

6. `src/crypto_manual_alert/decision/final_engine.py`
   - 承载 fixture / OpenAI-compatible final LLM 调用。
   - 真实模型证据必须来自 public HTTPS OpenAI-compatible endpoint/model/key，并在 LLM summary 中体现成功；mock/local endpoint 只能证明 wiring。

7. `src/crypto_manual_alert/decision/plan_parser.py`
   - 负责 strict JSON plan 解析，把模型输出约束为结构化计划。

8. `src/crypto_manual_alert/decision/production_control_gate.py`
   - 负责 manual-only、安全边界、facts gate 和 production control blocking。
   - `manual_execution_required=true` 与 `auto_order_enabled=false` 必须继续作为主链不可变约束。

9. `src/crypto_manual_alert/storage/business_summary.py`
   - 当前产品页的核心业务投影。
   - 它只投影已持久化事实，不调用外部 provider，不改变风控结论；`actionable_local_proof` 与 `actionable_manual_review` 的 proof boundary 必须在这里保持诚实。

10. `src/crypto_manual_alert/storage/query_repository.py`
    - API/frontend 详情页读取的 canonical projection。
    - 前端应优先消费 `business_summary`、`result_review`、notification projection，而不是让用户阅读 raw JSON。

明确不属于 production final input 的路径：

- `src/crypto_manual_alert/workflow/candidate_sidecar_step.py`
- `src/crypto_manual_alert/orchestration/*`
- `src/crypto_manual_alert/agent_swarm/*`
- `src/crypto_manual_alert/eval/*`
- `frontend/src/app/runs/[traceId]/raw-tab.tsx`

这些模块是 sidecar/audit/eval/diagnostic surface。它们可以帮助审计、复盘、对比和调试，但不能被写成“生产 AgentSwarm 已接管”。

## outcome collector 运维闭环

当前 outcome 管道已经有真实代码路径，但仍缺生产样本积累。要把金融质量从“有代码”推进到“有证据”，运维流程必须按下面执行：

1. 先生成真实或准生产提醒。
   - Web: `POST /api/runs/manual`
   - CLI: `crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml run-once --symbol ETH-USDT-SWAP --query "..." --horizon 6h`
   - 该提醒仍必须是 manual-only，不能自动下单。

2. 等待 matured horizon。
   - `src/crypto_manual_alert/eval/outcome_collector.py` 会从 trace 的 horizon 解析窗口。
   - 未成熟窗口不会提前评分；例如 `6h` 的提醒必须等生成时间加 6 小时以后再采集。

3. 运行 collector。
   - `crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml collect-outcomes --limit 50`
   - 可用 `--symbol ETH-USDT-SWAP` 收窄范围。
   - collector 只读 journal，拉取 OKX public history candles，写 eval sidecar `OutcomeStore`；不写生产 `plan_runs`，不发 Bark，不触发 replay/eval runner live fetch。

4. 检查结果。
   - API: `GET /api/eval/outcomes`
   - UI: `/eval?tab=quality`
   - 部署 smoke: `python3 tools/deployment/smoke_real_outcome_evidence.py --api-base <hosted-api> --min-count 1`
   - Hosted collection gate: `python3 tools/deployment/smoke_hosted_real_outcome_collection.py --api-base <hosted-api> --same-host-data-dir-confirmed --min-count 1`

5. 证明边界。
   - 只有 `source_type=exchange_native`、`matured=true`、`can_score=true`、入场/止损/目标和窗口 OHLC 齐备的样本，才能算真实可评分 outcome。
   - `mocked_outcome` 只用于本地可视化，不代表金融质量。
   - `tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture` 使用本地 mock OKX，只证明 collector wiring；它不是 production success，也不是真实金融质量证明。
   - `real_outcome_evidence` 只证明 OutcomeStore 已有真实 exchange-native matured outcome；它仍不是 `prod-actionable` 提醒成功。
   - `hosted_real_outcome_collection` 在操作员确认的同一 hosted `DATA_DIR`/volume 上触发 `collect-outcomes`，并在 collection 前后都跑 evidence gate；默认 `collection_errors_allowed=false`，`collected=0` 不能被旧样本伪装成本次 collection success，后置 API 必须给出 `new_refs_verified=true`。

6. 失败处理。
   - OKX 网络失败、空 candles、未成熟窗口、缺交易价位或 source 非 exchange-native，都应保持 skipped/pending/unscored，不得伪造成 scored outcome。
   - 如果 `collect-outcomes` 输出 errors，先确认 OKX public endpoint、`MARKET_DATA_PROVIDER=okx_public`、symbol、bar 和 horizon 窗口，再重跑；不要把 `mocked_outcome` 混入真实质量统计。

## 已补 P1 浏览器证据

- 移动端 run detail 深滚动：已通过 `frontend/tests/e2e/async-and-mobile-depth.spec.ts` 覆盖顶部摘要、中段后续复盘、底部通知历史/复核状态，以及 top/middle/bottom DOM/视觉扫描。
- 长耗时异步状态：已通过同一 spec 覆盖 manual-run 和 eval run 的可见进度、disabled duplicate-submit controls、pending 期间即时 DOM/视觉扫描和成功态恢复。
- 生成后跨页面定位：`/manual-run` 成功态现在提供 `查看记录`，跳转到 `/runs?latest={trace_id}`；提醒记录页显示 `刚生成的提醒` 提示，并用稳定 `data-latest-run="true"` 高亮对应业务行。该能力由 `frontend/tests/e2e/async-and-mobile-depth.spec.ts::manual run can jump back to highlighted alert history entry` 固定，证明用户能从创建结果回到列表继续跟踪，不需要读 raw trace 或手动查找历史行。
- 默认 `/eval?tab=quality` 不再加载 `GET /api/eval/runs/{eval_run_id}` 工程复盘详情。质量页只展示 quality/outcome 相关信息；回放明细和 judge 分数继续保留在显式 `/eval?tab=runs` 诊断路径。该边界由 `tests/structure/test_frontend_route_boundaries.py::test_eval_quality_route_does_not_load_diagnostic_run_detail` 固定。

Proof-level token：以上 local/mock/staging/fixture/hosted-runtime/collector wiring 证据均为 `not production success`，只能证明对应层级的链路闭环。

## 2026-07-09 追加：proof gate hardening and latest local matrix

本追加段是当前 checkpoint 的最新证据摘要，优先级高于上方较早的 `1054 passed` / `46 passed` 历史记录；旧记录保留迁移过程，但不代表当前最新状态。

- hosted prod-actionable API gate：
  - `tools/deployment/smoke_hosted_prod_actionable.py` 现在默认要求 public HTTPS API base，拒绝 localhost、私网、非 HTTPS、保留地址，以及 DNS 解析到 local/private/reserved 地址的 public-looking hostname。
  - run-level proof 仍要求 `allowed=true`、真实 OpenAI-compatible `decision.final status=ok`、OKX exchange-native fresh execution evidence、Bark `sent`、`legacy_prompt`、production main path readiness、manual-only safety。
  - unexpired event assertion 已机器化：`macro_event.valid_until` 必须 ISO parseable、timezone-aware、future/unexpired；expired 或 timezone-less assertion 会失败。
  - production main path readiness 已机器化：`readiness.prod_actionable.production_main_path_ready=true` 且 `main_path_blockers=[]` 才能继续。
  - non-production model denylist 已机器化：`mock`、`fixture`、`fake`、`stub`、`test`、`local` token 出现在 `decision.final` model 名称中都不能通过。
  - strict Bark notification row 已机器化：同一条 notification history 必须同时满足 `channel=bark`、`status=sent`、`ok=true`、HTTP 2xx `status_code`、且 `created_at/sent_at` 不早于本次 manual-run start；非 Bark channel、failed Bark row、旧 row 或非 2xx row 即使带 `ok=true` 也不能通过。
  - 最新 fake-server contract：`python3 -m pytest tests/deployment/test_hosted_prod_actionable_smoke.py -q` -> `15 passed`。
  - 这只是部署契约测试，不是生产成功。

- hosted real-outcome collection gate：
  - `tools/deployment/smoke_hosted_real_outcome_collection.py` 默认要求 `--same-host-data-dir-confirmed`、production outcome config preflight、collector JSON contract、`collection_errors_allowed=false`、`collected>0`。
  - `new_refs_verified=true` 现在要求新 matched ref 的 `collected_at` 不早于本次 gate start，或同一 ref 在 gate start 后更新；如果 pre-collection evidence 失败，旧 outcome / old outcome 仍不能冒充本次 collection success。
  - 最新 fake-runner contract：`python3 -m pytest tests/deployment/test_hosted_real_outcome_collection_smoke.py -q` -> `16 passed`。
  - 这只证明 `real-outcome` gate contract，不证明 `prod-actionable`。

- hosted-positive visual proof：
  - `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` 时，`PLAYWRIGHT_REUSE_EXISTING_STACK=true`、`PLAYWRIGHT_FRONTEND_BASE_URL`、`PLAYWRIGHT_API_BASE_URL` 都必须显式给出。
  - frontend/API base URL 都必须是 public HTTPS；localhost/private/non-HTTPS 在 Playwright config load 阶段失败，不会启动本地 fixture stack。
  - hosted-positive spec 现在还会 DNS 解析 frontend/API hostname；解析到 local/private/reserved 地址的 public-looking hostname 会失败，不能用公网样式域名指向本地或内网来冒充 hosted production visual proof。
  - hosted-positive visual proof 也要求 `readiness.prod_actionable.production_main_path_ready=true` 且 `main_path_blockers=[]`。
  - hosted-positive visual proof 现在与 API `prod-actionable` smoke 对齐：拒绝本地/mock `market_data.okx_base_url`、拒绝 `readiness.market_data.status=unsafe`、拒绝非生产模型名，并要求同一 run 的 Bark row 同时满足 `channel=bark`、`status=sent`、`ok=true`、HTTP 2xx `status_code`、timezone-aware timestamp 且不早于本次 manual-run start。
  - 负向校验结果：`PLAYWRIGHT_FRONTEND_BASE_URL to be a public HTTPS URL`。
  - positive hosted visual proof 仍未在本 workspace 的真实 public HTTPS hosted 环境通过。

- production-intent API contract：
  - 新增 `tests/api/test_runs_routes.py::test_manual_run_production_intent_path_projects_model_notification_and_legacy_lineage`。
  - 红灯：`business_summary.generation_summary` 缺少安全的 `provider/status` 字段，API/visual gate 只能读产品标签，无法机器化验证真实模型证据。
  - 绿灯：`business_summary.generation_summary` 现在保留 `provider`、`model`、`status`，同时继续隐藏 raw `request_json` / `response_json`。
  - 该测试通过真实 `/api/runs/manual`、legacy workflow、production/risk gate、journal、notification history、run detail、`legacy_prompt` lineage 和业务摘要投影；OpenAI-compatible、OKX public、Bark 仍是测试桩，因此 proof level 是 production-intent contract，不是 hosted `prod-actionable`。
  - 后续补强：每条 persisted manual run 现在暴露 `main_path_contract`，并在 immediate response、run detail API projection、frontend schemas 中保留同一份证明边界。
  - 当前主链 contract 按配置记录 proof level：本地 mock-LLM 栈为 `proof_level=mock`，production-intent 配置契约才是 `proof_level=production-intent-contract`。共同边界是 `production_success=false`、`hosted_proof_required=true`、`does_not_prove=hosted_prod_actionable`、`runtime_role=production_main`、`final_input_contract.mode=legacy_prompt`、`manual_only.manual_execution_required=true`、`manual_only.auto_order_enabled=false`。这避免本地/mock 证据被误贴成 hosted `prod-actionable`，但不关闭 P0。

- local `--prod-actionable` rehearsal：
  - localhost 成功和 skip/failure 输出都必须自描述为 `local-prod-actionable-rehearsal`。
  - 成功与 missing/unsafe readiness skip payload 都必须带 `production_success=false`、`hosted_proof_required=true`、`does_not_prove=hosted_prod_actionable`。
  - 因此本地真实依赖演练或 exit `2` 缺 readiness 截图都不能被贴成 hosted `prod-actionable` production proof。

- 最新 no-secret local matrix：
  - `python3 tools/local_stack/run_local_checks.py` 最新结果：Python pytest `1113 passed, 2 warnings`；frontend typecheck passed；frontend production build passed；Playwright `48 passed, 10 skipped`；fixture、mock LLM、actionable staging、seeded mock-outcome、collect-outcomes fixture smokes passed。
  - proof level 仍是 local-browser + fixture/mock/staging/collector wiring only，not production success。

- strict prod gate still exits `2`：
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` 仍因 missing readiness 退出 `2`。
  - 缺口仍包括 `BARK_DEVICE_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`、`MACRO_EVENT_PROVIDER=no_active_event`。
  - 这是正确阻断，不是失败掩盖。

- Docker hosted runtime：
  - `python3 tools/deployment/smoke_docker_hosted_runtime.py` 最新结果 exit `0`，但 proof level 是 hosted-runtime only。
  - 默认 runtime 仍是 fixture：`decision_engine=fixture`、`market_provider=fixture`、`prod_actionable_ready=false`。
  - strict prod-config negative 仍正确拒绝 fixture：`production config requires decision.engine=openai_compatible`。

## 不变边界

- 不自动交易。
- `manual_execution_required=true`。
- `auto_order_enabled=false`。
- 不引入 OKX trade/withdraw key。
- `production_candidate_swarm` 仍是 audit-only/blocked。
- local/mock/staging/fixture/hosted-runtime 成功都不是 production success。
