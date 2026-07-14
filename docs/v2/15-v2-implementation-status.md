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

当前 16 个计划项（Task 0、0B、1-14）的裁决为：`done=0`、`partial=12`、`blocked=1`、`not_started=3`。**V2 不是 production ready。** 本文随 V2 recovery checkpoint 保存当前候选实现和证据边界；该 checkpoint 只解决未提交代码不可审计的问题，不构成 release、attestation 或 Task 完成追认。`14-v2-final-implementation-plan.md` 的 97 个 checkbox 全部未维护（97 个均为 unchecked）；checkbox 不能作为实际进度证据，本文也不据此反向勾选或追认完成。Product FastAPI 已作为 custom app 挂载到官方 Agent Server，不再部署第二个 Product HTTP 服务；官方 Postgres Runtime 镜像能够构建并连接独立 Agent PostgreSQL/Redis，但当前缺少有效 LangSmith API key 或自托管 license，尚未形成通过 readiness 的 durable Runtime 证明。

## 2. Task 0-14 状态矩阵

| Task | 状态 | 已存在的代码/测试证据 | 缺失项与裁决依据 |
|---|---|---|---|
| 0 Immutable Normative Baseline | `partial` | 13/14 及 V2 ADR 已在历史提交中形成；本 recovery candidate 的父提交为 `9ac296f`。 | `docs/v2/normative-baseline.json`、三段有序 review/attestation、release candidate 干净树证明均不存在；recovery checkpoint 不能替代 Task 0 完成条件。 |
| 0B Requirement Registry | `not_started` | 无可归属的 bootstrap 实现。 | registry/generator/verifier/transition tests、`requirements-registry.yaml`、pre-RED receipts 和实施说明均不存在。已写代码的历史 RED/owner receipt 不能事后伪造。 |
| 1 Dependency/Agent Server Bootstrap | `partial` | 精确依赖锁、uv source 模式的 `langgraph.json`、canonical graph export、`probe_agent_server.sh`、Agent Server base image digest lock 与隔离的 Agent PostgreSQL/Redis Compose 已存在。官方 `langgraph build` 产物已验证不包含 CLI/inmem/pytest 和 `.env`/tests/cache。 | `versions.json`、完整实施说明和最终 attestation 缺失；licensed Runtime 因缺有效 LangSmith/license credential 未通过 readiness，因而没有 restart persistence 或生产持久化证明。 |
| 2 Actor/Auth/Tenant Isolation | `partial` | `ActorContext`、Agent Server auth、internal JWT、namespace rewrite、development bootstrap 及相关 contracts 已存在。Backend `APP_ENVIRONMENT` 必填且拒绝未知值；`staging`/`production` 在没有 verifier 时于应用构造阶段 fail closed。Agent Server authenticated readiness 使用显式独立的 `AGENT_HEALTHCHECK_*` probe principal，而不是 development bootstrap principal；该 principal 或 signer 缺失时 fail closed，并与无身份的 socket liveness probe 分离。Frontend 在 production build 缺少 `APP_ENVIRONMENT` 时也按非本地环境 fail closed；production 即使误配完整 development bootstrap 变量也不会签发 bootstrap JWT。local-proof 仅在 `APP_ENVIRONMENT=development`、显式 profile、全部非空白 actor 字段和实际 loopback peer 同时成立时启用；contracts 覆盖纯空白字段、裸 `::1` 接受和远端 IPv6 拒绝。 | membership/launch-boundary、安全矩阵、真实 cross-tenant integration、operator audit、实施说明与 review/attestation 缺失；独立 probe principal 和环境门禁不等于 hosted 身份与租户隔离证明。 |
| 3 Domain/Evidence/Risk | `partial` | typed domain、evidence/risk policy、golden cases 及对应单元/contract coverage 均存在，并包含在通过的 backend 全量 suite 中。 | 缺 Task 0B registry/receipt、可核验 RED、实施说明和双 review/attestation；按 Task 14 协议不能判 `done`。 |
| 4 OKX/Web Search Providers | `blocked` | OKX/search/provider typed code与 parser/contract tests 已存在。严格环境的 provider readiness 为 async：阻塞 model probe 通过 `asyncio.to_thread` 隔离，Tavily connectivity 与 retry 使用 `asearch`/`execute_async`。真实 OKX typed snapshot 在显式配置本地 HTTP proxy 时成功，strict real Playwright 也已越过 OKX 阶段。 | 真实主链的 built-in `web_search` 连续 3 次既没有可验证 provider URL citation，也没有 completed/successful server tool call（即无 citation/tool success），因此产出 `UnverifiedServerToolCall`，任务最终为 `research_unavailable`。没有有效 `TAVILY_API_KEY`，Tavily 仍未验证；OKX 无显式本地 proxy 的路径也不能作为可用证明。缺 `search-provider-selection.json`、完整 real-provider proof 和 attestation。 |
| 5 Agent Factories/Structured Output | `partial` | market/research factories、structured model path、capability selection 与 async readiness contracts 已存在。 | middleware profiles/hook order、middleware/call budgets、PII canary、完整 research permission tests、实施说明与 attestation 缺失。独立 model/capability probe 通过不等于 integrated research 链通过。 |
| 6 Canonical Graph/HITL | `partial` | 当前 graph 已有 validate/market/research/analyze/evidence/risk/artifact/terminal 垂直链及 fixture contract 覆盖。 | 官方 HITL 尚未交付：完整 node 拆分、root/nested interrupt、approve/reject/edit/expiry、namespace/checkpoint routing、race/idempotency、restart resume，以及完整 command/event-stream contract 均缺失。 |
| 7 Product PostgreSQL/Outbox | `partial` | Alembic 0001-0004、SQLAlchemy models/repository/UoW、task projection、command dispatcher/worker 及 integration tests 已存在。Worker 在 official Run start 期间续租/heartbeat；已绑定 official Run 后若丢失 lease，会取消本地 join 并 detach，而不是误取消远端 Run。 | 完整关系模型、DB role isolation、progressive persistence、outbox/notification/reconciler、完整 worker lifecycle 与真实 PostgreSQL/恢复证明缺失；durable Agent Server 也未建立。全量 suite 的 skip 不能计为这些能力已通过。 |
| 8 Product APIs/Agent Integration | `partial` | 最小 Product API 已支持 create analysis、run list、get task；`GET /api/v2/tasks/{task_id}` 支持显式 `run_id` 读取历史 attempt。已有 official `langgraph-sdk` Runs client（create/list/join/cancel）和 `TaskView.agent_stream` 的 assistant/thread/run stream-binding metadata，以及 provision/worker contracts。Product routes 已挂载到 Agent Server `/app`，浏览器同源 BFF contract 保持不变。失败投影会白名单保留 `provider`、`error_type`、`attempt`，同时丢弃 raw response、authorization、endpoint 和 correlation 等非公开字段。这里的证据仅是 official SDK Run client 与 stream binding metadata，**不是完整 stream protocol**。 | Runs detail/Inbox/Workspace/feedback/commands 完整 API、Protocol v2 command/event contract、官方 HITL routing、licensed restart durability 与 protocol probe artifacts 缺失。 |
| 9 Observability | `partial` | callbacks assembly、provider attempt correlation 字段与 contract tests 已存在。 | 没有 fresh LangSmith/Langfuse 双端真实 trace，也没有贯穿 BFF/Product API/Task/official Thread/Run/provider/artifact 的 full correlation proof；secret canary、Dataset/Experiment/Release Gate、outage alert 和 attestation 均缺失。 |
| 10 Frontend Runtime/BFF/View Models | `partial` | Next.js/Auth.js、same-origin agent/product BFF、`@langchain/react` thread attachment、typed schemas/view models 与 production environment fail-closed guard 已存在。严格 runtime 的未登录跳转只从经过校验的 HTTPS `NEXTAUTH_URL` 构造 canonical sign-in/callback origin，不信任请求 origin；缺失或无效配置返回 `503`。fresh `lint`、`typecheck`、production build、unit 均为 green，unit 共 `127 passed`。 | 完整 durable command adapter、官方 HITL/fork/replay/history contract、生产 OIDC 与 Task 10 规定的实施说明/attestation 未闭合；canonical redirect contract 和当前 stream attachment 分别不能替代 hosted OIDC 证明与完整 Protocol v2 command/event 实现。 |
| 11 Product UI | `partial` | `/work`、`/runs` 和 run detail 产品面、响应式样式及 fixture Playwright 文件已存在；fresh fixture Playwright 在 Desktop 与 Pixel 7 共 `32 passed, 4 skipped`，其中包含白名单 provider/error type/attempt 诊断的无溢出与无敏感字段回归。 | **Inbox、Library、Settings 未交付**；当前路由仍不能构成计划要求的五个产品面，官方 HITL、notification、feedback、content safety、accessibility/VoiceOver artifacts 均缺失。4 个 real-flow skip 与 fixture green 不能替代真实成功主链或 hosted visual proof。 |
| 12 Real E2E/Failure Injection | `partial` | 有 `real-product-flow`、`official-stream-main-flow` 两个受环境开关保护的早期 E2E 文件；strict real Playwright 已证明浏览器、BFF、Product API、worker、Agent Server 与真实 OKX 能连通到 research 前。 | strict real Playwright 在 research 阶段因 built-in `web_search` 连续 3 次无 citation/tool success 而以 `UnverifiedServerToolCall` 失败，未产生成功 Artifact。计划命名的 real/failure profiles、failure-injection API、官方 HITL recovery、cross-tenant、notification、visual regression 和完整 stack scripts 均缺失。 |
| 13 Deep Research/Lifecycle | `not_started` | Task 5 的同步 research factory 不能替代 Task 13 交付。 | background Deep Research、monitor/Cron、retention/export/deletion、Outcome、memory、entitlement/usage/webhook workers 与 UI/tests 全部缺失。 |
| 14 Production Gates/Legacy Removal | `not_started` | Dockerfile/Compose 已固定 Python、Node、PostgreSQL、pgvector、Redis 和 Agent Server digest；官方 Agent image 使用 uv.lock、排除 dev/inmem 与敏感构建上下文，API 只发布到 loopback。独立 Product/Agent PostgreSQL、Redis、migrate/bootstrap、custom app/auth 均已执行到 licensed Runtime 校验阶段。 | 有效 LangSmith/license credential、durable restart proof、production packaging、hosted HTTPS、security/release gates、SLO/load/backup/restore/key rotation/upgrade/rollback、SBOM/signing、requirement evidence、独立 attestation、V1 parity/removal 均不存在；镜像构建成功不能解释为 release 或 production-ready 证明。 |

