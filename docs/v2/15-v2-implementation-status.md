# V2 Implementation Status Ledger

> authority_class: informative
>
> 当前交接校正：2026-07-20（Asia/Shanghai）；规范实现分支为 `codex/v2-production-completion`，稳定的完整代码 checkpoint 为 `6739f817c648c233944c86c99ae1d9cfa9fb0b37`。当前远程 HEAD 必须通过 `git fetch --all --prune`、`git switch codex/v2-production-completion`、`git pull --ff-only origin codex/v2-production-completion` 后现场确认。本文后续较早日期的段落保留当时的审计上下文，其中出现的“未提交”“旧 HEAD”或“未 push”只表示对应历史时点，不代表当前 Git 状态。
>
> 本文只记录当前工作树的实施状态和证据边界，不修改、替代或追认 `13-v2-final-rebuild-spec.md` 与 `14-v2-final-implementation-plan.md` 的 normative 要求。

## 0. 当前证据更正

### 2026-07-20 本地真实主流程与相关性边界校正

2026-07-19 记录的研究来源相关性 P0 已对新运行完成修复。无关来源仍以
`evidence_relation="excluded"` 保存在 Graph/Product/PostgreSQL 审计集合中，但不会
进入研究或市场分析模型、verified/available 统计、Evidence/Risk 判定、Artifact
引用或 provenance 聚合；全量无关时以 `NoRelevantResearchEvidence` fail closed。
历史数据未被回写。本轮 focused backend 为 `33 passed`，前端会单独显示有效和已排除
来源，不能由 excluded-only 数据制造 `available` 状态。

真实 Product Desktop/Pixel 7 回归保留了两轮 RED。第一轮分别是 Tavily
`TimeoutError` 与 `MissingCitedTicker`，根因为行情 fallback 查询召回不相关网页；查询
已改为 `current BTC USD price market data live`，引用和值一致性门禁未放宽。第二轮
Pixel 7 成功，Desktop 数据库 Task 成功但 UI 因一次超过八秒 BFF budget 的 `502` 永久
停止轮询；Product polling 现对 transport、`408`、`429`、`5xx` 采用最高十秒的有界
自动重试。最终真实 Product 为 `2 passed (1.7m)`。两个最终 Task 均为 1 Snapshot、
8 Evidence、1 committed Artifact、1 Decision、7 Events，PostgreSQL 核验
`excluded_urls_cited=0`。前端为 `39 files / 445 tests passed`，typecheck/lint 通过。

Monitor 的第一次回归保留了单选受控 `<select>` 的 React read-only console RED；该固定
条件现使用非交互语义 `<output>`。最终真实 Monitor Desktop/Pixel 7 为
`2 passed (8.7s)`，证据目录
`/tmp/crypto-alert-real-monitor-e2e-20260720-after-readonly-fix` 包含 JUnit、JSON、HTML、
traces 和八张视觉截图。其两个后台 Task 已终止：一个无错误地被 Evidence/Risk 边界
阻断并只保留 draft，另一个成功提交 1 Artifact 和 1 Decision。

以上只把 G0.2 **本机 development 主流程**重新收口为 green。它没有关闭 licensed
persistent Agent Server、restart/replay、hosted OIDC/HTTPS、真实外部
LangSmith/Langfuse、通知回执、PITR/SLO/security/SBOM signing 或完整 M1-M6 release
gate。当前结论继续是 `V2 PARTIAL / Production Ready: NO`；没有 stage、commit 或
push。

### 2026-07-19 当前运行校正

本轮真实运行确认：mounted Product API 的 `401 resource_token_invalid` 是本地
`APP_ENVIRONMENT=local` 启动身份与 PostgreSQL 现有 membership 不一致造成的，
不是 Library 没有数据，也没有通过关闭 `enable_custom_route_auth` 或添加未定义
header 绕过。使用匹配的 development local-proof 身份后，Next BFF 和 mounted
`GET /app/api/v2/artifacts` 均返回 `200`，当前作用域可读 3 个 committed
Artifact。

真实 Monitor Desktop/Pixel 7 无 mock Playwright 已完成 create -> scheduler active
-> refresh/rejoin -> trigger history -> pause -> resume -> manual trigger -> delete
闭环，最终证据为 `2 passed in 8.3s`，路径为
`/tmp/crypto-alert-real-monitor-e2e-20260719-continue-3`，并通过 axe、DOM、overflow、
console、request failure 和 5xx 门禁。该结果只关闭 Monitor 的本地真实 UI slice，
不关闭 hosted Agent Server、licensed durability 或 M1-M6 全量生产门禁。

真实手动触发随后产生一条成功 Task（1 Snapshot、16 WebEvidence、1 Decision、1
committed ArtifactVersion、8 Domain Events）和一条可审计的 Tavily
`provider_unavailable/TimeoutError` RED；两者都保留在 PostgreSQL，失败没有被转成
成功。当前仍有两个 G0 质量阻断项：历史搜索结果的资产/宏观相关性硬门禁，以及
未实现 Monitor condition evaluator 的 fail-closed admission。V2 仍为
`PARTIAL`，`Production Ready: NO`。

G0.1 入口审计另外将 `tools/v2/start_integration_stack.sh` 的默认 profile 限定为
唯一 `backend/langgraph.json`；`langgraph.multi-interrupt.json` 只能由显式
`task8-multi-interrupt-qa` probe 使用。该隔离不等同于 licensed Agent Server
版本兼容或持久化重启证明。

2026-07-18 的 provider 审计确认：`ddgs==9.14.3` 未指定 backend 时使用
`backend="auto"` 的自动元搜索，而旧实现却把所有结果持久化为
`source=duckduckgo`。因此，本文及早期 implementation note 中所有基于该
auto 路径的“真实 DuckDuckGo”表述均被本节撤销；真实结果与 citation 仍然
有效，但 provider 身份必须更正为 `ddgs_metasearch`。当前代码显式传入
`backend="auto"`，旧配置值 `duckduckgo` 会 fail closed，Alembic `0019` 已
可逆修复历史 Evidence、Run、Artifact 和 Domain Event provenance。approved
`builtin_web_search` 仍为生产默认值，当前用户 endpoint 的该能力仍是 RED。
本轮完整 RED、修复、迁移、故障注入和真实浏览器证据见
`docs/v2/implementation/2026-07-18-readiness-provider-integrity-and-real-regression.md`。

2026-07-19 Task 8 证据复核同时撤销早期 overall-GREEN、默认
licensed tests “fail-closed”及已完成“zero-skip acceptance”的表述。当前开发
矩阵为 `langgraph-api 0.11.1` / `langgraph 1.2.9` /
`langchain-protocol 0.0.18`；licensed image verifier 仍固定
`langgraph-api 0.11.0`。开发环境 root `checkpoints` channel 为 RED：上游完整
`StateSnapshot` shape 到达只接受 `id/parent_id/step/source` 的 Protocol
envelope 边界后被丢弃，official `getState` fallback 仅用于诊断，不能计为
channel、replay 或 acceptance 通过。`state.fork` 仍返回 `unknown_command`；
Product-owned Runs API checkpoint fork 是 fallback，不是 Protocol capability。
两份 compatibility exception 均为 `PROPOSED / NOT ACCEPTED`。licensed restart
和 server-effective `durability="exit"` 均为 `UNPROVED`。因此当前总裁决保持
`V2 PARTIAL / Production Ready: NO`。详细边界见：

- `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-checkpoints.md`
- `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-state-fork.md`
- `docs/v2/implementation/2026-07-18-task-08-protocol-persistent-harness.md`

Task 8 outer harness 已在当前未提交工作树中进一步收紧：强制持久 evidence
目录、Compose target/镜像绑定、真实 stop -> URL unavailable -> start ->
recovery、Product Task admission 跨重启绑定、`sync/exit` 双 manifest、严格
zero-skip JUnit、完整 expected-RED 后续执行及证据 SHA manifest。fresh 静态
门禁为 `14 passed`，Agent/Protocol/graph/durability focused 为
`95 passed, 8 skipped`；这些 skip 继续按未证明处理。当前进程没有 licensed
credential，且既有 Product PostgreSQL 占用同名 Compose project，因此未执行
licensed `0.11.0` live harness，不能把实现完成写成 restart/durability GREEN。
本轮随后完整 backend 为 `935 passed, 174 skipped, 1 warning`，root
structure/deployment `exit 0`，frontend `390 passed` 且 typecheck/lint/build
通过。Work/Home/Runs/Inbox/Library/Settings 在 Desktop `1280x720` 与 Pixel 7
`412x915` 的只读真实浏览器扫描均无横向溢出、文本裁切、重复 ID、未命名控件、
raw JSON 或 console warning/error。现有 Agent/Worker 是本轮改动前启动的
`--no-reload` 进程，因此这些 UI 结果不能证明最新 Task 8 backend 已运行，亦不
改变 licensed/hosted 门禁结论。

2026-07-19 后续主流程审计又关闭三个本地实现缺口，但没有形成 hosted 或
licensed 证明。Canonical Graph 现在通过官方 `get_stream_writer()` 发送严格、
版本化且 payload-bounded 的 `task_progress/artifact/evidence/usage/notification/
quality` custom events；Runs API submit/fork/resume 明确请求 `updates+custom`，
Product worker 仍只消费 `updates` 形成 durable projection；前端使用官方
`useChannel` 订阅六个 named custom channels，并以 strict Zod、Run scope、稳定
event ID 去重后映射成人类可读进度。in-process Graph `stream_mode=custom` 与实验性
`astream_events(version="v3")` 本地 contract 均通过，但当前保留的 no-reload
Agent 进程早于该修改，且没有 licensed/hosted live custom replay 证据。

ADR 0010 记录 Task 13 已触发 ADR 0009 的 Deep Agents reintroduction 条件；
`deepagents==0.6.12` 受限 factory foundation 已通过 deny-all filesystem、禁用
general-purpose subagent、唯一 verified-source subagent、structured output、调用
预算和显式 LangChain fallback 二选一合约。该 harness 现已作为唯一 canonical
`StateGraph` 的 `deep_research` 分支接入同一个 Product Task/Command/Worker/Agent
Server 生命周期；成功结果持久化为独立 `deep_research_report` ArtifactVersion 和
WebEvidence，不创建交易 Decision。Work、Run Detail、Runs、Library 和 Artifact
Detail 已消费 typed report/source/citation projection，本地 Desktop/Pixel 7 fixture
验证了页面离开后按同一 Task 重读、axe/DOM/overflow/raw JSON 门禁。该证据没有调用
真实外部模型或 Search provider，也没有 licensed/hosted restart，因此 Task 13 仍是
`partial`，不能称为生产 Deep Research 完成。后续真实页面复核发现历史
`waiting_human` Run 与当前 Task authority 被混在一个字段中；Run Detail 现已拆分为
immutable `run`、current `task`、selected `run_projection` 和 server-owned
`is_current_run`。旧审核不再无限轮询、显示取消或冒充可操作审核，并能进入当前成功
Task 的完整报告。Home 也按 `exchange_native/web_search_verified/
controlled_dependency` 如实披露来源，不再把降级数据称为交易所原生行情。

本日后续真实 Tavily runner 已补齐 Task 13 主链的临时外部 provider 证据：同一
隔离 PostgreSQL、官方开发 Agent Server、统一 Worker 和 production Next build
下，Desktop 与 Pixel 7 均完成 admission -> Tavily Evidence -> Deep Agents draft
-> waiting_human reload -> full-report edit -> second review -> approve -> committed
ArtifactVersion -> terminal reload，Playwright `2 passed, 0 skipped`，数据库每个
Task 有 24 条 Tavily Evidence、8 个唯一内容哈希、8 个唯一 URL 哈希和一个 committed
ArtifactVersion。该 credential 只在 runner 进程中注入，没有写入配置或仓库；默认
`builtin_web_search` 仍未被替换。该证据关闭的是本地临时 Tavily real-provider
slice，不是 hosted/licensed Agent Server、外部 LangSmith/Langfuse delivery 或
Task 13/M1-M6 全量生产交付，当前总裁决仍为 `V2 PARTIAL / Production Ready: NO`。

同日随后又完成了中央 Market Analysis 真实主链。初次 Desktop/Pixel 7 执行因空白
proxy 环境变量被保留为 `""` 而在 `httpx.Client` 构造期真实失败；`Settings` 现将
空白 optional string/secret 归一化为 `None`，且 Tavily 被选中时要求非空凭据。保留
RED 后，隔离 PostgreSQL、官方 development Agent Server、统一 Worker、真实 OKX、
真实 Tavily 和 `gpt-5.5` 的当前源码重跑为 `2 passed (1.4m), 0 skipped`。每个
成功 Task 有 1 个 OKX snapshot、8 条唯一 Tavily Evidence、1 个 committed
ArtifactVersion、1 个 `no_trade` Decision 和完整 7 段 Domain Event 谱系；Desktop/
Pixel 7 均通过 axe、DOM、overflow、raw JSON、console/page/network 门禁。该结果关闭
本地 Tavily Market Analysis slice，但仍不是默认 built-in Search、licensed/hosted
durability、OIDC/HTTPS 或生产发布证明。

Deep Research 专用报告审核现已进入同一个 canonical `StateGraph`：executor 只
生成 typed draft，`review_policy=required` 通过官方 `interrupt()` 暂停，Product
InterruptPause/Inbox/Work 以 discriminated union 展示 approve、reject 和完整报告
edit；edit 必须再次进入审核，approve 才能提交 ArtifactVersion，reject 只保留
blocked draft 且不创建交易 Decision 或 `artifact.committed` 事件。本地 controlled
浏览器后半链在 Desktop 执行 edit/re-review/approve，在 Pixel 7 执行 reject，结果为
`2 passed (16.0s)`。Seeder 直接向开发 Runtime 注入预构造 draft 并建立 Product
waiting-human 投影，因此该结果不覆盖 Product 初始 admission、Deep Agent、真实
模型/Search 或证据采集；仓库也没有保留可哈希的 Playwright 回执，不能称为真实
Provider 全链、licensed durability、hosted acceptance 或 release attestation。

