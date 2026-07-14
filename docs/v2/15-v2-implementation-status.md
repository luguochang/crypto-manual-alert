# V2 Implementation Status Ledger

> authority_class: informative
>
> 审计时点：2026-07-14（Asia/Shanghai）
>
> 本文只记录当前工作树的实施状态和证据边界，不修改、替代或追认 `13-v2-final-rebuild-spec.md` 与 `14-v2-final-implementation-plan.md` 的 normative 要求。

## 1. 判定口径与总裁决

- `done`：Task 14 规定的代码、测试、真实环境证明、candidate/review/attestation 均存在且可核验。
- `partial`：已有实质代码或测试切片，但 Task 的必需范围、真实证明或实施协议尚未闭合。
- `blocked`：已有实质实现，但当前外部能力或环境使关键验收链无法继续成立。
- `not_started`：没有足以构成该 Task 交付切片的实现与测试证据。

当前 16 个计划项（Task 0、0B、1-14）的裁决为：`done=0`、`partial=13`、`blocked=0`、`not_started=3`。**V2 不是 production ready。** M1 本地真实纵向链已经通过，但这只证明开发 Runtime 下的 OKX、搜索、模型、数据库、官方 Run 读取和前端渲染链可运行，不构成 durable Runtime、HITL、跨租户、托管部署或 release attestation。`14-v2-final-implementation-plan.md` 的 97 个 checkbox 仍未按 Task 14 实施协议维护；本文不据此反向追认 Task 完成。Product FastAPI 已作为 custom app 挂载到官方 Agent Server，不再部署第二个 Product HTTP 服务；官方 Postgres Runtime 镜像能够构建并连接独立 Agent PostgreSQL/Redis，但当前缺少有效 LangSmith API key 或自托管 license，尚未形成通过 readiness 的 durable Runtime 证明。

## 2. Task 0-14 状态矩阵

