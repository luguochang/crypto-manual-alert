# V2 Final 选择性重构规格

> 状态：Approved
>
> 批准日期：2026-07-13
>
> 适用分支：`codex/v2-final-20260713`
>
> 原型备份：`codex/v2-prototype-backup-20260713` / `b583e5a`

## 0. 权威与优先级

- 本规格和 `14-v2-final-implementation-plan.md` 是实施入口，但不缩减 `03-v2-delivery-checklist.md`、`11-core-object-access-recovery-contract.md`、`12-production-proof-slo-and-lifecycle.md` 与 Accepted ADR 0001-0007 的规范性要求。
- ADR 0008 在部署 Profile preflight（许可、区域、网络、Auth、Persistence、HA/SLO、成本、退出）通过前保持 Provisionally Accepted；preflight 通过后必须先改为 Accepted，才能执行 hosted runtime proof。Accepted 不等于 hosted release gate 已通过，本地 Compose 也不能替代真实 hosted 证据。
- 如早期文档与本规格存在状态枚举或职责表达冲突，以本规格的标准 Run 状态、`recovery_status/failure_code`、Checkpoint/Product DB/live projection 三分权威为准；其余更严格要求继续有效。
- 最终 requirement-to-evidence verifier 必须覆盖上述全部规范性来源，不得只检查本文件。

## 1. 目标

V2 Final 是一个多用户加密市场智能 Agent 工作空间。首条必须完整交付的纵向主链是：

```text
ActorContext
  -> 创建 Thread/Task
  -> OKX 真实行情
  -> 真实 Web Search
  -> LangChain create_agent
  -> 官方 Structured Output
  -> 确定性 Evidence Gate
  -> 确定性 Risk Gate
  -> LangGraph interrupt
  -> approve/reject/edit
  -> 产品数据库事务提交
  -> Notification Outbox
  -> 前端实时展示、刷新恢复和历史回看
  -> LangSmith/Langfuse 同一 correlation ID
```

系统只提供人工决策辅助，不自动下单、撤单、转账或提现。

## 2. 重构方式

本次不是全量重写。采用“干净 Runtime 骨架 + 受测试保护的业务迁移”：

### 2.1 迁移并修正

- `MarketAnalysis`、`EvidenceVerdict`、`RiskVerdict` 等领域模型。
- 风控纯函数和有业务价值的单元测试。
- 证据门禁规则，但必须补齐 VIX、10Y real yield、DXY、事件扫描四项硬门禁。
- OKX、Web Search、Bark 的 Provider 请求逻辑，但统一返回验证后的 DTO。
- 分析结果、行情、证据、风险等前端展示组件。
- V1 中已经证明有价值的产品文案和 golden cases。

### 2.2 重建

- Python/Node 精确依赖锁。
- LangChain `create_agent` 工厂、Middleware 和 Structured Output。
- LangGraph canonical graph、Agent Server、Protocol v2 和 HITL。
- 多用户 ActorContext、Resource Auth 和 Store namespace 隔离。
- Product PostgreSQL、Alembic、事务和 Notification Outbox。
- LangSmith/Langfuse 集中观测装配。
- Next.js BFF、`@langchain/react` 根 Runtime 和产品 View Model。
- V2 专用 Playwright、视觉回归和真实链路测试。

### 2.3 删除

- V1 REST Runtime 与 V2 Agent Server 的长期双主链。
- 静态 Home/Inbox/Library/Settings 假数据。
- 页面直接打印完整 Graph State JSON 的产品路径。
- SDK 边界 `as any`。
- 手工 SSE、重连、消息去重和 Thread Store。
- 正则或字符串解析 Structured Output。
- 吞掉 Provider/数据库错误后返回 generic success。
- 仓库内任何真实凭据。

## 3. 锁定技术栈

实施开始时使用以下兼容组，并生成 lockfile；升级必须单独提交 contract test 证据：

### 3.1 Python