## 1. 判定口径与总裁决

- `done`：Task 14 规定的代码、测试、真实环境证明、candidate/review/attestation 均存在且可核验。
- `partial`：已有实质代码或测试切片，但 Task 的必需范围、真实证明或实施协议尚未闭合。
- `blocked`：已有实质实现，但当前外部能力或环境使关键验收链无法继续成立。
- `not_started`：没有足以构成该 Task 交付切片的实现与测试证据。

当前 16 个计划项（Task 0、0B、1-14）的裁决为：`done=0`、`partial=16`、`blocked=0`、`not_started=0`。**V2 仍不是 production ready。** G0.1 canonical audit、G0.2 本地 zero-mock 主流程和 G0.3 canonical framework convergence 已形成 fresh 本地证据；唯一生产 Graph、官方 `create_agent`/structured output/HITL/Agent Server/`@langchain/react` 边界已经锁定，孤儿手写 runtime 已删除。Task 13 依据 ADR 0010 锁定受限 `deepagents==0.6.12`，当前已推进到 canonical Graph、Product background lifecycle、Scheduled Monitor/Cron、本地 retention/export/deletion、独立 report Artifact、typed frontend 和本地断开重连 Playwright；真实外部 deletion receipts、licensed durability 以及 Task 13 的 Outcome、memory、完整 entitlement/usage/webhook 范围仍未完成。当前源码在显式本地 HTTP proxy 与 `SEARCH_PROVIDER=ddgs_metasearch` 条件下，production-auth local-proof Desktop/Pixel 7 真实 Product 主流程为 `2 passed (2.5m)`，真实 Library/Artifact detail 为 `2 passed (12.7s)`；approved `builtin_web_search` 在用户 endpoint 上仍为 `RED / EXTERNAL DEPENDENCY`。M1-M5 已有真实产品切片，但 Task 0-14 的正式 review/attestation 均未闭合。Hosted OIDC/HTTPS、多主体浏览器状态、licensed persistent Agent Server restart、真实 LangSmith/Langfuse 双端 trace、真实通知回执、load/SLO、安全供应链和 release attestation 仍未证明；本地、fixture 或 skip 证据不能替代这些门禁。

## 2. Task 0-14 状态矩阵

| Task | 状态 | 已存在的代码/测试证据 | 缺失项与裁决依据 |
|---|---|---|---|
| 0 Immutable Normative Baseline | `partial` | 13/14 及 V2 ADR 已在历史提交中形成；本 recovery candidate 的父提交为 `9ac296f`。 | `docs/v2/normative-baseline.json`、三段有序 review/attestation、release candidate 干净树证明均不存在；recovery checkpoint 不能替代 Task 0 完成条件。 |
| 0B Requirement Registry | `partial` | `build_requirement_registry.py`、`verify_requirements.py`、`transition_normative_baseline.py` 及 16 项 synthetic/temporary-Git contract tests 已存在；工具严格要求显式映射、immutable candidate、owner 与 pre-RED receipt。 | `normative-baseline.json`、`requirements-registry.yaml`、正式 implementation note、reviewed immutable candidate 和 pre-RED receipts 不存在；当前 dirty 未提交工作树不能生成或回填这些治理证据。 |
| 1 Dependency/Agent Server Bootstrap | `partial` | 精确依赖锁、uv source 模式的唯一 `graph_factory`、authenticated `probe_agent_server.sh`、Agent Server base image digest lock 与隔离的 Agent PostgreSQL/Redis Compose 已存在。Probe 已真实通过 401/403/200 resource authorization 和 assistant registration；官方 `langgraph build` 产物已验证不包含 CLI/inmem/pytest 和 `.env`/tests/cache。当前 development matrix 为 `langgraph-api 0.11.1` / `langgraph 1.2.9` / Protocol `0.0.18`；checkpoint GET 与 Product-owned fork 已在 Desktop/Pixel 7 fresh 通过，Graph factory ambient-runtime 防泄漏契约也已通过。 | Licensed image verifier 仍固定 `langgraph-api 0.11.0`，且 licensed Runtime 未形成 readiness/restart 证据。Development checkpoint GET 只是 official state read；root `checkpoints` Protocol envelope 仍为 RED，不能由 `getState` fallback 或 Product fork 替代。`versions.json`、完整实施说明和最终 attestation 仍缺失；生产持久化、`durability="exit"`、HA 均未证明。 |
| 2 Actor/Auth/Tenant Isolation | `partial` | M4 将用户身份固定为规范化 OIDC `issuer + subject`；Auth.js 忽略 profile 中的 tenant/workspace/role/permission authority，并在 `iss` 与配置 issuer 不一致时 fail closed。浏览器只提交 opaque `context_id`，scoped JWT 不携带租户、workspace、角色或权限 authority；Product API 与 Agent Server 每次用户请求都从 Product PostgreSQL 解析 active membership，撤权后旧 token 立即失效。provisioning 持久化精确 `(tenant, identity_issuer, external_subject)`，worker/health-check 使用独立 service-token purpose。Agent Store namespace 被重写到 tenant/workspace/private-purpose 边界，principal 由 issuer+subject 不可逆派生，防止不同 issuer 的同 subject 碰撞且不暴露原始 subject；真实 PostgreSQL 已通过双用户/双租户 list/detail/respond/cancel/fork/revoke 与同 workspace 两用户 Store 隔离矩阵。原有 environment、loopback bootstrap、liveness/readiness fail-closed contracts 继续存在。 | **真实 hosted OIDC provider、trusted HTTPS、由真实登录生成的 owner/peer/cross-tenant/revoked browser storage states 均未证明**；`cross-tenant-security.spec.ts` 因缺 hosted credentials 仍是 skip-gated executable requirement，不是通过证据。hosted context-switch late-response、零 mock 浏览器矩阵、operator audit、实施说明与 review/attestation 仍缺失。 |
| 3 Domain/Evidence/Risk | `partial` | typed domain、evidence/risk policy、golden cases 及对应单元/contract coverage 均存在，并包含在通过的 backend 全量 suite 中。 | 缺 Task 0B registry/receipt、可核验 RED、实施说明和双 review/attestation；按 Task 14 协议不能判 `done`。 |
| 4 OKX/Web Search Providers | `partial` | OKX/search/provider typed code、parser/contracts 与 async readiness 已存在。OKX 现逐行验证 `instId` 并拒绝负 candle volume；provider retry 配置在构造期拒绝零/负预算。当前用户 endpoint 的普通模型能力可用，但 built-in Web Search 没有可验证 server-tool citation。保留该 RED 后，显式本地 proxy + `SEARCH_PROVIDER=ddgs_metasearch` 的当前源码真实主流程 Desktop/Pixel 7 为 `2 passed (2.5m)`；临时 caller-injected Tavily runner 已分别完成 Deep Research `2 passed (6.3m)` 和真实 OKX/Tavily Market Analysis `2 passed (1.4m)`。后者每个任务有 1 个 OKX snapshot、8 条唯一 Tavily Evidence、1 个 committed ArtifactVersion 和 1 个 Decision。 | Tavily 仅以一次性进程注入 credential 证明本地 real-provider slices，未写入配置；approved built-in provider、默认 Compose provider 切换、hosted egress、完整 failure matrix 和 hosted attestation 仍未关闭。 |
| 5 Agent Factories/Structured Output | `partial` | ADR 0009 继续固定现有 market/research 为两个轻量 LangChain `create_agent` factory；ADR 0010 只为 Task 13 增加唯一受限 `create_deep_agent` selector。三条官方 factory 路径均使用 `ToolStrategy` typed structured output，且每次 Deep Research 配置只能在 Deep Agents 与 LangChain fallback 中二选一；唯一 production Graph 仍为 `graph_factory`。孤儿 `graph/nodes` 手写 runtime 已删除。Deep Agents 的 filesystem deny-all、默认 subagent 禁用、唯一 verified-source subagent、模型/工具/委派调用预算、typed citation index 和禁止 raw URL/provider payload 合约已通过；受控模型还真实执行了官方 Deep Agent `task -> verified-source-researcher -> verified_web_search` 委派。 | 委派证明使用受控 fake chat model/search tool，不是外部模型/Search provider 成功；完整 hosted wire permission、licensed restart 及 Protocol/Trace/log/browser canary 仍缺失。本地 factory/runtime contract 不能替代生产运行时验收。 |
| 6 Canonical Graph/HITL | `partial` | canonical graph 使用官方 `interrupt()` 和 `Command(resume=...)`，root artifact review 支持 approve/reject/edit；edit 会重新执行 evidence/risk/review，reject 产生严格 `blocked` terminal output。server-owned `required` policy 不能被客户端降级，interrupt 前没有非幂等副作用。M3 adapter 使用官方 current ThreadState 收集同一 superstep 的 root/nested active interrupts，只恢复未消费成员，并在 current head 上一次提交 response map。独立 `multi_interrupt_fixture` 在 official Agent Server 中真实生成两个成员，Desktop/Pixel 7 均完成 resume。Canonical Graph 还通过官方 `get_stream_writer()` 生成六类 strict custom event，本地 `stream_mode=custom` 与 `astream_events(version="v3")` contract 通过。Task 13 以 `task_type` 在同一 `StateGraph` 内路由到受限异步 `run_deep_research` 节点，并复用 canonical review node。Deep Research executor 只产出 draft；required review 支持 approve、reject、完整 typed report edit 和强制二次审核，来源、harness、model audit 与 artifact status 保持不可编辑。 | Controlled 浏览器只证明注入 draft 后的 Product respond/Worker/official resume/terminal 半链；没有真实 Provider/Deep Agent 前半链、pending reload、双设备 first-writer、stale checkpoint 或 licensed restart/replay 证明。M3 multi graph 仍是 QA fixture，不证明真实 nested subagent review 已进入主图。 |
| 7 Product PostgreSQL/Outbox | `partial` | Alembic 0001-0022、SQLAlchemy models/repository/UoW、task projection、command/notification/monitor/lifecycle workers 及真实 PostgreSQL integration tests 已存在。0019 可逆修正 DDGS provenance；0022 增加 actor-scoped lifecycle policy/export/deletion。fresh isolated PostgreSQL 完整 integration 现为 `220 passed, 7 skipped`；它聚合覆盖 PostgreSQL interrupt pause/response projection、Deep Research report、通知、Scheduled Monitor、生命周期 export/deletion、投影和真实 Worker SIGKILL recovery。测试 actor cleanup 已按所有 RESTRICT 依赖显式排序，未关闭外键或使用 `TRUNCATE CASCADE`。Command Dispatcher 的 submit/resume/fork reconcile、resume create 和 Run get 均有统一远端 deadline，超时保持 typed indeterminate/reconciliation，不增加第二套 retry loop。 | 7 个 licensed durability 用例仍明确 skip/未证明；本地官方 development Runtime 和 controlled SIGKILL 不能证明 licensed persistent Agent Server 进程/数据库重启后的 stream history、checkpoint durability、生产 DB role isolation、HA 或 hosted SLO。 |
| 8 Product APIs/Agent Integration | `partial` | Product API 已提供 create/list/get/cancel_task/cancel_run/retry、single respond、aggregate `respond-all`、owner-scoped Inbox、Run detail、Artifact library、owner-scoped Artifact detail/version lineage、owner-scoped Feedback 和 checkpoint fork。`TaskView` 还针对 selected/latest Run 返回 payload-free、scope-bound 的 durable stage history 与 paired Product/official cursor；刷新、SSE 断线、终态和历史 Run 的前端持久化基线已实现，official `useStream` 保持 live enhancement。`cancel_run` 通过 Product durable command 只取消选定 Run，并允许后续 Retry；Feedback 通过 `0013` 持久化、同 key 重放并拒绝同一 Run 的第二次冲突写入。真实 PostgreSQL 已证明跨 owner 拒绝、Run terminal projection、stage-history scope、feedback Artifact Version linkage 和 `retry_of_run_id` 新 Run。官方 SDK submit 的缺失 Run 幂等语义已明确记录，Product 只宣称 at-most-once reconciliation。Fresh official-stream Desktop/Pixel 7 已证明 active stage、同一 Task/Run 绑定、reload、official Agent reads 和进入真实 HITL pause。Task 8 已有 version-locked route/Protocol/SDK contracts、官方 JS probe 和 skip-gated licensed `prepare -> restart -> verify` harness；QA image 只显式增加 multi-interrupt fixture，生产 image verifier 仍要求唯一 canonical Graph。 | Task 8 不是 GREEN。Development root `checkpoints` channel 未交付轻量 envelope，official `getState` fallback 仅诊断；`state.fork` 返回 `unknown_command`，Product Runs API fork 不构成 Protocol 通过。两项 exception 均未 accepted。默认 licensed skip 不是 fail-closed acceptance，且未完成 zero-skip outer harness；licensed `0.11.0` restart、同一 Thread/Checkpoint/Interrupt/history/`since` replay 与 server-effective `durability="exit"` 均为 **RED / UNPROVED**。Hosted OIDC/HTTPS 与 Task 8 review/attestation 也未闭合。 |
| 9 Observability | `partial` | 官方 LangSmith `Client`/`LangChainTracer` 与 Langfuse `Langfuse`/`CallbackHandler` 根级装配、tenant sampling、PII/secret redaction、provider attempt correlation 和结构化 delivery-failure event 已存在。Provider-isolated bootstrap fail-open 后，又以随机 loopback HTTP 实际证明 LangSmith `/runs/batch` 503->204 与 Langfuse OTLP protobuf 503->200：业务 Runnable 结果不变、真实官方 trace 出口可见、恢复后新 trace 可投递。Langfuse RED 发现并修复 OTEL exporter 响应日志 secret 泄漏与 4.14 `mask(data=...)` 签名不兼容；官方 transport 文件连续三轮均 `4 passed`，combined observability/security 为 `43 passed`。Canonical `graph_factory` 只把新建的 root callbacks 与规范化 metadata/tags 放入 Graph 默认配置；调用期 `configurable`、checkpoint/run/thread 坐标、checkpointer 和私有 Runtime 均不得进入 compiled Pregel defaults，ambient regression 已覆盖。Product Run delivery intent、PostgreSQL 状态、Worker hosted read-back verifier 和前端 completion scope 已接入。 | 当前只有本地官方 SDK transport/root assembly 与 completion-state contract，不是 fresh hosted LangSmith/Langfuse 双端 trace。SDK background error 仍只能记录 `correlation_id=unknown`；缺同一真实 Product Run 的双端 hosted query/recovery、贯穿 BFF/Task/official Run/provider/artifact 的 full correlation、bounded Agent process flush/shutdown、真实 hosted retention/query、生产告警和 attestation。 |
| 10 Frontend Runtime/BFF/View Models | `partial` | Next.js/Auth.js、same-origin agent/product BFF、`@langchain/react` thread attachment、typed schemas/view models 与 production environment fail-closed guard 已存在。Root `useStream` 通过官方 `useChannel` 订阅六个 named custom channels；strict Zod、event ID 去重、Product Run scope 和 bounded human projection 拒绝 raw/unknown payload。Deep Research 新增 strict submission/task/report/source/citation schemas、typed review interrupt union 和同源 BFF route，Run/Artifact detail 按 `task_type/artifact_type` 选择 typed projection；official stream 只发现受限 `verified-source-researcher`。 | 本轮研究执行证明包含 fixture report projection 和 controlled post-draft Product chain，不是 live external model/Search stream。真实 production/hosted OIDC、trusted HTTPS、多主体 storage states、完整 Protocol v2 replay 与 Task 10 attestation 未闭合。 |
| 11 Product UI | `partial` | `/work`、`/home`、`/runs`、真实 Run detail、真实 Library、owner-scoped Artifact version detail、真实 Run Detail Feedback、`/inbox` 和 Settings 产品面、响应式样式及 Playwright 已存在。Work 现在以 segmented control 提交市场分析或 Deep Research；研究报告以章节、finding citation、风险提示、证据缺口和可验证来源渲染，Runs/Library/Artifact Detail 均可识别研究任务。Work/Inbox 现在还提供专用 Deep Research approve/reject/full-report edit UI。Desktop edit/re-review/approve 和 Pixel 7 reject 的 controlled 后半链通过 axe、overflow、duplicate ID、accessible-name、raw JSON 和 full-page screenshot 门禁。 | Seeder 注入预构造 draft，因此没有证明真实外部 Provider、初始 admission/dispatch 或每个动作的双视口矩阵；也没有 hosted visual baseline、VoiceOver 人工 artifact 或真实 OIDC 多主体状态。通知真实 Outbox 延迟/回执 E2E 与 canonical nested provider review 仍缺失。 |
| 12 Real E2E/Failure Injection | `partial` | M1-M4 既有 success/cancel/HITL/Inbox/fork 真实本地切片继续有效。历史 failure-injection Product matrix 在 Desktop/Pixel 7 为 `14 passed`；新增 controlled partial-state body 在 Desktop/Pixel 7 为 `2 passed`，临时 Tavily Deep Research full-chain 为 `2 passed (6.3m)`，真实 OKX/Tavily Market Analysis full-chain 为 `2 passed (1.4m)`。后者覆盖 admission、真实行情/Search、双模型 structured output、Evidence/risk gates、ArtifactVersion/Decision、数据库谱系及双视口 DOM/axe/visual/network 门禁。当前 discovery 为 20 个 failure-injection project-test instances，但没有当前全量执行结果，不能合并写成 `16 passed`。Dispatcher 已有 pre/post remote-create fencing、取消竞态、reconcile-only 与 compensating cancel 的真实 PostgreSQL contracts；Notification Worker 已有 expired `sending` lease -> `unknown` 恢复 contract。 | 现存 Playwright report 的 20 个 failure-injection 实例全部是 skip/discovery 产物，不是通过证据。Tavily 成功只证明本地临时 provider slices，不是完整外部 OKX/Search/model outage matrix；真实进程 kill、真实通知回执、licensed restart、hosted OIDC/HTTPS 与完整发布矩阵仍缺失。 |
| 13 Deep Research/Lifecycle | `partial` | ADR 0010、`deepagents==0.6.12`、受限官方 Deep Agents/显式 LangChain fallback、typed citation ledger/report 已存在。`POST /api/v2/deep-research` 使用既有 Product admission、TaskCommand、Worker、同一 Assistant/Thread/Graph；executor draft 进入 canonical report HITL，approve 才提交独立 `deep_research_report` ArtifactVersion。Scheduled Monitor/Cron 已进入同一 Graph/Worker 边界。Task 13 的 Product-owned retention/export/deletion vertical slice 已增加可逆 `0022`、严格 API/BFF、统一 Lifecycle Worker、Settings UI、owner-scoped reload/rejoin 和隔离 PostgreSQL Desktop/Pixel 7 零拦截 Playwright `4 passed (10.0s)`；真实导出 manifest/bundle hash 与 deletion `pending_external` 数据库状态均已核验。 | Deep Research Tavily full-chain 仍是一次性本地 credential + development Agent Server 证据；默认 built-in Search 仍 RED。Data lifecycle 只完成 local Product slice，外部 deletion adapters/receipts、checkpoint/Store/object storage/search/LangSmith/Langfuse/log/backup 删除仍未交付。Outcome、memory、完整 entitlement/usage、webhook、licensed restart、hosted OIDC/HTTPS 及 candidate/review/attestation 仍不存在，因此不能判 `done`。 |
| 14 Production Gates/Legacy Removal | `partial` | Dockerfile/Compose 已固定 Python、Node、PostgreSQL、pgvector、Redis 和 Agent Server digest；官方 Agent image 使用 uv.lock、排除 dev/inmem 与敏感构建上下文，API 只发布到 loopback。独立 Product/Agent PostgreSQL、Redis、migrate/bootstrap、custom app/auth 均已执行到 licensed Runtime 校验阶段。G0.3 已删除孤儿手写 Agent runtime；ADR 0010 只为 Task 13 重新引入受限 Deep Agents 稳定依赖并增加防回归契约。Task 14 的 protocol secret test 与 local backup/restore、key rotation、migration rollback、health-load/SLO foundation 均存在。 | 有效 LangSmith/license credential、licensed durable restart、production packaging/HTTPS、完整 hosted security/release gate、真实 Product-flow SLO、PITR/failover、签名 SBOM、requirement evidence、独立 attestation 均不存在；V1 parity/removal 均不存在。所有 local-only 结果均不能解释为 release 或 production-ready 证明。 |