| Task | 状态 | 已存在的代码/测试证据 | 缺失项与裁决依据 |
|---|---|---|---|
| 0 Immutable Normative Baseline | `partial` | 13/14 及 V2 ADR 已在历史提交中形成；本 recovery candidate 的父提交为 `9ac296f`。 | `docs/v2/normative-baseline.json`、三段有序 review/attestation、release candidate 干净树证明均不存在；recovery checkpoint 不能替代 Task 0 完成条件。 |
| 0B Requirement Registry | `not_started` | 无可归属的 bootstrap 实现。 | registry/generator/verifier/transition tests、`requirements-registry.yaml`、pre-RED receipts 和实施说明均不存在。已写代码的历史 RED/owner receipt 不能事后伪造。 |
| 1 Dependency/Agent Server Bootstrap | `partial` | 精确依赖锁、uv source 模式的 `langgraph.json`、canonical graph export、`probe_agent_server.sh`、Agent Server base image digest lock 与隔离的 Agent PostgreSQL/Redis Compose 已存在。官方 `langgraph build` 产物已验证不包含 CLI/inmem/pytest 和 `.env`/tests/cache。 | `versions.json`、完整实施说明和最终 attestation 缺失；licensed Runtime 因缺有效 LangSmith/license credential 未通过 readiness，因而没有 restart persistence 或生产持久化证明。 |
| 2 Actor/Auth/Tenant Isolation | `partial` | `ActorContext`、Agent Server auth、internal JWT、namespace rewrite、development bootstrap 及相关 contracts 已存在。Backend `APP_ENVIRONMENT` 必填且拒绝未知值；`staging`/`production` 在没有 verifier 时于应用构造阶段 fail closed。Agent Server authenticated readiness 使用显式独立的 `AGENT_HEALTHCHECK_*` probe principal，而不是 development bootstrap principal；该 principal 或 signer 缺失时 fail closed，并与无身份的 socket liveness probe 分离。Frontend 在 production build 缺少 `APP_ENVIRONMENT` 时也按非本地环境 fail closed；production 即使误配完整 development bootstrap 变量也不会签发 bootstrap JWT。local-proof 仅在 `APP_ENVIRONMENT=development`、显式 profile、全部非空白 actor 字段和实际 loopback peer 同时成立时启用；contracts 覆盖纯空白字段、裸 `::1` 接受和远端 IPv6 拒绝。 | membership/launch-boundary、安全矩阵、真实 cross-tenant integration、operator audit、实施说明与 review/attestation 缺失；独立 probe principal 和环境门禁不等于 hosted 身份与租户隔离证明。 |
| 3 Domain/Evidence/Risk | `partial` | typed domain、evidence/risk policy、golden cases 及对应单元/contract coverage 均存在，并包含在通过的 backend 全量 suite 中。 | 缺 Task 0B registry/receipt、可核验 RED、实施说明和双 review/attestation；按 Task 14 协议不能判 `done`。 |
| 4 OKX/Web Search Providers | `partial` | OKX/search/provider typed code与 parser/contract tests 已存在。严格环境的 provider readiness 为 async；Tavily connectivity 与 retry 使用 `asearch`/`execute_async`。由于当前 OpenAI-compatible endpoint 能完成 server-side search 但不返回 provider citation，新增显式 `duckduckgo` provider：维护中的 `ddgs` client 封装为 LangChain `StructuredTool`，并把 URL、标题、摘要、provider、发布时间、获取时间和内容 hash 规范化为 `WebEvidence`。真实 OKX 与 DDG 均在显式本地 proxy 下成功，四条 strict real Playwright 已通过。 | built-in search 在当前 endpoint 仍不能提供可验 citation；Tavily 无有效 key，仍未真实验证。当前 proof 依赖本地 proxy；缺 hosted 网络决策、provider-selection artifact、failure matrix 和 attestation。 |
| 5 Agent Factories/Structured Output | `partial` | market/research factories、structured model path、capability selection 与 async readiness contracts 已存在。Builtin Web Search 保留 Responses 模式；研究抽取和市场分析通过共享 helper 强制使用 Chat Completions，底层 `/v1/responses` 与 `/v1/chat/completions` transport contracts 均有测试。真实 integrated research/analysis 链已在桌面和移动 Playwright 中成功。 | middleware profiles/hook order、middleware/call budgets、PII canary、完整 research permission tests、实施说明与 attestation 缺失。 |
| 6 Canonical Graph/HITL | `partial` | 当前 graph 已有 validate/market/research/analyze/evidence/risk/artifact/terminal 垂直链及 fixture contract 覆盖。 | 官方 HITL 尚未交付：完整 node 拆分、root/nested interrupt、approve/reject/edit/expiry、namespace/checkpoint routing、race/idempotency、restart resume，以及完整 command/event-stream contract 均缺失。 |
| 7 Product PostgreSQL/Outbox | `partial` | Alembic 0001-0004、SQLAlchemy models/repository/UoW、task projection、command dispatcher/worker 及 integration tests 已存在。Worker 在 official Run start 期间续租/heartbeat；已绑定 official Run 后若丢失 lease，会取消本地 join 并 detach，而不是误取消远端 Run。 | 完整关系模型、DB role isolation、progressive persistence、outbox/notification/reconciler、完整 worker lifecycle 与真实 PostgreSQL/恢复证明缺失；durable Agent Server 也未建立。全量 suite 的 skip 不能计为这些能力已通过。 |
| 8 Product APIs/Agent Integration | `partial` | 最小 Product API 已支持 create analysis、run list、get task；`GET /api/v2/tasks/{task_id}` 支持显式 `run_id` 读取历史 attempt。已有 official `langgraph-sdk` Runs client（create/list/join/cancel）和 `TaskView.agent_stream` binding。Product routes 已挂载到 Agent Server `/app`。真实浏览器已观察同一 official Thread 的 state、history 与 SSE events，并验证浏览器不直接创建 command/run。失败投影只白名单保留公开诊断。 | `runs.get` 对账、terminal-only join、幂等/有 fence 的投影、重启 reconciler、orphan deadline 与 durable cancel 尚未实现，因此当前 proof **不是**完整可恢复 stream protocol。Runs detail/Inbox/Workspace/feedback/commands 完整 API、官方 HITL routing、licensed restart durability 与 protocol probe artifacts仍缺失。 |
| 9 Observability | `partial` | callbacks assembly、provider attempt correlation 字段与 contract tests 已存在。 | 没有 fresh LangSmith/Langfuse 双端真实 trace，也没有贯穿 BFF/Product API/Task/official Thread/Run/provider/artifact 的 full correlation proof；secret canary、Dataset/Experiment/Release Gate、outage alert 和 attestation 均缺失。 |
| 10 Frontend Runtime/BFF/View Models | `partial` | Next.js/Auth.js、same-origin agent/product BFF、`@langchain/react` thread attachment、typed schemas/view models 与 production environment fail-closed guard 已存在。开发 BFF 只在 loopback Product upstream 注入 server-owned local Agent token，远端 upstream 与严格环境均不使用该路径。fresh `lint`、`typecheck`、production build、unit 均为 green，unit 共 `128 passed`。 | 完整 durable command adapter、官方 HITL/fork/replay/history contract、生产 OIDC 与 Task 10 规定的实施说明/attestation 未闭合；当前 stream attachment不能替代完整 Protocol v2 command/event 实现。 |
| 11 Product UI | `partial` | `/work`、`/runs` 和 run detail 产品面、响应式样式及 Playwright 已存在。真实 Desktop `1440x1000` 与 Pixel 7 `412x915` 均渲染自然语言结论、风险、真实 Web 来源和官方执行进度；DOM 扫描验证无 raw JSON、横向溢出、无名称控件或 console/page/server error，全页截图已人工检查。 | **Inbox、Library、Settings 未交付**；当前路由仍不能构成计划要求的五个产品面，官方 HITL、notification、feedback、content safety、accessibility/VoiceOver artifacts 均缺失。 |
| 12 Real E2E/Failure Injection | `partial` | `real-product-flow` 与 `official-stream-main-flow` 在 Desktop 和 Pixel 7 共 `4 passed`。链路真实经过浏览器、Product BFF、Product PostgreSQL、worker、官方 Agent Server、OKX、DDG、结构化模型、Artifact 投影、state/history/SSE 和最终 UI；测试同时验证失败终态会立即报告而不会等待满超时。 | 计划命名的 failure profiles、failure-injection API、官方 HITL recovery、cross-tenant、notification、licensed restart、hosted visual regression 和完整 stack scripts 均缺失。 |
| 13 Deep Research/Lifecycle | `not_started` | Task 5 的同步 research factory 不能替代 Task 13 交付。 | background Deep Research、monitor/Cron、retention/export/deletion、Outcome、memory、entitlement/usage/webhook workers 与 UI/tests 全部缺失。 |
| 14 Production Gates/Legacy Removal | `not_started` | Dockerfile/Compose 已固定 Python、Node、PostgreSQL、pgvector、Redis 和 Agent Server digest；官方 Agent image 使用 uv.lock、排除 dev/inmem 与敏感构建上下文，API 只发布到 loopback。独立 Product/Agent PostgreSQL、Redis、migrate/bootstrap、custom app/auth 均已执行到 licensed Runtime 校验阶段。 | 有效 LangSmith/license credential、durable restart proof、production packaging、hosted HTTPS、security/release gates、SLO/load/backup/restore/key rotation/upgrade/rollback、SBOM/signing、requirement evidence、独立 attestation、V1 parity/removal 均不存在；镜像构建成功不能解释为 release 或 production-ready 证明。 |