| Package | Version |
| --- | --- |
| Python | 3.12.x |
| langchain | 1.3.13 |
| langgraph | 1.2.9 |
| deepagents | 0.6.12 |
| langchain-openai | 1.3.5 |
| langchain-tavily | 0.2.18 |
| langgraph-checkpoint-postgres | 3.1.0 |
| langgraph-cli | 0.4.31 |
| langgraph-api | 0.11.0 |
| langgraph-sdk | 0.4.2 |
| langchain-protocol | 0.0.18 |
| langsmith | 0.10.2 |
| langfuse | 4.14.0 |
| SQLAlchemy | 2.0.51 |
| Alembic | 1.18.5 |
| asyncpg | 0.31.0 |
| FastAPI | 0.139.0 |
| pydantic-settings | 2.14.2 |
| PyJWT | 2.13.0 |

### 3.2 Frontend

| Package | Version |
| --- | --- |
| Node.js | 22 LTS |
| Next.js | 16.2.10 |
| React / React DOM | 19.2.7 |
| TypeScript | 5.9.3 |
| @langchain/react | 1.0.26 |
| @langchain/langgraph-sdk | 1.9.25 |
| @langchain/core | 1.2.2 |
| @langchain/protocol | 0.0.18 |
| Zod | 4.4.3 |
| Playwright | 1.61.1 |
| lucide-react | 1.24.0 |
| next-auth | 4.24.14 |
| jose | 6.2.3 |
| @axe-core/playwright | 4.12.1 |
| react-markdown | 10.1.0 |
| rehype-sanitize | 6.0.0 |

Node/Next/TypeScript 组合必须通过空环境 `npm ci`、typecheck 和 production build。版本升级只能在独立提交中完成，并附 SDK/Protocol contract test 证据。

Agent Server兼容组由 `langgraph-api==0.11.0`、`langgraph-sdk==0.4.2`、`langchain-protocol==0.0.18`、`@langchain/langgraph-sdk==1.9.25`、`@langchain/react==1.0.26` 和 `@langchain/protocol==0.0.18` 共同定义。集成和生产镜像必须把不可变 image digest写入 `artifacts/v2-final/versions.json`；只记录浮动 tag不构成版本证据。`langgraph-api==0.11.0` OpenAPI 的 `ProtocolChannel` 漏列 `checkpoints` 但锁定 Protocol/React Runtime 包含该 channel，必须通过真实 capability probe 和记录的兼容性例外处理；BFF 不得用该漏项 OpenAPI enum 拒绝官方 React 请求。

## 4. 目录结构

```text
backend/
  pyproject.toml
  uv.lock
  langgraph.json
  alembic.ini
  alembic/
  src/crypto_alert_v2/
    agents/          # create_agent/create_deep_agent 工厂
    api/             # /app/* 产品 API 与健康检查
    auth/            # ActorContext、Agent Server auth、AuthZ
    domain/          # 纯领域模型、证据和风控
    graph/           # canonical graph、state、nodes、routes
    observability/   # LangSmith/Langfuse 集中装配和脱敏
    persistence/     # ORM、Repository、UnitOfWork、Outbox
    prompts/         # 版本化 Prompt
    providers/       # OKX、Web Search、Notification adapter
    projections/     # Graph state -> 产品 View Model
  tests/
    unit/
    contract/
    integration/
    real/

frontend/
  src/app/
    api/auth/[...nextauth]/route.ts
    api/agent/[...path]/route.ts
    api/product/[...path]/route.ts
    sign-in/
    work/
    inbox/
    library/
    runs/
    settings/
  src/features/
    agent-runtime/
    analysis/
    evidence/
    interrupts/
    runs/
  src/lib/
    api/
    schemas/
  tests/e2e/
```

每个模块只能有一个明确责任。Agent Factory 不写业务路由；Graph Node 不创建数据库 Session；Repository 不解析模型输出；React组件不解析 Protocol frame。

## 5. 后端边界

### 5.1 Agent Harness

- 市场分析使用 `create_agent`。
- `response_format=MarketAnalysis`，结果只读取 `result["structured_response"]`。
- Agent Factory集中装配模型、Tool、Middleware、Langfuse Callback和 LangSmith metadata。
- Provider SDK重试与 `ModelRetryMiddleware` 只能有一个 retry owner。
- Deep Agents只用于受限研究子图；必须通过官方 `HarnessProfile.excluded_tools` 从模型实际绑定工具中移除 `write_file/edit_file/execute`，并使用 `GeneralPurposeSubagentProfile(enabled=False)` 关闭默认通用子 Agent。仅在配置了显式只读同步 SubAgent 时保留 `task`，并验证只能调用已批准子 Agent；无同步 SubAgent 时排除 `task`。使用非执行 `StateBackend` 并禁止工具直接获得 backend。若锁定 Deep Agents 能力探测无法强制这些约束，Research 显式选择唯一受限 `create_agent` Harness，不同时保留两套。