## 3. Fresh 测试与运行证据

截至本次审计，当前工作树的 fresh 本地命令结果如下；所有 skip 都按“未证明”处理。表中明确标为“最近一次”的外部运行没有在本次安全边界下重新执行：

| 范围 | 结果 | 解释 |
|---|---|---|
| Backend `APP_ENVIRONMENT=test .venv/bin/pytest -q backend/tests` | `376 passed, 24 skipped, 1 warning` | 当前 hermetic/local backend suite 为 green；24 个 skip 仍按未证明处理，不能用来宣称外部 provider、durability 或生产门禁完成。唯一 warning 是 FastAPI/Starlette TestClient dependency deprecation。 |
| Root migration/structure/deployment suite | `1154 collected；full run exit 0` | 根目录 `tests` 全量执行退出为 0，覆盖 V1 retirement accounting、V2 route ownership、formal docs 状态和容器命令契约；这是本地静态/contract evidence。 |
| Auth/deployment focused contracts | `包含在 backend/root 全量 suite；额外 recursive-ignore 回归 2 passed` | Agent readiness 独立 probe principal、hosted verifier fail-closed、loopback/IPv6/空白身份、liveness/readiness 分离、递归 ignore 与 Compose topology 已纳入全量 suites；本次不另造不可复现的聚焦总数。 |
| PostgreSQL integration | `27 passed` | 在本机真实 PostgreSQL 上显式开启 `REAL_DATABASE_TESTS=1`，当前 `backend/tests/integration` 全量通过，包含 artifact transaction、command dispatcher、Product analysis service 及非数据库 integration cases；这仍不是 hosted role isolation、backup/restore 或 HA proof。 |
| Real OKX typed snapshot | 仅在显式本地 HTTP proxy 下成功 | 证明 typed OKX adapter 能处理真实交易所数据；同时证明当前网络环境对该 proxy 有运行依赖，不能推广为 direct/hosted 可用性。 |
| Real Tavily | 未验证 | 当前没有有效 `TAVILY_API_KEY`；async connectivity/retry 代码与 hermetic tests 通过不构成真实 Tavily proof。 |
| Frontend static/unit/build | lint（零 diagnostic）、typecheck、production build、unit 均为 green；`127 passed` | canonical `NEXTAUTH_URL` redirect/fail-closed coverage 已纳入 unit；证明当前 frontend/BFF/view-model 切片可生产构建，不等于 hosted behavior、生产 OIDC 或真实 provider 主链通过。 |
| Fixture Playwright | `32 passed, 4 skipped` | Desktop `1440x1000` 与 Pixel 7 `412x915` 各 16 passed/2 skipped；10/10 已测状态水平 overflow 为 0，四个 `/work` 状态 overlap 数组为空，`pageError=0`。四条 browser console error 均来自显式断网/404 负向 fixture。4 个 `REAL_PRODUCT_E2E` case 明确未执行，不能计为真实链通过。 |
| Strict real Playwright（最近一次已记录，未在本次重新执行） | 到达真实 OKX，随后失败 | 最近一次真实 integrated chain 在 research 阶段执行 3 次 built-in `web_search` attempt，均无可验证 citation 且无 completed/successful server tool call，因而为 `UnverifiedServerToolCall` 并最终 `research_unavailable`；没有成功 Artifact，因此不能计为 real E2E pass。 |