## 3. Fresh 测试与运行证据

截至本次审计，当前工作树的 fresh 本地命令结果如下；所有 skip 都按“未证明”处理。表中明确标为“最近一次”的外部运行没有在本次安全边界下重新执行：

| 范围 | 结果 | 解释 |
|---|---|---|
| Backend `APP_ENVIRONMENT=test .venv/bin/pytest -q` | `385 passed, 24 skipped, 1 warning` | 当前 hermetic/local backend suite 为 green；24 个 skip 仍按未证明处理。外部纵向主链由下方 strict real Playwright 另行证明；skip 不能用来宣称 durability 或生产门禁完成。唯一 warning 是 FastAPI/Starlette TestClient dependency deprecation。 |
| Root migration/structure/deployment suite | `1154 collected；full run exit 0` | 根目录 `tests` 全量执行退出为 0，覆盖 V1 retirement accounting、V2 route ownership、formal docs 状态和容器命令契约；这是本地静态/contract evidence。 |
| Auth/deployment focused contracts | `包含在 backend/root 全量 suite；额外 recursive-ignore 回归 2 passed` | Agent readiness 独立 probe principal、hosted verifier fail-closed、loopback/IPv6/空白身份、liveness/readiness 分离、递归 ignore 与 Compose topology 已纳入全量 suites；本次不另造不可复现的聚焦总数。 |
| PostgreSQL integration | `27 passed` | 在本机真实 PostgreSQL 上显式开启 `REAL_DATABASE_TESTS=1`，当前 `backend/tests/integration` 全量通过，包含 artifact transaction、command dispatcher、Product analysis service 及非数据库 integration cases；这仍不是 hosted role isolation、backup/restore 或 HA proof。 |
| Real OKX typed snapshot | 仅在显式本地 HTTP proxy 下成功 | 证明 typed OKX adapter 能处理真实交易所数据；同时证明当前网络环境对该 proxy 有运行依赖，不能推广为 direct/hosted 可用性。 |
| Real DuckDuckGo | 真实 provider 与 Graph 主查询均成功 | 显式 local proxy 下取得公开 HTTPS 新闻证据，真实 Product E2E 的成功 projection 含 8 条 typed `duckduckgo` evidence；这不推广为 hosted 直连可用性。 |
| Real Tavily | 未验证 | 当前没有有效 `TAVILY_API_KEY`；async connectivity/retry 代码与 hermetic tests 通过不构成真实 Tavily proof。 |
| Frontend static/unit/build | lint（零 diagnostic）、typecheck、production build、unit 均为 green；`128 passed` | local-token loopback boundary 与 canonical redirect/fail-closed coverage 已纳入 unit；证明当前 frontend/BFF/view-model 切片可生产构建，不等于 hosted behavior或生产 OIDC。 |
| Fixture Playwright | `32 passed, 4 skipped` | Desktop `1440x1000` 与 Pixel 7 `412x915` 各 16 passed/2 skipped；10/10 已测状态水平 overflow 为 0，四个 `/work` 状态 overlap 数组为空，`pageError=0`。四条 browser console error 均来自显式断网/404 负向 fixture。4 个 `REAL_PRODUCT_E2E` case 明确未执行，不能计为真实链通过。 |
| Strict real Playwright | `4 passed (5.0m)` | `official-stream-main-flow` 与 `real-product-flow` 在 Desktop 和 Pixel 7 全部通过；真实任务产生成功 Artifact、typed WebEvidence、自然语言报告和官方 stream DOM，刷新后终态与 binding 保持一致。 |