### 5.2 Canonical Graph

顶层只允许一个生产图：

```text
START
  -> bootstrap
  -> validate_request
  -> [collect_market_snapshot || research_events]
  -> analyze_market
  -> validate_evidence
  -> apply_risk_policy
  -> build_artifact
  -> review_policy
  -> bypass: commit_artifact
  -> required: interrupt_review
  -> approve: commit_artifact
  -> reject: complete_blocked
  -> edit: apply_edits -> revalidate -> interrupt_review
  -> complete
  -> END
```

- `interrupt()` 前不得执行非幂等副作用。
- `review_policy` 由服务端 Workspace/Request 策略决定；本地默认黄金主链为 `bypass`，不强制 Interrupt。强制 HITL 集成/E2E 显式使用 `required`，完整验证 approve/reject/edit/expire。客户 payload 不得越权降低 Workspace 要求。
- `edit` 必须应用到确定性的 `ArtifactEdit` schema，并重新执行 evidence/risk gate。
- Run状态只允许 `queued/running/waiting_human/succeeded/blocked/failed/cancelled`。`degraded` 不是终态，通过 `completion_scope`、`warnings` 和 Artifact completeness表达。
- Orphan/restart 不引入额外 Run 状态：可恢复过程使用 `recovery_status=none/pending/recovering/superseded`，不可恢复使用 `status=failed` + `failure_code=orphaned`。
- Provider调用失败进入分类错误并 fail closed，不能转换成成功 `no_trade`。只有 Provider调用成功、返回合法响应但事实证据仍不足时，Evidence Gate才可以形成可审计的 `no_trade`。

### 5.3 Streaming

- Python进程内：`astream_events(version="v3")` 和 `graph.astream(stream_mode=...)`。
- 服务边界：Agent Server Protocol v2。
- React：一个 Thread一个根 `useStream`。
- 产品持久化只保存稳定投影，不保存每个 wire frame。
- Custom event使用版本化 `custom:<name>`；schema来自锁定协议和 Zod/Pydantic contract。

## 6. 多用户与安全

- 每个 Workspace、Task、Run、Artifact、Evidence、Interrupt、Notification都携带 `tenant_id`、`workspace_id` 和 owner `user_id`。
- 非生产开发身份由服务端注入；生产构建禁止开发身份。
- 最终交付使用 Auth.js 的标准 OIDC Provider 流程；BFF 必须先验证服务端 Session，再为 Agent Server/Product API 签发不超过 60 秒的内部 JWT。
- 内部 JWT 必须包含 `iss/aud/sub/tenant_id/workspace_id/roles/permissions/jti/iat/exp/kid`；后端拒绝过期、未知 `kid`、错误 audience 或与 Membership 不一致的声明。
- 用户只能切换至已有 Membership 的 Workspace；浏览器不得通过自定义 header/payload 选择 tenant、role 或 permission。
- Workspace membership明确记录 `role` 和 permission；资源 visibility只允许 `private/workspace/restricted`。
- `private` 仅 owner可见；`workspace` 对拥有对应 read/write permission的成员可见；`restricted` 只允许显式 principal集合。
- Agent Server resource auth、Product Repository和数据库RLS/查询条件执行同一 ACL规则，不允许只做 owner filter或只在前端隐藏。
- Store的 `put/get/search/delete/list_namespaces` 全部重写 namespace为 `(tenant_id, workspace_id, scope, principal_id, purpose, ...)`；`scope` 仅允许 `private/workspace/restricted`，`principal_id` 必须与 scope 对应为 owner、workspace 或受限 principal 集合的稳定标识。
- Next.js BFF不向浏览器暴露 LangSmith、Langfuse、模型、搜索或通知密钥。
- PII和密钥过滤覆盖模型输出、Tool result、Protocol frame、Thread snapshot、Trace和日志。
- 仓库 secret scan 是提交和 CI硬门禁。