## 4. 真实外部证据限制

- 开发 probe 仍使用 `langgraph dev`，但部署镜像由官方 `langgraph build` 从固定 digest 和 uv.lock 构建，最终镜像不含 `langgraph-cli`/`langgraph-runtime-inmem`。该镜像已连接独立 Agent PostgreSQL/Redis并加载 custom auth/app，但因缺有效 LangSmith/license credential 未通过启动；当前仍没有 restart persistence、licensed durable deployment 或生产 HA 证明。
- Product task GET 现在可以用 `run_id` 选择历史 Product Run，并把对应 Artifact/Evidence 与 official assistant/thread/run binding 一起投影。这是历史读取与 stream re-attachment metadata，不证明 Agent Server 重启后仍可恢复，也不构成完整 Protocol v2 replay/ordering contract。
- 真实 OKX typed snapshot 和 strict browser 链都依赖显式本地 HTTP proxy；未通过该 proxy 的 direct/hosted 网络路径没有成功证明。Tavily 没有有效 key，仍为 unverified。
- 最近一次已记录的 strict real Playwright 已到达真实 OKX，但 built-in `web_search` 的 3 次 attempt 都没有可验证 provider URL citation，也没有 completed/successful server tool call，因而以 `UnverifiedServerToolCall` 失败并最终成为 `research_unavailable`。该外部运行未在本次凭据安全边界下重跑；async probe/retry 的实现正确性不能覆盖这一真实集成失败。
- Backend 与 production frontend 的 environment/auth/readiness 路径均 fail closed。Agent authenticated readiness 使用独立 `AGENT_HEALTHCHECK_*` probe principal，并与 socket liveness 分离；frontend 未登录跳转使用 canonical HTTPS `NEXTAUTH_URL`，缺失或无效时返回 `503`。这些是必要控制，不是 hosted OIDC、cross-tenant、secret canary、full correlation 或 release security gate 的替代证据。
- 根目录与 `backend/.dockerignore` 已分别保护 helper 和官方 Agent 构建上下文，Agent context 对任意深度的 `.env*` 递归排除；启动脚本会验证最终镜像的锁定基础层前缀、官方 auth/http/graph 映射、生产依赖与排除项，并在 180 秒启动超时或信号失败后按同一 Compose project 自动清理且保留数据卷。实测 Agent image 不含 `.env`、tests、coverage、cache、CLI 或 inmem Runtime。Compose 使用固定 digest 的 Redis 7，只部署一个官方 Agent HTTP 服务，Product app 挂载在 `/app`；当前缺口是 license 后的完整启动和 restart durability，而不是旧 dual-service/dev-runtime 偏差。
- 当前没有 hosted HTTPS、真实生产数据库角色/恢复、outbox/reconciler/通知回执、LangSmith/Langfuse 双写、端到端 correlation、告警、负载/SLO、key rotation、upgrade/rollback、SBOM/signing 或 release attestation 的 fresh 证据。

## 5. 下一条关键路径

1. 先保存当前 dirty WIP 为可审查的恢复基线并回到干净工作树；不得 reset/revert/clean，也不得伪造已经错过的 RED、owner receipt 或 review 时间线。
2. 补齐 Task 0 manifest 与 Task 0B requirement registry，明确把当前实现登记为 pre-existing recovery，而不是追认完成。
3. 立即收敛 Task 4：保留 OKX 显式 proxy 前提并形成可部署网络决策，修复 built-in `web_search` 当前同时缺 citation/tool success 的 `UnverifiedServerToolCall` 链，或提供有效 Tavily key 完成 async connectivity/real search proof；随后生成 provider-selection artifact，并让 strict real E2E 成功且外部 proof 零 skip。
4. 搜索恢复后按 Task 6 -> 7 -> 8 完成官方 HITL、durable Agent Server、完整 command/event protocol、outbox/reconciler 与 worker recovery；不得把现有 official SDK Run client 和 stream binding metadata 表述为完整 stream protocol。
5. 提供有效 LangSmith API key 或自托管 license，完成官方 Postgres Runtime readiness、restart durability 与 protocol probe；之后补齐 full correlation、middleware/call budgets、Inbox/Library/Settings、hosted security 与 Task 12-14 release gates。