## 4. 真实外部证据限制

- 开发 probe 仍使用 `langgraph dev`，但部署镜像由官方 `langgraph build` 从固定 digest 和 uv.lock 构建，最终镜像不含 `langgraph-cli`/`langgraph-runtime-inmem`。该镜像已连接独立 Agent PostgreSQL/Redis并加载 custom auth/app，但因缺有效 LangSmith/license credential 未通过启动；当前仍没有 restart persistence、licensed durable deployment 或生产 HA 证明。
- Product task GET 现在可以用 `run_id` 选择历史 Product Run，并把对应 Artifact/Evidence 与 official assistant/thread/run binding 一起投影。这是历史读取与 stream re-attachment metadata，不证明 Agent Server 重启后仍可恢复，也不构成完整 Protocol v2 replay/ordering contract。
- 真实 OKX、DDG 和 strict browser 链都依赖显式本地 HTTP proxy；未通过该 proxy 的 direct/hosted 网络路径没有成功证明。Tavily 没有有效 key，仍为 unverified。当前 OpenAI-compatible endpoint 的 built-in search 仍不返回可验 provider citation，因此没有把模型生成的普通 URL 降格当成证据。
- strict real Playwright 已在开发 Runtime 下通过，并证明真实 Product task、official Thread/Run 和 Artifact 可以成功串联；它没有覆盖 licensed Agent Server 重启、lease 丢失、join 断线、orphan、durable cancel 或 terminal projection replay，不能作为恢复能力证明。
- Backend 与 production frontend 的 environment/auth/readiness 路径均 fail closed。Agent authenticated readiness 使用独立 `AGENT_HEALTHCHECK_*` probe principal，并与 socket liveness 分离；frontend 未登录跳转使用 canonical HTTPS `NEXTAUTH_URL`，缺失或无效时返回 `503`。这些是必要控制，不是 hosted OIDC、cross-tenant、secret canary、full correlation 或 release security gate 的替代证据。
- 根目录与 `backend/.dockerignore` 已分别保护 helper 和官方 Agent 构建上下文，Agent context 对任意深度的 `.env*` 递归排除；启动脚本会验证最终镜像的锁定基础层前缀、官方 auth/http/graph 映射、生产依赖与排除项，并在 180 秒启动超时或信号失败后按同一 Compose project 自动清理且保留数据卷。实测 Agent image 不含 `.env`、tests、coverage、cache、CLI 或 inmem Runtime。Compose 使用固定 digest 的 Redis 7，只部署一个官方 Agent HTTP 服务，Product app 挂载在 `/app`；当前缺口是 license 后的完整启动和 restart durability，而不是旧 dual-service/dev-runtime 偏差。
- 当前没有 hosted HTTPS、真实生产数据库角色/恢复、outbox/reconciler/通知回执、LangSmith/Langfuse 双写、端到端 correlation、告警、负载/SLO、key rotation、upgrade/rollback、SBOM/signing 或 release attestation 的 fresh 证据。

## 5. 下一条关键路径

1. 保存当前 M1 真实纵向链为独立可审查提交；不得把开发 Runtime 成功追认为 durable production release。
2. 立即实现 M2.3 worker recovery：短 admission lease、official `runs.get` 对账、terminal-only join、fenced/idempotent projection、restart reconciler、orphan deadline 与 durable cancel。
3. 在恢复语义稳定后完成官方 HITL、完整 command/event protocol、outbox/notification 与跨租户集成；不得把现有 stream binding 表述为完整可恢复协议。
4. 提供有效 LangSmith API key 或自托管 license，完成官方 Postgres Runtime readiness、restart durability 与 protocol probe；同时补 Task 0/0B governance artifacts，不事后伪造 RED 或 owner receipt。
5. 最后补齐 full correlation、middleware/call budgets、Inbox/Library/Settings、hosted security、failure injection 和 Task 12-14 release gates。