## 7. 数据权威和事务

- Agent Server Checkpoint负责执行恢复，不作为产品查询数据库。
- Product PostgreSQL负责 Workspace、Task、Run Projection、Artifact、Evidence、Decision、Interrupt Projection、Notification Outbox、Feedback和Outcome。
- Task创建后立即写入 Product DB；市场快照、搜索证据、结构化输出、Evidence Verdict和Risk Verdict按阶段幂等提交，避免中途失败丢失已付费结果。
- Artifact、Decision和Outbox必须在同一数据库事务提交。
- Outbox worker负责发送 Bark/Web Push/Email；Graph节点不直接把“调用过发送函数”当作“发送成功”。
- 每个外部副作用使用稳定 idempotency key。
- Alembic migration必须支持空库 upgrade、已有库 upgrade和 downgrade smoke test。
- Reconciler以 Checkpoint执行状态和Product Projection版本为输入，修复“Checkpoint已推进但投影未提交”或“投影已提交但Run状态未推进”的可恢复不一致；不得直接读取或修改Agent Server内部表。
- Internal Alpha 恢复参数冻结为：heartbeat 每 10 秒，30 秒未更新视为 stale，自动恢复最多 2 次，单次 recovery deadline 5 分钟，RTO <= 10 分钟，RPO <= 30 秒。运行投影延迟 <= 5 秒，终态投影延迟 <= 2 秒；超限必须告警并触发 reconciliation。

### 7.1 Durable Command Admission

- 跨刷新/设备需要持久保证的 `submit/respond/cancel_run/cancel_task/retry/fork` 先写入Product `task_commands`。`cancel_run` 只取消当前 Run 并允许后续 Retry；`cancel_task` 同时取消 active Run、将 Task 终止为 cancelled、保留历史并拒绝后续生成命令。
- 每条命令包含 `command_id`、`task_id`、`thread_id`、actor、sequence、payload hash、status、lease owner、lease deadline和idempotency key。
- Dispatcher 以 `thread_id` 作为唯一串行租约键，按同一 Thread 的全局 sequence 派发到官方 Agent Server Run/Command API，并记录官方 run/command 引用。两个 Task 共享 Thread 时也不得并发修改同一 Checkpoint；Scenario Compare 通过新 lineage Thread 并行。
- Product `task_commands` 是唯一持久排队 owner；Dispatcher 只在 Thread 可派发时创建官方 Run，不提前创建 Agent Server pending/enqueued Run。短暂客户端 queue 仅是未承诺的 ephemeral UX。
- 重复、过期、无权限或与当前Interrupt不匹配的命令必须被明确拒绝，不得静默成功。
- 前端使用官方 `AgentServerAdapter` 结构实现 Product Command Bridge：读取/事件流仍代理 Agent Server，Protocol-shaped `run.start/input.respond` 必须先通过 Product command admission 事务，事务提交前不得向 Agent Server 发送命令；后端 Dispatcher 将已准入命令翻译为官方 Runs REST API `runs.create(..., durability=...)`，resume 使用官方 `command` 参数。锁定的 Protocol 0.0.18 虽声明 `state.fork`，但 Agent Server 0.11.0 不实现该命令，因此 fork/time travel 也先进入 Product admission，再通过官方 `run.start`/SDK `forkFrom` 语义和 `config.configurable.checkpoint_id` 创建新的 lineage Run；历史读取使用官方 Thread history API。`cancel_run/cancel_task` 不是 Protocol v2 Command，必须通过独立 Product API：前者在提交后调用官方 Runs cancel API，后者为产品复合事务。
- UI 不直接调用 `useStream.stop()` 取消服务端 Run；取消先写入 Product `cancel_run/cancel_task` 命令，再仅断开当前客户端 stream。
- 产品级 submit 不允许使用 SDK 内存 `multitaskStrategy="enqueue"` 作为持久语义。如 UI 提供短暂本页排队，必须命名为 ephemeral 且不得返回“已提交”；可恢复排队必须在调用 SDK 前先创建 `task_commands`。