## 3. Fresh 测试与运行证据

截至本次审计，当前工作树的 fresh 本地命令结果如下；所有 skip 都按“未证明”处理。表中明确标为“最近一次”的外部运行没有在本次安全边界下重新执行：

| 范围 | 结果 | 解释 |
|---|---|---|
| Backend `cd backend && uv run pytest -q` | `957 passed, 177 skipped, 1 warning` | 当前完整 V2 hermetic/local backend suite 为 green；177 个 skip 仍按未证明处理。显式 PostgreSQL 与 worker process 证明单列如下；skip 不能用来宣称 hosted identity、durability 或生产门禁完成。唯一 warning 是 Starlette/httpx TestClient dependency deprecation。 |
| Root migration/structure/deployment suite | `1199 passed, 51 warnings` | Compose、dependency closure、migration/deployment tools、formal docs、frontend routes、Playwright discovery 和既有 root product contracts 全量通过。warnings 为 Starlette/httpx 与 pathspec deprecation，不是跳过。 |
| Auth/deployment focused contracts | `包含在 backend/root 全量 suite；额外 recursive-ignore 回归 2 passed` | Agent readiness 独立 probe principal、hosted verifier fail-closed、loopback/IPv6/空白身份、liveness/readiness 分离、递归 ignore 与 Compose topology 已纳入全量 suites；本次不另造不可复现的聚焦总数。 |
| PostgreSQL integration | fresh isolated database `220 passed, 7 skipped` | 独立临时 PostgreSQL 从 Alembic head 运行完整 `tests/integration`。聚合证据覆盖 canonical Graph、PostgreSQL interrupt pause/response projection、Deep Research、通知、Scheduled Monitor、Task 13 lifecycle export/deletion、租户范围、progressive events 和真实 Worker SIGKILL recovery。7 个 licensed durability 用例明确未证明。 |
| Real OKX typed snapshot | 仅在显式本地 HTTP proxy 下成功 | 证明 typed OKX adapter 能处理真实交易所数据；同时证明当前网络环境对该 proxy 有运行依赖，不能推广为 direct/hosted 可用性。 |
| Real DDGS metasearch | production-auth local-proof Desktop `1 passed (1.4m)`、Pixel 7 `1 passed (1.1m)`；合计 `2 passed (2.5m)` | 显式本地 proxy + `SEARCH_PROVIDER=ddgs_metasearch` 取得真实 OKX、公开 HTTPS Web Evidence、模型 Structured Output、2 个 committed Artifact、16 条 `ddgs-metasearch-v1` Evidence 和 4 个模型审计。它不关闭 approved built-in gate。 |
| Real Tavily | Deep Research `2 passed (6.3m)`；Market Analysis `2 passed (1.4m)` | caller-injected credential 下，Desktop/Pixel 7 已分别完成 Deep Research required-review full chain，以及真实 OKX -> Tavily -> `gpt-5.5` -> Evidence/risk -> ArtifactVersion/Decision 的交易分析主链。Market Analysis 每个成功 Task 有 1 个 OKX snapshot、8 条唯一 Tavily Evidence、1 个 committed ArtifactVersion、1 个 `no_trade` Decision 和 7 个 Domain Events。credential 未持久化；默认 `builtin_web_search`、hosted egress、licensed/hosted durability 仍未证明。 |
| Frontend static/unit/build | lint、typecheck 和 production build passed；unit `416 passed` | Product client/BFF、Deep Research submission/report/citation/review projection、Work/Inbox/Run/Artifact/Feedback/Home source disclosure、current/history Run authority、named custom channels、durable stage merge 和 identity/context/HITL contracts 已纳入 unit；证明当前 frontend/BFF/view-model 可构建，不等于真实 hosted OIDC、trusted HTTPS 或多主体 browser behavior。 |
| Deep Research Product UI | fixture Desktop/Pixel 7 `2 passed`；临时 Tavily full-chain `2 passed (6.3m)` | Persisted `deep_research_report` 在离开页面后按同一 Task 重读；两个 viewport 均通过 axe、horizontal overflow、duplicate ID、accessible-name、raw JSON、source deep-scroll 和 full-page screenshot 门禁。Tavily full-chain 覆盖真实外部 Search 和 initial admission，但仍是本地 development Agent Server 与一次性 credential，不是 hosted/licensed production acceptance。 |
| Controlled Deep Research HITL | Desktop edit/re-review/approve + Pixel 7 reject `2 passed (16.0s)` | 使用 isolated PostgreSQL、current-source development Agent Server、统一 Worker 和 production Next build，真实经过 Product BFF/API、持久化与 official resume。Seeder 以 `update_state` 注入 controlled draft 并手工建立 waiting-human 投影，故 initial admission/dispatch、Deep Agent、模型/Search 和真实证据采集未被证明；没有 retained machine-readable receipt。 |
| Current-source Run Detail read proof | local development `8124 -> 3002`; Desktop/Pixel 7 DOM green；fixture Playwright `6 passed` | 真实 persisted old waiting Run 通过 real BFF 渲染并进入 latest succeeded Task，显示 8 条 Evidence、数据溯源和 2 条模型审计；无 overflow、clipping、duplicate ID、unnamed control、raw JSON 或 current-page console error。该 proof 使用占位模型且没有新建 Run，只证明 Product read/render，不是 provider、licensed、hosted 或 production acceptance。 |
| Playwright profile discovery | contract `32 passed`；fixture `38 tests / 4 files` discovered | 当前默认 profile 只发现 route fixtures；failure-injection 当前 discovery 为 `20 / 2 files`；`controlled-deep-research-hitl` 被精确收集、npm command 和缺失环境门禁覆盖。该结果只来自 `--list`，不能代替浏览器 body 通过。 |
| Strict/controlled real Playwright | 当前源码真实 provider mainline Desktop/Pixel `2 passed (2.5m)`；真实 Library/Artifact detail Desktop/Pixel `2 passed (12.7s)`；此前 durable cancel、Inbox、HITL、Fork 和 official-stream 独立切片保持各自历史证据 | 最新四个测试使用 production-auth Product/Agent、真实 Product API/PostgreSQL/统一 Worker/canonical Graph/official local Agent Server、OKX/DDGS/model，未注入 Product route。页面与截图通过 raw JSON、overflow、clipped/unnamed control、axe、console/page/network error 门禁。Agent Server 仍是 in-memory development Runtime，不是 licensed durability 或 hosted acceptance。 |
| Task 8 Protocol/persistence harness | 历史 focused `26 passed, 5 skipped`；历史 adjacent Product/Agent/Protocol/HITL `193 passed, 5 skipped`；development Server OpenAPI coexistence `1 passed`；当前 root checkpoint live probe `RED` | 历史计数保留为 harness/contract 证据，不是 Task 8 GREEN。Development `0.11.1` + LangGraph `1.2.9` + Protocol `0.0.18` 未产出轻量 root checkpoint envelope，`getState` fallback 只允许诊断；`state.fork` 为 `unknown_command` 且 exception 未 accepted。Licensed verifier `0.11.0` 未完成 zero-skip restart；4 个 licensed tests、持久 replay 和 `durability="exit"` 均未证明。 |
| Hosted OIDC/HTTPS security browser gate | 未通过；credential-gated skip | 缺真实 hosted OIDC login storage states 与 trusted HTTPS deployment；owner、same-tenant peer、cross-tenant、revoked-user 的 zero-mock respond/cancel/fork 以及 late old-context response 均保持 RED/未证明。 |

## 4. 真实外部证据限制

- 开发 probe 与 M4 fork proof 仍使用 official development Agent Server。该 in-memory Server 在 backend hot reload 后曾丢失旧 Thread，最终 fork proof 使用 fresh stable server；这正是**licensed persistent Agent Server restart/recovery 尚未证明**的边界。部署镜像虽由官方 `langgraph build` 从固定 digest 和 uv.lock 构建并连接独立 Agent PostgreSQL/Redis，但因缺有效 LangSmith/license credential 未形成通过 readiness、restart persistence 或生产 HA 的证据。
- Task 8 development Protocol probe 还保留独立 RED：root `checkpoints` 事件没有形成 Protocol `id/parent_id/step/source` envelope。通过 official `getState` 取得 checkpoint ID 仅支持下游诊断，不证明 channel/replay。`state.fork -> unknown_command` 和 Product-owned checkpoint create 也不能互相替代；两份 compatibility record 均未被接受。
- Product task GET 可以用 `run_id` 选择历史 Product Run；M4 fork 只接受 owner-scoped `source_run_id`，由 Product 端绑定 checkpoint 并通过 durable command 创建 official fork。该本地闭环证明 lineage/admission/worker contracts 可运行，但不证明 Agent Server 重启后 checkpoint 仍可恢复，也不构成完整 Protocol v2 replay/ordering contract。
- 真实 OKX、built-in Web Search RED、DDGS metasearch 诊断和 strict browser 链依赖显式本地 HTTP proxy；未通过该 proxy 的 direct/hosted 网络路径没有成功证明。Tavily 没有有效 key，仍为 unverified。当前用户 endpoint 的 built-in Search 没有形成可接受的 server-tool citation；模型生成但不在 provider citation 集内的 URL 仍不被接受为证据。
- strict real Playwright 已在开发 Runtime 下通过 M1 success chain，证明 Product task、official Thread/Run、真实 provider 和 Artifact 可以成功串联；M2.3 另有 live official Run cancel proof。M2.4/M3 local proof 使用独立 development Product API、同一 PostgreSQL、真实 worker 和官方 dev Agent Server，分别证明 root HITL 与 aggregate root+nested fixture 后半链；M4 又在同类本地拓扑证明 Product-owned historical checkpoint fork、durable command、worker dispatch 与 UI 回到新 `waiting_human` Run。它们都不是目标 hosted OIDC/HTTPS 拓扑、canonical nested provider、provider success 重跑或 licensed restart proof。lease/replay/orphan 与 M4 fork recovery 虽有真实 PostgreSQL contracts，仍没有 licensed Agent Server 重启、真实进程 kill、真实 join 断线或 hosted recovery 证明。
- Backend 与 production frontend 的 environment/auth/readiness 路径均 fail closed。M4 已实现 OIDC issuer/subject、Product DB membership authority、opaque context 与 revoke enforcement；Agent authenticated readiness 继续使用独立 service probe principal并与 socket liveness 分离。但这些本地 contracts 和 PostgreSQL matrix 不是**真实 hosted OIDC、trusted HTTPS、多主体 browser storage state**、secret canary、full correlation 或 release security gate 的替代证据。
- 根目录与 `backend/.dockerignore` 已分别保护 helper 和官方 Agent 构建上下文，Agent context 对任意深度的 `.env*` 递归排除；启动脚本会验证最终镜像的锁定基础层前缀、官方 auth/http/graph 映射、生产依赖与排除项，并在 180 秒启动超时或信号失败后按同一 Compose project 自动清理且保留数据卷。实测 Agent image 不含 `.env`、tests、coverage、cache、CLI 或 inmem Runtime。Compose 使用固定 digest 的 Redis 7，只部署一个官方 Agent HTTP 服务，Product app 挂载在 `/app`；当前缺口是 license 后的完整启动和 restart durability，而不是旧 dual-service/dev-runtime 偏差。
- 当前已有 local-only key rotation、upgrade/rollback、backup/restore、supply-chain/SBOM rehearsal 和 SLO evaluator foundation；仍没有 hosted HTTPS、真实生产数据库角色/PITR/HA、独立生产 projection recovery、真实通知回执、LangSmith/Langfuse 双写、端到端 correlation、生产告警、正式负载/SLO、签名 SBOM 或 release attestation 的 fresh 证据。

## 5. 未完成项与下一条关键路径

M4 已完成本地实现切片和本地 gate，但因 hosted identity/deployment 与 durable restart 证据缺失，裁决保持 `partial`。M5、M6 仍开放，**V2 仍不是 production ready**。

1. 在 trusted HTTPS 部署接入真实 hosted OIDC，以真实登录生成 owner、same-tenant peer、cross-tenant、revoked-user storage states；强制执行 Desktop/Pixel 7 zero-mock list/detail/respond/cancel/fork 与 context-switch late-response 门禁。
2. 使用 licensed persistent Agent Server 重跑 create/respond/cancel/fork，执行 Server/worker 进程 kill 与 restart/recovery，核验 checkpoint、create-intent reconciliation、first-writer 和无重复 official Run；在此之前不得宣称 fork durability 或 M4 `done`。
3. Deep Research 专用 root report HITL 已完成本地 controlled 后半链；下一步从 Product admission 开始执行 approved 真实模型/Search/Deep Agent 到 draft/review/commit 的完整链，并补 pending reload、expiry、双设备 first-writer/stale checkpoint。M3 aggregate 仍需接入 canonical nested provider review，且必须与 fixture proof 分离。
4. 进入 M5：固定 Task admission correlation，完成 LangSmith/Langfuse 出口脱敏、真实双端 trace、独立 outage 降级和 secret canary；补齐通知真实 Outbox 延迟、投递/recovery/unknown 与真实回执 E2E。
5. 进入 M6：完成 hosted HTTPS 与 production packaging、DB role/backup/restore、DR/load/SLO/security、key rotation、upgrade/rollback、SBOM/signing、独立 operator audit/release attestation 和 Task 12-14 release gates；已存在的 Library/Settings/retry 继续接受真实部署回归，不能重复计作完成。

## 6. 2026-07-17 Fresh Execution Update

本轮没有改变总体裁决：V2 仍为 `PARTIAL`，但 G0.2 的本地真实主流程已重新收口为 green。

- 真实稳定栈使用官方 `langgraph dev --no-reload`，避免 backend 测试文件变化触发 Runtime 热重载；Product PostgreSQL 数据保留。
- 真实 Product Playwright Desktop + Pixel 7：`2 passed (2.6m)`。全新任务实际经过 Product API、PostgreSQL、Worker、官方 Agent Server、OKX、Web Search 和模型，并持久化 Artifact/Evidence/Market Snapshot；页面显示中文判断依据和可区分的逐来源摘要。
- 本轮发现并修复了 observability redaction 对官方 `ProxyUser`/Runtime Store 的两个确定性兼容缺陷。focused observability/security `27 passed`；全量 backend `654 passed, 136 skipped, 1 warning`。
- 前端 typecheck/lint/unit/build 全部通过，unit `282 passed`；本地 supply-chain gate `4/4` 扫描通过，Python/前端漏洞均为 0，SBOM 已生成。
- `model/provider/version` 尚未作为独立 Product 审计字段落库；当前证明的是模型输出内容已经进入 committed Artifact 并由前端渲染，而不是完整的模型身份审计证明。
- fixture Playwright 依赖旧的注入式 Work 状态契约，当前失败不计为真实链路失败，也不计为生产通过；严格 zero-mock 主流程结果以本节和执行账本的 fresh evidence 为准。

因此下一步仍按生产价值排序推进：真实 LangSmith/Langfuse 双端 trace、通知回执、licensed persistent Agent Server restart/recovery、hosted OIDC/HTTPS、多主体安全浏览器、生产 DB/DR、load/SLO、key rotation、SBOM signing 和 release attestation。未完成项继续显式保持 open。

## 7. 2026-07-17 Provenance audit follow-up

本轮将模型/provider 身份审计字段补入 canonical Artifact 内容，并完成了真实桌面浏览器展示验证：

- `ArtifactProvenance` 记录 OKX、Web Search provider、citation parser、模型 provider、模型名和安全 endpoint host；旧 Artifact 缺少该字段时仍可读取。
- `app.artifact_versions.content` 的最新成功记录已由 PostgreSQL 直接核验，包含上述字段；前端 `数据溯源` 区块由 schema、view model 和真实 Product 页面共同消费该字段。
- 更新后的真实 Desktop Playwright 明确断言 `数据溯源` 标题，并通过 DOM、axe、无横向溢出、无 unnamed controls、无 console error、无 5xx 和 HTTPS citation 门禁。

## 8. 2026-07-18 Historical provider-revalidation snapshot

> Historical snapshot. Current counts, provider identity and local-regression
> verdict are superseded by sections 0 and 3 and
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`. The approved
> built-in provider RED recorded here remains open.

- Fresh current backend hermetic verification is `848 passed, 164 skipped, 1
  warning`; the warning is the existing Starlette/httpx TestClient deprecation.
- Fresh isolated PostgreSQL verification migrated `0001 -> 0018` and ran the
  complete integration suite: `191 passed, 0 skipped`.
- The latest recorded frontend evidence is `368 passed`, with typecheck, lint and
  production build passing; frontend was not re-run during this backend/provider
  revalidation.
- The controlled partial-state Product browser body is GREEN on Desktop and Pixel
  7 (`2 passed`). It proves failure attribution, retained Evidence and truthful UI
  projection under controlled dependencies only.
- The current `market-analysis-v2` / `web-market-extraction-v2` real success gate
  is `RED / EXTERNAL DEPENDENCY`: with the user-provided model runtime configuration,
  ordinary model capabilities passed, but built-in Web Search produced no invoked
  tool/citation; the Desktop and Pixel 7 Product flows both ended with market and
  fallback search unavailable and no final Artifact.
- The seven real provider/model tests remain unproved unless explicitly enabled;
  no skip, fixture, local-only Runtime or historical proxy run is counted as
  production acceptance.

Current V2 result: `PARTIAL`; `Production Ready: NO`. The next critical path is an
approved Web Search credential/endpoint with reachable egress, followed by a
successful two-viewport Product run; licensed persistent Agent Server restart,
hosted identity and Task 13 lifecycle remain open after that gate.
- 该次 approved-provider Pixel 7 重跑连续三次在 Web Search provider 层失败：
  `MissingProviderCitation` 后 `APITimeoutError`，页面正确 fail closed；后续 DDGS
  local-proof GREEN 不关闭该 approved-provider RED，也不能计为 Pixel 7 生产证据。

因此该历史切片只把 provenance 的本地持久化和 Desktop 视觉链路收口为已证明，
整体 V2 仍保持 `PARTIAL`。Approved-provider Pixel 7 稳定性、hosted OIDC/HTTPS、
licensed Agent Server durability、LangSmith/Langfuse 真实 trace、通知回执和 M6
发布证据仍开放。

## 8. 2026-07-17 Real integration follow-up

- 当前 Product PostgreSQL 拓扑下，`REAL_DATABASE_TESTS=1` 的完整 backend integration suite 为 `160 passed`，不再把通知/outbox、任务投影、HITL、租户隔离、fork lineage 和 reconciliation 仅按 fixture 计数。
- `REAL_PROVIDER_TESTS=1 REAL_MODEL_TESTS=1` 为 `5 passed, 1 skipped`；真实 OKX、built-in Web Search 和模型测试通过，Tavily 因没有配置 `TAVILY_API_KEY` 明确保持 skipped。
- LangSmith/Langfuse 的代码装配已存在并由 contract/security/outage 测试覆盖，但当前安全状态为两个出口均 disabled/unconfigured，因此没有外部 trace 证据，不能写成 M5 完成。
- 更新后的真实 Pixel 7 产品测试连续三次在真实 Web Search provider timeout，系统正确返回 `research_unavailable`；该外部稳定性缺口仍开放，不通过增加 Playwright 重试或 fixture 来掩盖。
- 使用已经由真实 Product/Worker/Agent Server 生成并持久化的 succeeded Run，补做了 Pixel 7 历史运行详情页扫描：`数据溯源` 可见，`overflow=0`、unnamed controls 为 0、axe 为 0、console error 为 0、5xx 为 0。该结果只证明移动端真实 Artifact 渲染，不冒充新任务 provider-success。

## 9. 2026-07-17 Production packaging gate

- 固定 digest 的 backend/frontend 镜像构建、官方 `langgraph build` 和锁定 Agent base image 校验均完成。
- 生产 Compose 曾因未传递 `NOTIFICATION_CREDENTIAL_KEY` 而启动失败，现已把 key/version 明确传给 Agent API 和 Worker；本地 integration 脚本只生成进程级临时 key，不写入仓库或文件。
- 修复后真实 licensed Compose 初始化已到达 Postgres/Redis/runtime migration，但被官方 license 校验阻断：当前没有 `LANGGRAPH_CLOUD_LICENSE_KEY` 或具备 LangGraph Cloud 权限的 `LANGSMITH_API_KEY`。启动脚本已将此条件前置为状态 `78`，避免长时间构建后才失败。
- 因此 M6 的本地 packaging/fail-fast 已收口（deployment topology contract `5 passed`），licensed persistent Agent Server、生产 restart durability、hosted OIDC/HTTPS、真实 LangSmith/Langfuse trace 和发布证明仍不能标记完成。

## 10. 2026-07-17 Endpoint identity audit

当前本地配置的安全摘要为：模型 `gpt-5.5`、endpoint host `xixiapi.cc`、OpenAI key 已配置；本轮没有读取或打印 key。对用户此前提供的 `https://codexai.club/v1` 做 process-only 真实探测时，结构化模型和能力探测都返回 `401 INVALID_API_KEY`。因此没有擅自替换 endpoint，也没有把不匹配的凭据写入项目；codexai 仍是待注入对应 credential 后才能验证的 provider 候选。

## 11. 2026-07-17 Model execution audit

- 新增可选 `ModelExecutionAudit`，并把官方 `create_agent` 返回的
  `usage_metadata`、`response_metadata.id` 和单次模型调用延迟写入
  `Artifact.provenance.model_audits`。
- 研究提取和市场分析分别使用稳定的 prompt version，canonical graph 按
  `research -> analysis` 顺序持久化调用审计；不保存 prompt 原文、完整
  payload、模型内容、Authorization、Cookie 或密钥。