## 8. 观测

- LangSmith使用框架自动 Trace，负责 Graph/Agent调试、Dataset、Experiment和Release Gate。
- Langfuse通过一个集中 Callback/OTel入口负责 session、user、cost、latency和运营视图。
- 同一执行使用统一 `correlation_id/thread_id/task_id/run_id`。
- 业务节点不手工创建重复 generation。
- 观测不可用不得阻断业务，但必须产生告警和本地结构化日志。

## 9. 前端产品契约

- `/work` 是首屏实际工作台，不以静态 Landing或调试页作为首页。
- 页面显示人类可读的消息、分析卡片、证据、风险和状态；Raw JSON只对诊断角色开放。
- Checkpointer是执行活性权威，Product PostgreSQL是用户可查询状态权威；`useStream` 只拥有当前连接的live projection。断线、hydration或stream error时，页面先读取Product Task状态，再以同一Thread ID重新附着官方stream。
- 字段所有权必须显式：Product API 独占用户可见业务 status、Artifact/history、Evidence、Decision、command/recovery 状态，并决定 Interrupt 是否仍未解决且可操作；`useStream` 只提供当前执行 messages、Interrupt payload/namespace、lifecycle 和显式命名的 live stage/tool/subagent 字段。React 组件不得直接消费整个 `stream.values` 作为产品 View Model。
- hydration/reconnect 后 Checkpoint state 与 Product projection 冲突时，各字段按上述所有权合并；不得让迟到的 Checkpoint values 覆盖已提交的 Product Artifact/Decision/terminal status。
- HITL按钮只在存在匹配 interrupt ID时可用。
- HITL 控件还必须同时满足 Product Task 未终止、Product Run=`waiting_human`、完整 `(task_id, run_id, interrupt_id, checkpoint_id, response_version)` 与未解决 Product Interrupt Projection 匹配；取消/解决后的迟到 Checkpoint interrupt 不得重新启用按钮。
- `approve/reject/edit` 使用锁定 SDK类型；单个中断传递显式 `interruptId`，同一 checkpoint 的多个中断使用 `@langchain/react` 官方 `respondAll(responsesById)`。
- Thread ID必须持久化并可刷新恢复。
- 移动端使用单列/抽屉/Tab，不允许固定三列被裁切。
- 所有空态、失败、长耗时和重连状态都有明确 UI，不显示伪绿色“已就绪”。

## 10. 真实主链完成定义

只有以下证据全部存在，首条主链才能标记完成：

1. 精确 lockfile可从空环境安装。
2. `langgraph dev` 启动且 `/ok`、Graph schema和 custom routes可访问。
3. PostgreSQL/Redis健康；Alembic已执行。
4. OKX返回真实且经过解析的 ticker/mark/index/order book/candles。
5. Web Search返回真实 URL、发布时间、抓取时间和摘要。
6. 模型调用产生有效 `MarketAnalysis` Structured Output。
7. Evidence/Risk Gate对缺失和冲突证据按规则阻断或降级。
8. 前端收到渐进状态并渲染业务组件，不以 JSON作为主要内容。
9. HITL approve/reject/edit均通过；刷新后可恢复。
10. approve后事务写入 Artifact/Decision/Outbox；reject为 blocked；异常为 failed。
11. Runs/详情/Inbox从Product API读取持久投影。
12. LangSmith与Langfuse可用同一 correlation ID定位调用。
13. Playwright桌面和移动端通过，包含截图、Trace、console和network断言。
14. 真实链路失败不会被 mock/fallback/generic success掩盖。

## 11. 阶段顺序

1. Foundation：依赖、Graph、Agent Server、ActorContext、Schema Contract。
2. Golden Path：OKX、Search、Model、Evidence/Risk、HITL。
3. Persistence：Product DB、Projection、Outbox、History。
4. Observability：LangSmith、Langfuse、脱敏、告警。
5. Product UI：Work、Runs、Inbox、Settings、移动端。
6. Deep Research：受限 Deep Agents和后台长任务。
7. Production Gate：跨租户、安全、恢复、SLO、部署和V1删除。

任何阶段未通过退出条件，禁止并行扩展后续产品功能。