- Product API Zod、view model 和 `数据溯源` 页面已经消费该字段；旧 Artifact
  缺少字段时仍按空列表兼容读取。
- 新增后端 helper/graph contract 与前端 schema/view-model 测试。后端 focused
  `17 passed`，前端全量 unit `284 passed`，typecheck/lint/build 均通过。
- 当时从仓库根目录执行的 root suite 曾暴露 `11 failed` 的 Compose/结构文档/
  测试布局基线漂移；该组失败已在后续基线收敛中修复，当前精确结果见第 13 节。

因此本项已完成，但总体裁决仍为 `V2 = PARTIAL`、`Production Ready = NO`。

## 12. 2026-07-17 Fresh browser and database verification

- 重启 `--no-reload` 本地验收栈后，真实 Product Playwright Desktop 和 Pixel 7
  主流程均通过，各 `1 passed`；两次都实际走 Product API、PostgreSQL、worker、
  官方本地 Agent Server、OKX、built-in Web Search 和模型。
- 两个 viewport 都断言页面出现 `数据溯源`、两种 prompt version、中文判断依据、
  HTTPS 引用、无 raw `<pre>`、无 console error、无 5xx、无 unnamed control、
  无 axe violation、无横向溢出。
- 直接查询最新两个 `app.artifact_versions` 记录：每条 `audit_count=2`，顺序均为
  `research-extraction-v1 -> market-analysis-v1`，真实 token 总数为
  `2109/11942` 和 `2062/12524`。

该项在本地开发拓扑完成 fresh proof；生产授权 Runtime、hosted OIDC/HTTPS、
LangSmith/Langfuse 外部 trace、生产 DB/DR、SLO、密钥轮换、签名 SBOM 和发布证明
仍然开放，整体不能标记 production ready。

当前 Product API 覆盖 `create analysis、run list、get task`，并支持
`Product task GET` 通过 `run_id` 读取历史运行；canonical local path 已包含
官方 HITL、notification 和 feedback 的 Product 侧交互。它们仍不等于 hosted
OIDC/HTTPS、licensed Agent Server restart 或生产发布证明。
`GET /api/v2/tasks/{task_id}` 支持显式 `run_id`；完整 Protocol v2
replay/ordering contract 仍保持开放。

## 13. 2026-07-17 Full local gate convergence

- Root migration/structure/deployment/legacy contracts：`1154 passed`。Compose
  测试会显式注入测试进程占位 license/notification key，不再绕过生产必需配置；
  worker 入口锁定为 `crypto_alert_v2.workers`，新增 Playwright 文件不会被旧精确
  集合误判。
- V2 backend hermetic suite：`658 passed, 136 skipped, 1 warning`。skip 继续按
  未证明处理，不并入真实数据库/provider 证据。
- `REAL_DATABASE_TESTS=1` 的完整 backend integration suite：`160 passed`。
- Frontend typecheck、lint、unit `284 passed`、production build 全部通过。
  UI 内原有四处 `JSON.stringify` 相等/幂等判断已统一替换为稳定 JSON-like
  fingerprint helper，保持请求身份语义，同时满足产品界面禁止 raw JSON 的结构门禁。
- 当前代码 fresh zero-mock Product Playwright：Desktop `1 passed (1.5m)`、
  Pixel 7 `1 passed (1.4m)`；两者都断言模型审计、来源、DOM、axe、console、5xx
  和横向溢出门禁。

本地可执行门禁现已恢复 green；licensed production Agent Server、hosted OIDC/
HTTPS、LangSmith/Langfuse 外部 trace、生产 DR/SLO/密钥轮换/SBOM signing 和
release attestation 仍未完成，因此总体裁决不变。

## 14. 2026-07-17 Strict real HITL terminal projection closure

本轮修复并重新证明了当前本地拓扑的完整真实主流程，但不改变总体裁决：
`V2 = PARTIAL`、`Production Ready = NO`。

- 失败 trace 的直接根因是前端数值 schema 不接受 OKX Decimal 产生的合法科学
  计数法 `3.399075660E-7`。最后一条 Product 响应已经是
  `succeeded/committed`，但严格解析失败使 polling 停止并保留上一帧
  `waiting_human`。同一真实响应在修复后的 production schema 中已回放为有效。
- Product polling 现为 Task 状态唯一权威写入源；官方 `@langchain/react`
  stream 只展示 Agent 执行进度，不再从缺少 run 身份的 `onCompleted` 发起并发
  Product 刷新。同一 Task 的 terminal projection 不允许被旧非终态读回退，retry
  保留为显式重置路径。
- strict real Playwright 已收紧为只接受 `分析完成 + committed + actionable`；
  `blocked`、`failed`、`cancelled` 全部判红。还要求报告引用全部匹配 persisted
  Evidence，并检查 Product/Agent API 4xx/5xx、console/page errors、request
  failures、axe、unnamed controls、页面与证据卡横向溢出、控件裁切和 full-page
  screenshot。
- 最终 Desktop `1 passed (59.1s)`，Task
  `cf9d9539-8822-42e3-8677-8db89eab7545`；最终 Pixel 7
  `1 passed (56.4s)`，Task `d16b5ae2-4b15-4404-90ae-a7f52d61bcd0`。
  两条 Task 均经过真实 OKX、DuckDuckGo、两个官方 Structured Output Agent、
  HITL DOM 决策和恢复 Run，最终各保存 committed Artifact、8 条 Web Evidence、
  2 条模型审计；endpoint host 为 `codexai.club`。
- frontend 当前为 `29 files / 319 tests passed`，typecheck、lint、production
  build 通过；backend hermetic/local 为 `758 passed, 154 skipped`，真实
  PostgreSQL integration 为 `181 passed`；root 依赖缺口修复后，迁移/结构/
  部署套件全部 `1154` 项通过。所有 skip 继续按未证明处理。
- earlier built-in search timeout、`MissingCitedTicker` 和科学计数法解析失败均已
  记录在执行账本，没有通过 fixture、Mock、延长等待或接受 blocked 来掩盖。

当前本地前后端继续运行在 [http://127.0.0.1:3001](http://127.0.0.1:3001)，
但该证据仍基于 `langgraph dev --no-reload`、本机 worker/PostgreSQL 和本地代理。
licensed persistent Agent Server restart、hosted LangSmith/Langfuse、hosted
OIDC/HTTPS、真实通知回执、backup/restore、load/SLO、密钥轮换、升级回滚、
签名 SBOM 和 release attestation 仍是正式生产交付缺口。

### Local database recovery addendum

本轮随后对当前真实本机 Product PostgreSQL 执行了既有 backup/restore rehearsal：
固定 digest PostgreSQL 16 隔离恢复容器中，`22` 张用户表、`912` 行数据逐表计数
完全一致，dump 前后源计数稳定，未验证 constraint 为 `0`，结果为 `passed`。
该证据把本地 logical dump/restore 切片收口为 green，但不代表 hosted backup
policy、PITR、跨区恢复、生产 RTO/RPO、failover 或 operator runbook 已通过。

## 16. 2026-07-18 Deterministic availability and Web market fallback

本轮修复并重新核验了一个真实浏览器暴露的跨层矛盾：同一失败 Run 已经
持久化 8 条可验证 Web Evidence 和一条 Web Search 市场快照，但模型输出的
`unavailable_data` 仍把这些能力描述为不可用；随后独立的
`research_events` 阶段失败，页面又把该状态显示成“没有来源”。这不是可
接受的生产状态表达。

- Graph 现在以 typed market snapshot、research bundle 和 persisted Evidence
  为数据可用性的唯一事实来源，覆盖模型自报的 `unavailable_data`；模型仍
  只负责分析、推理和结构化结论。
- 前端 view model 将稳定机器码映射为中文标签，不把 provider capability
  code 或 raw JSON 直接显示给用户。
- Web market fallback 复用现有 `WebSearchMarketCollector` 和统一 typed
  extraction contract；DuckDuckGo 的研究检索继续使用 News，当前价格市场
  fallback 改用 Text，避免用新闻 vertical 处理行情查询。
- 市场提取提示词版本为 `web-market-extraction-v2`，要求精确引用价格和 URL，
  携带抓取/发布时间，并禁止对冲突值求平均或自行调和。
- Web-derived market data 标记为 `web_search_verified`，只能作为观察和分析
  证据，不能授权开仓；执行门禁仍要求 exchange-native data。

真实本地浏览器证据为：OKX 直连超时并耗尽重试，DuckDuckGo Text fallback
成功，保存 8 条 Evidence，页面显示最新 ticker `62,040.82` 和来源
`DuckDuckGo`；之后 `research_events` 独立失败，页面诚实保持 failed，并显示
`后续研究检索未完成`、`已保留 8 条来源，研究未完成` 及 8 张来源卡。这证明
的是正确的 partial-failure 行为，不是最终分析成功。最新本地门禁为 backend
`848 passed, 164 skipped, 1 warning`，frontend `368 passed`，typecheck、
lint、build、Ruff 和 root `1184 passed` 均通过；skip 仍按未证明处理。

详细记录：
`docs/v2/implementation/2026-07-18-deterministic-availability-and-web-market-fallback.md`。

该切片不改变总体裁决：V2 仍为 `PARTIAL`，`Production Ready: NO`。新的
`market-analysis-v2` 与 `web-market-extraction-v2` 成功最终分析尚未在最新
提示词版本下重新证明；approved hosted Search、licensed Runtime durability、
hosted OIDC/HTTPS、真实通知回执、DR/HA、SLO、签名 SBOM 和 release attestation
仍保持开放。没有执行 commit 或 push。

## 17. 2026-07-18 Live DOM accessibility scan

真实当前 Work 页面在 partial-failure 状态下通过 DOM 扫描确认没有 raw JSON
和横向溢出，但发现 Bark 通知 checkbox 的隐藏 input 没有显式 accessible
name。虽然外层 label 具备可点击文本，扫描器仍将其识别为无名控件。

现已在 `work-surface.tsx` 为该 checkbox 增加 `aria-label="完成后通知 Bark"`，
不改变视觉结构、状态模型或提交 payload。修复后的前端单测为 `368 passed`
（30 files），typecheck、lint、production build 和 `git diff --check` 均通过；
实时页面再次扫描为 `rawJson=0`、`horizontalOverflow=0`、
`unnamedControls=0`，前端和 Agent Server docs 健康探针均为 HTTP 200。

详细记录：
`docs/v2/implementation/2026-07-18-live-dom-accessibility-scan.md`。
该证据仍是本地浏览器/开发 Runtime 证明，不改变 V2 `PARTIAL` 和
`Production Ready: NO`，也不关闭 hosted identity、licensed durability、
真实通知回执或 release gates。没有执行 commit 或 push。

## 18. 2026-07-18 Partial-state Playwright body

failure-injection profile 新增了完整的 Desktop/Pixel 7 Product 浏览器体，
覆盖“OKX 重试耗尽 -> Web 行情回退成功并保存 Evidence -> 后续
`research_events` 失败 -> UI 显示 partial 并保留来源”的跨层状态。测试同时
断言 Product API 的 error endpoint/provider/type、无 Artifact、Evidence
lineage、reload 持久化、raw JSON、overflow、unnamed controls 和 axe。

Playwright `--list` 已发现 2 个测试实例，随后在隔离本地 failure-injection
Agent/Worker/Frontend 栈实际执行，Desktop/Pixel 7 为 `2 passed (17.3s)`。
执行过程中原有 3001/8123 开发栈没有参与该测试的 Worker lease path，测试后
已恢复原 Worker，前端和 Agent health 均返回 HTTP 200。该证据证明的是受控
依赖下的 Product/API/持久化/真实渲染 partial 语义；现有真实外部依赖 partial
页面证据仍单独保留。

详细记录：
`docs/v2/implementation/2026-07-18-partial-state-playwright-body.md`。
V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

### 2026-07-18 Compose-style BFF bootstrap authorization

当前主流程继续按 `G0.2` 推进。真实审计发现 Compose DNS 拓扑下 BFF 鉴权
没有被 loopback 测试覆盖：上下文发现路由可能收到 scoped user token，完整
non-loopback bootstrap 配置还会触发错误模块导入并被隐藏成 502；后端一次性
bootstrap 也可能使用 legacy issuer/context，而生产 Product app 使用新配置。

已完成：Product BFF 按路由区分 identity discovery 与 scoped resource token，
Agent BFF 修正 bootstrap runtime import 并强化本地 HTTP/非 loopback 边界；
backend bootstrap 复用 `configured_development_actor`，统一数据库成员关系与
运行时 issuer/context。Frontend unit `372 passed`，typecheck、lint、build
通过；backend auth/deployment contracts `41 passed`，完整 hermetic suite
`850 passed, 164 skipped, 1 warning`，Ruff lint/format 通过。当前源代码栈的
Work、Product readiness、Agent docs、Worker live/ready 均为 HTTP 200；固定
membership context 已经由 BFF 和 PostgreSQL 双重确认。Desktop/Pixel 7 实时
DOM/axe/overflow 扫描全绿，但真实 provider success-only 两视口仍在
`builtin_web_search/collect_market_snapshot` 三次 timeout 后按 RED 退出。

状态：本地 Compose-style BFF authorization RED 已关闭；这仍不是生产通过。
真实 approved built-in Web Search 成功主链仍 RED（`collect_market_snapshot`
bounded timeout），licensed persistent Agent Server recovery、hosted OIDC/HTTPS、
通知回执和 release proof 仍开放。V2 仍为 `PARTIAL`，`Production Ready: NO`。
详细记录：
`docs/v2/implementation/2026-07-18-compose-bff-bootstrap-auth.md`。

## 35. 2026-07-18 Historical approved-provider Product revalidation

> This built-in provider RED remains current, but it does not supersede or
> invalidate the later explicit DDGS local-proof result in sections 0 and 3.

The latest current-source Desktop and Pixel 7 real Product profile both reached
the canonical `collect_market_snapshot` stage and then failed after three
`builtin_web_search` `APITimeoutError` attempts. The UI correctly rendered
`市场数据与后备检索均失败`, retained failure provenance, produced no Artifact
and accepted no uncited data. Worker readiness, Product database readiness,
PostgreSQL projection and ordinary model capabilities are separate GREEN
evidence; they do not close this external Web Search gate. Detailed record:
`docs/v2/implementation/2026-07-18-real-provider-revalidation-after-prompt-update.md`.
V2 remains `PARTIAL` and `Production Ready: NO`.

## 33. 2026-07-18 Worker readiness gate

Worker operational readiness is now represented by an explicit standard-library
HTTP probe (`/livez`, `/readyz`, `/healthz`). Product has a separate
`/api/v2/readiness`; staging/production fail closed when the Product database
check or Worker readiness URL is absent/unhealthy, and Compose/frontend startup
waits for the Worker `service_healthy` condition. Fresh verification is backend
`850 passed, 164 skipped, 1 warning`,
frontend `368 passed`, typecheck/lint/Ruff passed, and the restarted local stack
returned Worker `/livez=200`, `/readyz=200` and frontend BFF Product readiness
`200`. This closes the false-health/start-order gap only; licensed Agent Runtime
durability, hosted identity, approved Web Search success and release acceptance
remain open. Detailed record:
`docs/v2/implementation/2026-07-18-worker-readiness-gate.md`.

## 39. 2026-07-18 Search readiness error attribution

strict provider selection 现在把 capability probe 的安全失败类型带入启动错误：
当 builtin Web Search 没有被 endpoint 支持时，日志明确显示
`built-in web search was not invoked (APITimeoutError)` 并同时指出 Tavily 是否
配置，而不是只返回模糊的 not-ready。没有加入 key、带凭证 URL、request body 或
raw provider response。

Search capability/runtime readiness `51 passed`，Ruff check/format 通过。该改动
只改善故障溯源，不会把 unsupported Web Search 标记为 ready。详细记录：
`docs/v2/implementation/2026-07-18-search-readiness-error-attribution.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 38. 2026-07-18 Model versus Web capability separation

真实模型能力测试证明当前 endpoint 的普通模型主调用通过：tool calling、
Structured Output、streaming 和 usage reporting 均为 green；同一探测唯一失败
的是 `builtin_web_search`，结果为 `builtin_web_search_invoked=false`、citation
count 为 0、normalized failure 为 `ResearchUnavailable`。

因此 G0.2 的当前根因已经拆清：不是大模型主链不可用，而是当前 endpoint 不提供
兼容的 Responses `web_search` tool。生产必须切换到能通过内置 Web Search
capability probe 的 endpoint，或配置并真实验证 Tavily；代码继续在二者都未验证
时 fail closed。详细记录：
`docs/v2/implementation/2026-07-18-model-vs-web-capability-separation.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 37. 2026-07-18 Backup/restore local rehearsal

固定 digest 的 PostgreSQL 16 临时恢复库完成 Product logical dump/restore：23
张表、2440 行逐表计数一致，source counts stable，restored counts match，未验证
约束为 0。源库没有被修改。

该证据只证明 local backup/restore rehearsal，不证明 hosted backup policy、PITR、
跨区恢复、生产 RTO/RPO 或 failover。详细记录：
`docs/v2/implementation/2026-07-18-backup-restore-rehearsal.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 36. 2026-07-18 SLO observation boundary

当前 Product PostgreSQL 观测 collector 在合法 tenant/workspace UUID scope 下
执行成功，但严格 Internal Alpha evaluator 返回 `formal_slo_measured=0` 并拒绝
该 manifest。只有 domain-event duplicate proxy 和本地运行时长 proxy 可计算；
hosted health、browser 首屏阶段、reconnect、request confirmation、checkpoint
recovery、structured operation、跨租户和 live secret canary 均缺少权威观测。

这条 RED 证明 evaluator 没有把 proxy 或 health endpoint 冒充正式 SLO；它同时列出
下一步必须补的观测数据。详细记录：
`docs/v2/implementation/2026-07-18-slo-observation-boundary.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 35. 2026-07-18 Upgrade/rollback local rehearsal

临时 PostgreSQL 中执行 `0018_progressive_events -> 0015_observability_delivery
-> 0018_progressive_events` 通过。最终 fork source-checkpoint scope、Domain
Event source identity/thread scope、不可变 payload 列、progressive sequence
列和 secret scan 均通过验证。

该结果不证明 hosted image rollback、生产零停机发布、生产数据库 failover 或
release attestation。详细记录：
`docs/v2/implementation/2026-07-18-upgrade-rollback-rehearsal.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 34. 2026-07-18 Key rotation local rehearsal

M6 key-rotation drill 在隔离临时 PostgreSQL 中通过：0018 head migration 成功，
4 条通知凭据全部 rewrap，旧版本剩余 0，rotation 前/overlap/退休后的 delivery
均为 delivered，重复投递为 0；JWT old/new overlap 与退休旧 token 拒绝通过，
进程被 kill 后能够恢复，secret scan findings 为 0。

该结果的 proof level 是 `local-key-rotation-rehearsal`，不修改当前产品库，
也不证明 hosted secret manager、数据库密码、OIDC/provider key、生产零停机
发布或 release attestation。详细记录：
`docs/v2/implementation/2026-07-18-key-rotation-rehearsal.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 33. 2026-07-18 Local supply-chain gate

重新执行当前工作树的本地供应链门禁，4 个扫描全部完成、无 skip：Python
审计覆盖 119 个包、前端审计覆盖 582 个依赖，漏洞数均为 0；Python 和前端
CycloneDX SBOM 分别生成 119 和 574 个组件。扫描期间源文件 identity 保持
stable，工具没有继承 package-manager credential，也没有发布原始 stderr。

该结果的 proof level 是 `local-working-tree-supply-chain`，工作树仍然 dirty，
产物写入 `/tmp` 而不是 release artifact。因此它不能证明 hosted dependency
audit、container-image SBOM、签名、release attestation 或 production release。
详细记录：
`docs/v2/implementation/2026-07-18-local-supply-chain-gate.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 15. 2026-07-18 KR-GATE-01 local key rotation proof

The M6 key-rotation slice now has a fresh local recovery rehearsal, but its
formal status is still `partial` because hosted custody and release evidence
are unavailable.

- Notification credentials use an active write key plus versioned decrypt-only
  overlap keys. Product settings remains usable while the stored version is in
  the overlap keyring and fails closed after retirement.
- Internal JWT public keys support old/new overlap, same-kid idempotence and
  conflict rejection. Retired old tokens are rejected while new tokens remain
  valid.
- Rewrap is bounded, CAS-protected and resumable. A process killed after a
  committed batch can be restarted without redoing completed rows or claiming
  retirement early.
- `tools/v2/key_rotation_drill.sh` runs a pinned local PostgreSQL 16 rehearsal
  with four tenant destinations, delivery checks before/during/after overlap,
  SIGKILL recovery, JWT checks and a secret-safe `0600` report.
- Fresh result: `4/4` rows rewrapped, `0` old rows remaining, delivery was
  `delivered` in all three phases, duplicate deliveries `0`, JWT overlap and
  retirement checks passed, recovery passed, secret findings `0`.
- Focused contracts and real PostgreSQL integration were `64 passed` and
  `7 passed`, respectively; the full real PostgreSQL integration after the
  migration repair was `184 passed`. The first drill RED was fixed and is
  documented; it was not converted to a pass by weakening the assertions.
- Migration `0016_repair_fork_scope` repairs stale five-column fork constraints
  and passed a local downgrade/upgrade round trip.
- The migration debugging retained the real intermediate REDs: missing
  six-column uniqueness and an overlong Alembic revision id. The final
  conditional migration handles both databases already carrying the correct
  unique key and databases carrying the stale five-column constraint.

This does not prove hosted secret-manager custody, production database
password rotation, OIDC client-secret rotation, provider API-key rotation,
zero-downtime rollout, hosted Agent Server durability or release attestation.
The detailed record is
`docs/v2/implementation/2026-07-18-kr-gate-01-key-rotation.md`. V2 remains
`PARTIAL`; `Production Ready: NO`.

## 16. 2026-07-18 local migration upgrade/rollback proof

The migration compatibility slice now has a fresh local rehearsal. A pinned
PostgreSQL 16 container completed `0016_repair_fork_scope -> 0015_observability_delivery -> 0016_repair_fork_scope`; the six-column fork foreign key and unique constraint were queried directly after the final upgrade. The focused contract suite is `4 passed`, and the report is secret-safe `0600`.

The first drill RED was a real CLI argument bug and is recorded in the ledger;
it was fixed without weakening assertions. This remains local evidence only:
hosted image rollback, production zero-downtime traffic, database failover,
operator approval and release attestation are still open. V2 remains
`PARTIAL`; `Production Ready: NO`.

## 17. 2026-07-18 local health load preflight

The load tooling foundation now has a real local Product health measurement:
`200/200` successful requests at concurrency `20`, p95 `22.852ms`, failures
`0`, with `4 passed` performance contracts and a secret-safe `0600` report.

This is intentionally not mapped to any complete ADR 0006 SLO. Task admission,
first stream event, market analysis, reconnect, duplicate events, Structured
Output, Evidence completeness, checkpoint recovery and hosted availability are
not measured by a health endpoint. The report therefore carries
`slo_claims=[]` and proof level `local-http-load-preflight`. Hosted load/SLO
remains open; V2 remains `PARTIAL`; `Production Ready: NO`.

## 18. 2026-07-18 Internal Alpha SLO contract foundation

The accepted ADR 0006 Internal Alpha threshold set now has a strict evaluator
and synthetic source-candidate coverage. All 12 metrics, positive sample counts,
measurement windows and query IDs are mandatory; any missing, malformed,
non-finite or failed metric rejects the report. Combined load/SLO performance
contracts are `8 passed`.

No real complete Product-flow SLO manifest has been produced. The passing
fixture is explicitly synthetic, while the health load proof has
`slo_claims=[]`. Actual Task/stream/analysis/reconnect/dedup/Structured Output/
Evidence/recovery samples, hosted availability and alert receipts remain open.
V2 remains `PARTIAL`; `Production Ready: NO`.

## 19. 2026-07-18 terminal Domain Event ledger foundation

Alembic `0017_domain_events` and the existing Product worker now provide an
ordered, scoped and idempotent terminal Domain Event ledger for the exact eight
Task 7 event types. Successful Runs append seven events without notification
or all eight with a notification plan in the existing terminal transaction;
the worker repairs terminal Runs missing `run.terminal` using
`FOR UPDATE SKIP LOCKED`.

The first contracts failed because the model and event builder did not exist;
intermediate schema/worker contract failures were fixed without weakening the
gate. A full run on the long-lived local database reported `179 passed, 5
failed` because pre-existing Outbox and credential-version rows invalidated
tests that assumed global empty-table counts. No local data was deleted. A
fresh isolated PostgreSQL 16 database migrated from zero and passed all `184`
integration tests. The real migration round trip passed
`0017_domain_events -> 0015_observability_delivery -> 0017_domain_events` and
reported zero secret findings. The backend hermetic suite is `805 passed, 157
skipped, 1 warning`; root structure/deployment is `153 passed`.

This is not progressive stage persistence. Product PostgreSQL still does not
guarantee that successful paid stages remain queryable when a later stage or
Run fails. Official SDK stream consumption, per-stage idempotency across node
retries/reconnects, licensed persistent Agent Server restart and hosted SLO
evidence remain open. Detailed record:
`docs/v2/implementation/2026-07-18-task-07-domain-event-ledger.md`. V2 remains
`PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 20. 2026-07-18 official-stream progressive stage persistence

The Product worker now consumes bounded slices of the official
`langgraph-sdk==0.4.2` resumable `updates` stream. Submit, resume and fork Runs
are created with `stream_mode=["updates"]` and `stream_resumable=True`; Product
persists each validated paid-stage payload and the official event cursor in one
fenced transaction. The first attach uses official `Last-Event-ID=0`, while
reconnects use the exact last committed event ID.

Alembic `0018_progressive_events` replaces event-type-as-identity with a stable
source key, stores immutable JSONB payloads, includes Thread in the Run scope
foreign key and allocates Thread sequence ranges atomically. Same source/same
hash replay is idempotent; same source/different hash fails closed. The
terminal Artifact/Decision/notification transaction and official HITL path are
unchanged.

Fresh evidence includes `104 passed` focused contracts, `68 passed` real
dispatcher tests, `2 passed` worker SIGKILL recovery after removing a competing
local worker, `187 passed` full fresh PostgreSQL integration, a passing
`0018 -> 0015 -> 0018` migration drill, frontend `319 passed` plus
typecheck/lint/build, backend hermetic `809 passed, 160 skipped`, and a real
Pixel 7 Product flow `1 passed (1.4m)`. Direct
database verification of the successful Run found exactly seven ordered
events: five official-source market/research/analysis/evidence/risk stages and
Product-owned artifact/terminal events, with no duplicates.

Desktop real-provider failures remain visible evidence: Search timeout/citation
failures and invalid model Structured Output were not hidden. The last failure
retained official-source market and research events before terminal failure,
proving paid stages survive a later real model failure.

Licensed persistent Agent Server restart, hosted OIDC/HTTPS, production DB
failover, complete Product-flow SLO and release attestation remain open.
Detailed record:
`docs/v2/implementation/2026-07-18-task-07-progressive-stage-persistence.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 21. 2026-07-18 local Product SLO observation boundary

Two independent audits established that Product PostgreSQL alone can
recompute `0/12` formal ADR 0006 SLOs. A new tenant/workspace-scoped,
payload-free collector now runs in one repeatable-read/read-only transaction
and emits only explicit proxy or unavailable observations, never a production
pass. The existing SLO evaluator no longer accepts unbound caller-supplied
`local-observed` values; its hard-coded secret-scan zero was removed and
no-threshold availability no longer appears as passed.

Fresh contracts are `10 passed`; the complete performance group is `14
passed`; focused Ruff lint/format passed. A settled real local Product DB
window contained four initial Runs: one succeeded and three failed. The local
proxy report measured first persisted stage p95 `36,986.381ms`, first persisted
agent output `78,056.762ms` for only `1/4` Runs with three missing, Run execution
max `90,224.340ms`, persisted duplicate proxy `0/15`, and successful normalized
projection chain `1/1`. These values are local mixed-traffic diagnostics, not
hosted SLOs.

The `0600` report is staged outside the repository under content hash
`1432b30664adca638a23362a3a0ff681b2de4c17c4db1258d42ecb5b641b6137`.
Formal request/ack, browser render, stream delivery/reconnect, Structured
Output attempt, Evidence relation, recovery, hosted security and secret-scan
measurement sources remain absent. Detailed record:
`docs/v2/implementation/2026-07-18-m6-local-product-slo-observation.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 22. 2026-07-18 canonical terminal persistence and real failure rendering

All audited Product terminal branches now use one atomic canonical persistence
path for Task/Run state, completion timestamps, safe terminal output, SHA-256
hash, projection fence and `run.terminal` Domain Event. This includes invalid
persisted commands, confirmed/permanently failed cancel, expired submit
uncertainty, resume/fork/generic Agent Server exhaustion, database fallback and
terminal hash conflict. Same-hash replay repairs a missing event; conflict
replaces a stale success projection with an explicit canonical failure.

Failed terminal output now requires a bounded structured error, and unknown raw
diagnostics are discarded. A same-Task authoritative
`failed/terminal_projection_conflict` correction can replace an older terminal
frontend projection. The Work surface now performs four bounded, visibility-
aware terminal revalidations over about 110 seconds; correction, Task/Run
change, unmount or budget exhaustion stops it, and late responses are fenced.
Focused RED was `3 failed, 320 passed`; current combined terminal/error-copy
focus is `62 passed`.

Fresh backend verification is `71 passed` for the complete real PostgreSQL
dispatcher suite, `820 passed, 163 skipped, 1 warning` for hermetic, Ruff passed
and formal docs `18 passed`. A retained local real `model_invalid_output` Task
was inspected at Desktop and Pixel 7. Its failure diagnosis, exchange market
snapshot and four persisted Web Evidence rows rendered without raw JSON,
horizontal overflow or clipped text; there was no success Artifact.

This is local browser evidence, not a visual baseline or hosted acceptance.
Product stage-history DTO and its running-refresh browser proof, licensed
restart durability, hosted OIDC/HTTPS and M6 release gates remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-task-07-canonical-terminal-persistence.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 23. 2026-07-18 Playwright profile discovery gate

An executable `playwright test --list` audit found the old default configuration
mixed 36 fixture tests with two real-provider and 14 failure-injection tests,
while official stream, cancel, HITL, Inbox, Library and Fork specs were not
collected by their intended commands. The first discovery contract retained
`14 failed`.

Playwright now has explicit profile-to-spec ownership, default fixture
isolation, unknown-profile rejection and fail-closed environment admission for
every non-fixture profile. Dedicated npm commands collect their exact spec.
The new structure test executes Playwright `--list` and verifies all project /
spec pairs rather than checking only that files exist.

Fresh discovery evidence is `29 passed` focused and `32 passed` with existing
browser structure gates. This slice executed no browser test body and made no
Product database or failure-injection mutation, so it is not real E2E
acceptance. Official-stream running refresh and all other real profiles still
need explicit execution.

Detailed record:
`docs/v2/implementation/2026-07-18-playwright-profile-discovery-gate.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 24. 2026-07-18 Product stage-history recovery

`TaskView` now exposes a selected/latest Run stage history containing only
ordered stage/status/time/source metadata plus coherent Product and official
cursors. The query is tenant/workspace/owner/Task/Run scoped and never selects
Domain Event payload, checkpoint, source identity, model content or
authorization. Product history is the durable UI baseline; official
`@langchain/react useStream` remains the live enhancement. Stage versions merge
by greatest sequence and a committed stage cannot regress.

Fresh proof includes Product contracts `138 passed`, Product/persistence
contracts `194 passed`, real PostgreSQL Product service `34 passed`, combined
real Product/dispatcher `105 passed`, backend hermetic `835 passed, 164 skipped`
and frontend `29 files / 335 tests`; typecheck/lint passed. The current shared
API projected the retained real Task's market, Evidence and failed Run events
with Product cursor `3`.

The new official-stream E2E now requires a real nonterminal persisted stage,
reloads while running, forbids a second POST and refuses terminal fallback. It
is discoverable on Desktop/Pixel 7 but was not executed after the in-app browser
URL policy rejected the post-restart reload. No alternate browser workaround
was used, so browser acceptance remains open.

Detailed record:
`docs/v2/implementation/2026-07-18-task-07-product-stage-history-recovery.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 25. 2026-07-18 controlled OKX to Web Search fallback matrix

Two explicit failure profiles now prove the canonical market fallback path.
OKX HTTP failures still traverse the real provider retry budget; the controlled
Web Search market collector either returns a typed cited partial snapshot or a
typed fallback error. Product errors preserve bounded endpoint, fallback source
and primary attempt, and the failure UI explains both dependency layers.

Backend profile/Graph contracts are `39 passed`; Product fallback UI retained
`2 failed, 34 passed` as RED and is `36 passed` GREEN. In an isolated fresh
local Product/PostgreSQL/worker/official Agent Server stack, Desktop exercised
both paths, a focused success rerun was `1 passed (9.9s)`, and Pixel 7 A/B were
`2 passed (20.7s)` with overflow, unnamed-control and axe checks. Provider/model
inputs were controlled; this is not actual external outage or hosted evidence.

Detailed record:
`docs/v2/implementation/2026-07-18-task-12-market-fallback-matrix.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 26. 2026-07-18 Web Search timeout budget and structured evidence binding

The first fresh real built-in Web Search Product run exposed a retry-budget
defect: one transport call consumed the complete 30-second budget. Search now
allocates bounded per-attempt time while retaining the formal three-attempt
total budget, and the latest built-in run transparently reached `attempt=3`
before persisting `research_unavailable`.

Research structured output no longer asks the model to reproduce provider URLs
or timestamps. The official LangChain `ToolStrategy` returns a bounded
`source_index`; the application maps it to immutable verified Web Evidence and
fills metadata deterministically. Market Analysis, Web Market extraction and
Research share one official `Runnable.with_retry` budget that includes one
`StructuredOutputError` repair.

Fresh verification is backend `837 passed, 164 skipped, 1 warning`, frontend
unit `335 passed`, typecheck/lint/build passed, root structure/discovery passed,
and isolated fresh PostgreSQL integration `191 passed` after migrations through
0018. With an explicit local-only `SEARCH_PROVIDER=duckduckgo` decision, a
real Product Desktop flow passed in `1.0m` and Pixel 7 passed in `56.5s`.
Both persisted eight typed web evidence rows, a committed Artifact, a succeeded
Run and all seven ordered Product/official stages; Playwright performed the
DOM, axe, overflow, unnamed-control, console and network checks. These results
are local explicit-provider evidence, not hosted or approved built-in/Tavily
production acceptance.

Detailed record:
`docs/v2/implementation/2026-07-18-web-search-timeout-budget.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 27. 2026-07-18 Run detail navigation and live revalidation

Persisted Run rows now open the dedicated `/runs/[runId]` Product route instead
of bypassing it through Work. Active Run details revalidate every five seconds,
pause while the page is hidden, refresh on visibility recovery, fence stale
responses and preserve the last valid projection during background failures.
Cancellation, Task/Run-scoped Work actions and feedback availability now follow
the latest durable Run state.

The first browser execution retained two locator failures because the same
correct status appeared in Run metadata and Task projection. The assertion was
scoped without weakening its content. The first complete lint run then retained
a React effect-state error; Run identity now remounts state via `key`, while the
initial fetch updates state only from its asynchronous completion.

Fresh evidence is `21 passed` focused Run unit tests, frontend `30 files / 356
tests`, typecheck/lint/build passed, route boundaries `7 passed`, and fixture
Playwright Desktop/Pixel 7 `4 passed`. The browser test proves a fresh
`running -> failed` transition, two or more GETs, status-consistent controls,
feedback suppression, axe, overflow and unnamed-control checks.

The current local stack was then restarted as one token-coherent topology with
official `langgraph dev --no-reload` 0.11.1, Product worker, PostgreSQL and
Next.js. All health probes returned 200. Fresh zero-mock Product Playwright
passed Desktop in `1.5m` and Pixel 7 in `51.5s` (`2 passed in 2.5m`). Both
latest Runs are succeeded with final actions. The latest detail showed one
committed Artifact, eight typed DuckDuckGo sources and two model audit calls;
a fresh in-app browser tab reported zero current console errors, raw JSON blocks
or horizontal overflow. The new full-page screenshots were visually inspected
but remain execution artifacts rather than approved baselines.

Detailed record:
`docs/v2/implementation/2026-07-18-run-detail-live-revalidation.md`.
The zero-mock result uses explicit local `SEARCH_PROVIDER=duckduckgo` and an
in-memory development Agent Server; it does not close approved production
provider, licensed durability or hosted acceptance. V2 remains `PARTIAL`;
`Production Ready: NO`. No commit or push was performed.

## 28. 2026-07-18 G0.3 single Graph and Worker entry

The production Python package no longer compiles or exports a module-level
Graph. `crypto_alert_v2.graph` exports only `create_graph` and the sole deployed
`graph_factory`; tests explicitly construct their in-process Graph harnesses.
The transitional `commands/worker.py` executable was deleted. Agent Server
authorization assembly now lives in a non-executable auth module, and
`python -m crypto_alert_v2.workers` remains the only Worker process entry.

Fresh verification is `42 passed` canonical Graph/Worker/security, `1 passed`
projection-worker assembly, `30 passed` deployment/routes, backend `836 passed,
164 skipped, 1 warning`, focused Ruff passed, formal docs `18 passed` and diff
check passed. The complete local stack was restarted from current source:
official Agent Server loaded `graph/__init__.py:graph_factory`, the unified
Worker process stayed alive, and Work/Runs/Product health/Agent docs all
returned HTTP 200. Import inspection found no legacy Worker module and exactly
`create_graph`/`graph_factory` as public Graph exports.

Detailed record:
`docs/v2/implementation/2026-07-18-g03-single-graph-worker-entry.md`.
This does not replace the licensed persistent Runtime or prove hosted restart.
The Product SDK adapter, V1 parity/removal, approved Web Search, OIDC/HTTPS and
M6 gates remain open. V2 remains `PARTIAL`; `Production Ready: NO`. No commit or
push was performed.

## 29. 2026-07-18 durable cancellation stream teardown

The first fresh current-source durable cancellation profile reached the correct
Product `cancelled` state on Desktop and Pixel 7 but retained `2 failed`: the
terminal durable progress panel and live official stream shared
`data-testid="official-run-stream"`. The official `@langchain/react useStream`
component had unmounted, while the Product-owned fallback was misidentified as
the live connection.

The two DOM identities are now exclusive. A pure eligibility rule rejects
historical selection, persisted cancel requests, absent Tasks and all terminal
statuses. The browser profile requires the live stream to leave the DOM,
requires durable progress to replace it, and proves no new `/api/agent/` read
starts in a post-terminal observation window or after reloading the cancelled
Task. Exactly one Product cancel POST remains required, and browser-side Run
writes remain forbidden.

Fresh evidence is frontend `30 files / 364 tests`, typecheck, focused ESLint and
production build passed. The first corrected Desktop/Pixel run was `2 passed
(22.6s)`; the strengthened lifecycle run was `2 passed (27.8s)`.

Detailed record:
`docs/v2/implementation/2026-07-18-cancel-stream-teardown.md`.
This local official Server remains an in-memory development Runtime and does not
prove hosted identity or restart durability. V2 remains `PARTIAL`; `Production
Ready: NO`. No commit or push was performed.

## 30. 2026-07-18 Inbox, HITL, Fork and official-stream closure

Four independent real-browser profiles were re-executed against the same
current-source local topology while preserving separate Task fixtures. The
profiles intentionally retained each failure before correcting the product or
acceptance contract:

- Inbox first failed after its long-page bottom assertion left the intended
  review entry outside the actionable viewport, then exposed an ambiguous
  same-symbol card binding. The profile now returns to the exact
  `/work?task=<id>` entry before interaction.
- HITL first retained an unpadded `H:MM:SS` countdown and obsolete English
  evidence/risk headings. The Product view now uses stable `HH:MM:SS` and the
  current `证据门禁`/`风险门禁` labels.
- Fork first retained Node 22 visual baseline differences. The deeper backend
  failure was checkpoint GET serializing private `_ReadRuntime` state. Upgrading
  `langgraph-api`/in-memory Runtime did not fix it by itself, and a first
  factory allowlist still failed because ambient child config was merged back
  into Graph defaults. The final factory uses official `Pregel.copy` with only
  root callbacks and sanitized metadata/tags; an ambient-runtime contract
  prevents `configurable`, checkpointer and execution coordinates from leaking.
- Official stream first timed out while waiting for a terminal status even
  though the canonical required-review profile correctly reached
  `waiting_human`. Subsequent RED runs found an incorrect durable-fallback
  expectation during live HITL, a brittle comparison of dynamic reload text,
  and one real `StructuredOutputValidationError`. Market Analysis now uses the
  official `ToolStrategy(handle_errors=...)` repair loop bounded by
  `ModelCallLimitMiddleware(run_limit=3)`; outer `Runnable.with_retry` remains
  limited to transport errors.

Fresh GREEN evidence is Inbox Desktop/Pixel 7 `2 passed (8.5s)`, HITL approve
`2 passed (16.4s)`, Fork `2 passed (15.4s)`, and official-stream main flow `2
passed (1.5m)`. Framework/factory/observability contracts are `46 passed`;
focused agent/graph contracts are `21 passed`; Ruff passed. The official-stream
profile additionally proves real OKX, explicit local DuckDuckGo, model
structured output, active-stage reload, same Task/Run binding, official Agent
reads, HITL pause, a second reload, DOM/axe/overflow checks and no browser-side
Agent commands.

Detailed record:
`docs/v2/implementation/2026-07-18-real-inbox-hitl-fork-stream-closure.md`.
All Agent Server evidence in this section uses the official in-memory
development Runtime. It does not prove licensed persistence, restart recovery,
hosted OIDC/HTTPS, approved production Search or a release gate. V2 remains
`PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 31. 2026-07-18 Web Evidence partial-state and full QA convergence

A cross-layer audit reproduced a valid partial-failure state: OKX can fail,
Web Search market fallback can persist verified Evidence, and the later
independent research search can then fail. The Graph and Product persistence
correctly retained `failed + web_evidence`, but the Product API and frontend
incorrectly described that state as if no Web Search evidence existed.

The retained RED proved all affected boundaries:

- Graph errors did not identify the `research_events` stage.
- Product public errors always said no verified source was returned.
- Frontend error text repeated the false no-source claim.
- `toResearch()` prioritized `research_unavailable` over a non-empty Evidence
  list, so the header rendered `检索不可用` above a real source card.
- The official structured-output repair loop now ends with
  `ModelCallLimitExceededError`; the Product Graph initially misclassified that
  bounded repair exhaustion as generic `model_unavailable`.

The Graph now emits `endpoint=research_events`, preserves the earlier verified
Evidence and maps both `StructuredOutputError` and official bounded repair
exhaustion to typed non-retryable `model_invalid_output`. Product public error
text counts the same terminal payload's Evidence. The frontend has an explicit
`partial` research state and renders `已保留 N 条来源，研究未完成` with the source
cards, while keeping the failed Run and diagnostics visible.

Fresh GREEN is backend focused `151 passed`, complete backend `840 passed, 164
skipped, 1 warning`, isolated PostgreSQL migration `0001 -> 0018` plus complete
integration `191 passed`, frontend unit `366 passed`, typecheck/full ESLint and
isolated production build passed, root suite `1184 passed`, Playwright discovery
contract `29 passed`, and Ruff check/format passed with all 179 backend files
formatted. The frontend production build generated all 14 current routes.

Detailed record:
`docs/v2/implementation/2026-07-18-web-evidence-partial-state-and-full-qa.md`.
The new partial-state path has component-render and cross-layer contracts but no
new real Playwright test body yet. Playwright `--list`, controlled dependencies,
the in-memory Agent Server and local PostgreSQL do not prove hosted Search,
licensed durability or release acceptance. Seven real provider/model tests
remain skip-gated and unproved. V2 remains `PARTIAL`; `Production Ready: NO`.
No commit or push was performed.

## 32. 2026-07-18 Real provider revalidation after prompt update

最新 `market-analysis-v2` 和 `web-market-extraction-v2` 下重新执行了真实
Product Desktop/Pixel 7 主流程。两组结果均按失败处理，没有通过放宽引用契约
或接受 uncited 数据掩盖问题：

- 诊断 DuckDuckGo 配置：OKX 重试耗尽后，DuckDuckGo Text 行情回退保存了 8 条
  Evidence，但后续 `research_events` 的 News 查询连续 3 次超时；两视口都
  正确显示研究未完成且不生成 Artifact。
- approved `builtin_web_search` 配置：两视口在
  `collect_market_snapshot` 的 builtin Web Search 连续 3 次
  `APITimeoutError`，Product 正确显示交易所和 Web Search 两层依赖均不可用，
  没有生成模型分析或 Artifact。

这证明当前本机 endpoint/网络/Provider capability 尚未形成真实成功主链，
不是前端把结果渲染错了。代码继续保持严格 provider、引用、Evidence 和执行
门禁；需要正确的生产 Web Search credential/endpoint/egress 后才能关闭 G0.2
真实成功门禁。详细记录：
`docs/v2/implementation/2026-07-18-real-provider-revalidation-after-prompt-update.md`。

V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行 commit 或 push。

## 34. 2026-07-19 Controlled post-draft Deep Research report HITL

Deep Research draft 已进入唯一 canonical `StateGraph` 的官方审核节点。Required
policy 通过 LangGraph `interrupt()` 暂停并由 Product InterruptPause/Inbox/Work
投影；approve、reject 和完整 typed report edit 通过 official resume 保持同一
Thread/checkpoint/interrupt lineage，但每个被接受的审核批次都会创建新的 Product
resume Run 和同一 Thread 上新的 official Run。Edit 后必须出现第二次 interrupt；approve 后才创建 committed
ArtifactVersion；reject 保留 blocked draft，且不创建 ArtifactVersion、交易
Decision 或 `artifact.committed` Domain Event。前端不可修改 source catalog、
harness mode、model audits 或 artifact status，scope/type/no-op/citation 违约均
fail closed。

Fresh local evidence 为 focused backend `48 passed`、complete backend
`957 passed, 177 skipped, 1 warning`、fresh isolated PostgreSQL integration
`209 passed, 7 skipped`、frontend unit `416 passed` 以及 typecheck/lint/build。
PostgreSQL 总数是 Graph MemorySaver 审核语义、Product pause/response projection 和
既有 success report store 的聚合证据，不是单条 required-review PostgreSQL E2E。
Root structure/deployment `1199 passed, 51 warnings`，Ruff 对 194 个 backend 文件
和 `git diff --check` 通过。新增 Playwright profile 的 discovery RED 缺口已修复：
profile 改名为 `controlled-deep-research-hitl`，要求显式 controlled gate，并由
profile/npm/missing-environment 三类 contract 覆盖，focused discovery 为
`32 passed`。最终 root 重跑还保留了一次真实 RED：通知 TSX 用
`JSON.stringify` 计算内部轮询指纹，触发产品面 raw-JSON 结构门禁；现已统一改用
既有 `stableFingerprint()`，定向结构/docs/discovery `57 passed`，完整 root 再次
通过 `1199 passed`。

当前源码浏览器后半链使用 isolated PostgreSQL、development Agent Server、统一
Worker 和 production Next build，Desktop 完成 edit -> second review -> approve ->
committed/reload，Pixel 7 完成 reject -> blocked/reload，结果为
`2 passed (16.0s)`。运行中修复了 invalid notification key、Next dev lock、
accessible-name 定位和 disabled/transition color contrast 等真实故障；各关键状态
保持 axe、DOM、overflow、raw JSON、console/page/5xx 和截图门禁。

证据边界不变：Seeder 直接注入 controlled draft 和 waiting-human projection，绕过
initial Product admission、Worker submit、Deep Agent、真实模型/Search 与来源采集；
Desktop/Pixel 7 分别覆盖不同分支，仓库中没有 retained JUnit/HTML/trace/screenshot
receipt。它是本地 post-draft Product/official-resume 证据，不是完整 zero-mock
Provider 链、licensed restart、hosted OIDC/HTTPS、hosted LangSmith/Langfuse 或
release attestation。

Detailed record:
`docs/v2/implementation/2026-07-19-task-13-deep-research-mainline.md`。
Task 13 remains `partial`; Task 8 remains `RED / PARTIAL`; all 16 planned Tasks
remain `partial` (`done=0`, `blocked=0`, `not_started=0`). V2 remains `PARTIAL`;
`Production Ready: NO`. No code was staged, committed or pushed.

## 35. 2026-07-19 Real Deep Research runner and provider RED

新增 current-source runner 以 isolated PostgreSQL、`langgraph dev --no-reload`、统一
Worker 和 production Next build 执行 Desktop/Pixel 7 同一条 zero-route-override
Deep Research admission -> pending reload -> required HITL -> edit -> second review ->
approve -> committed reload 路径，并保留 JUnit/JSON/HTML/trace/screenshot/video、
secret-safe DB lineage、review-policy receipt、redacted logs 和 SHA-256 manifest。
Runner 不读取 `backend/.env`、不提取其他进程环境，也不停止用户 `3110` 进程。

执行先修复了 runner 的 PostgreSQL 变量绑定与 exact label locator 两个真实缺陷。
随后真实 Product Task 揭示 Deep Agents coordinator 的三主题委派被
`SUBAGENT_DELEGATION_LIMIT=1` 拒绝。临时调到 `3` 后，最新 retained run 又证明模型
仍可超过该上限，因此该方案已废弃。当前恢复硬上限 `1`，通过 LangChain 官方
`ModelRequest.override(model_settings={..., "parallel_tool_calls": False})` 同步/异步
middleware 与 Deep Agents 官方 `HarnessProfile.tool_description_overrides`，要求唯一
researcher 在一次 task 内携带 1-3 条查询。filesystem、general-purpose subagent、
Search 和 model budget 继续 fail closed。

临时 limit `3` 的两视口 retained RED receipt 为
`/tmp/crypto-alert-real-deep-research-20260719-135341`：Desktop 为
`ToolCallLimitExceededError`，Pixel 7 为 `APITimeoutError`，均为 0 evidence / 0
Artifact / 0 Decision。最终单委派设计下又完成三次 direct real Deep Research；分别
在 `57.65s`、`62.04s`、`125.14s` 后以 `APITimeoutError`、`InternalServerError`、
`APITimeoutError` 终止。没有一次取得 verified evidence，因此没有继续重复整站 runner。
Tavily 没有配置 key，DDGS 不作为 production proof。

Deep Research Artifact 现在新增 server-owned typed `search_coverage`。多 query
部分成功会保留 verified evidence，全失败仍抛最早真实 provider error；来源按 query
round-robin 合并并严格封顶 8 条，同一 Run 的 harness transport replay 读取 ledger
cache 而不重复 Search。详细 provider/error kind 不进入模型或可编辑 report，前端以
typed coverage band 展示成功/尝试数量和规范化失败原因。后端最终聚焦回归为
`104 passed`，ledger/harness 定向为 `15 passed`；前端
typecheck/lint 与全部 `416 passed`。PostgreSQL-gated 相关用例本轮 `5 skipped`，明确
不计作通过。

本机检查栈随后重新启动在 Agent `8123`、Worker `19091`、frontend `3001`。Fresh
Product Task `db35d0bf-d100-4a6f-9402-9bc391f93da4` 实际经过 admission、PostgreSQL、
Worker、official local Agent Server 和 canonical Graph，并以
`builtin_web_search / APITimeoutError / attempt=3` 安全失败；0 Evidence、0 Artifact、
0 interrupt。Desktop/Pixel 7 重载保持同一 Task 与 correlation ID，无 raw JSON、横向
溢出、重复 ID、匿名控件或 console error。移动端失败诊断已改为单列，canonical code
不再生硬拆词。受控 partial `search_coverage` Artifact 的 Desktop/Pixel 7 Playwright
再次为 `2 passed (7.3s)`，明确断言 `1 / 2`、展开 timeout reason、axe、DOM、来源深
滚动和断线重读；它仍只是 UI/fixture 证据，不是 provider GREEN。

Built-in Search 随后补齐官方 server-tool 强制调用参数。锁定版
`langchain-openai==1.3.5` 会把 `tool_choice="web_search"` / preview 转换为 Responses
API `{"type": ...}`，当前 provider 每次 bind 同时传入
`parallel_tool_calls=False`；Search/readiness/retry focused regression 为
`126 passed`。真实结构探针却证明当前兼容端点忽略 forced `web_search`：返回只有一个
plain text block，0 completed Search、0 tool call、0 provider citation；forced preview
为 `InternalServerError`。修复后的 provider preflight 依次为
`UnverifiedServerToolCall 13.12s -> APITimeoutError 7.04s -> APITimeoutError 7.52s`，
最终仍是 attempt `3` RED。因此没有重复完整 Deep Agent/Playwright。检查栈已重启到
最新源码并继续监听 `8123/19091/3001`。

Task 13 remains `partial`; Task 8 remains `RED / PARTIAL`; all 16 planned Tasks
remain `partial`. V2 remains `PARTIAL`; `Production Ready: NO`. No code was staged,
committed or pushed.

## 36. 2026-07-20 Task 13 data-lifecycle local vertical slice

Task 13 的 Product-owned retention/export/deletion 已从“未实现”校正为本地
vertical slice GREEN。实现包含 `0022_data_lifecycle`、actor/workspace policy、durable
export/deletion jobs、统一 `LifecycleWorker`、严格 Product API/BFF、Settings typed UI、
owner-scoped reload/rejoin、manifest/bundle canonical SHA-256 和 explicit
`pending_external` external-system state。它没有新增 Graph、Agent Runtime 或队列。

共享开发库保留了一次真实 `DuplicateTable` RED：integration fixture 先执行了
`Base.metadata.create_all`。核对表/索引后只为保留本地数据 stamp 到 `0022`；该 stamp
不算迁移证明。另一个 fresh PostgreSQL 从 `0001` 升到 `0022`，用于 isolated
production-build Playwright。首轮 4 个浏览器用例因三处 axe 对比度和 switch decoration
pointer interception 全部 RED；修正 CSS 后未关闭 axe、未 force click、未 route mock，
最终 Desktop/Pixel 7 export/reload 与 hold/deletion 为 `4 passed (10.0s)`。证据目录：

`/tmp/crypto-alert-real-lifecycle-e2e-20260720-after-contrast-fix`

隔离数据库最终有两条 `blocked_legal_hold` 与两条 `pending_external`。真实删除均为
`product_db=succeeded`，外部系统仍 `pending_external`、receipt 为 null，并显式记录
adapter 未配置；历史 export bundle 已 scrub，legal hold 已恢复 inactive。检查完成后
隔离服务和数据库已删除。Fresh regression 为 backend unit/contract
`975 passed, 1 skipped`、PostgreSQL integration `220 passed, 7 skipped`、frontend
`40 files / 453 passed`、lint/typecheck/build、root structure/deployment、Ruff 与
`git diff --check` GREEN。8 个 skip 仍是 live/licensed Agent Server 未证明能力，不能
计作通过。

详细记录：
`docs/v2/implementation/2026-07-20-task-13-data-lifecycle.md`。外部 deletion adapter/
receipt、Memory、Outcome、完整 entitlement/usage、webhook、licensed restart、hosted
OIDC/HTTPS、PITR/DR/SLO/security/release attestation 仍开放。Task 13 remains
`partial`; V2 remains `PARTIAL`; `Production Ready: NO`. No code was staged,
committed or pushed.
