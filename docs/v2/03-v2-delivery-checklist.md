# V2 最终交付 Checklist

> 状态：Proposed，待用户批准
>
> 原则：主流程优先，但最终产品范围不缩水。所有阶段均通过后才能声明 V2 可交付。

## 0. 设计批准

- [ ] 用户批准产品范围和 manual-only 边界。
- [ ] 用户批准 Agent Server + Next.js BFF 架构。
- [ ] 用户批准 Deep Agents 只用于受限研究域。
- [ ] 用户批准默认开发身份和正式 Auth 后置策略。
- [ ] 用户批准 LangSmith + Langfuse 职责划分。
- [ ] 用户批准 V1 只读归档、业务语义迁移、基础设施实现废弃。
- [ ] 用户批准 C 端 Agent Workspace 定位、产品模式和 Thread/Task/Artifact 第一等对象。
- [ ] 用户批准三层事件架构、Middleware role matrix 和长任务/商业化边界。
- [ ] 用户批准生产治理规范中的部署、数据权威、重试、Outbox、观测去重、保留、安全和量化门槛。
- [ ] 用户批准 AI Elements 或 assistant-ui 的视觉组件 ADR，且 `@langchain/react` 保持唯一 Runtime 状态源。
- [ ] `docs/v2/` 不存在 `TODO`、`TBD` 和模糊完成条件。

完成证据：设计文档提交及用户明确确认。

## 1. Clean V2 Skeleton

- [ ] V2 应用目录不复制 V1 `src/crypto_manual_alert`。
- [ ] Python 使用最新兼容的 LangChain/LangGraph 1.x stable 版本并锁定。
- [ ] Deep Agents 锁定明确 0.x 版本。
- [ ] 前端使用 `@langchain/react` 和 `@langchain/langgraph-sdk`。
- [ ] `langgraph.json` 和单一 canonical graph 可被 `langgraph dev` 加载。
- [ ] PostgreSQL、Redis、Next.js 和 Agent Server 可在本地启动。
- [ ] 固定开发租户/用户能够进入 Runtime Context。
- [ ] LangSmith/Langfuse 可关闭，关闭后主链仍能运行。
- [ ] Import Contracts 和 forbidden-pattern CI 已启用。
- [ ] custom routes 使用 `/app/*`/`/internal/*`，auth-first 且不能覆盖 Agent Server 系统路由。
- [ ] Protocol v2 的 Agent Server/API/Python SDK/JS SDK/React SDK 兼容组已锁定。
- [ ] 第一份实施说明已创建。

完成证据：本地启动命令、health check、Graph schema、开发身份和 CI 输出。

## 2. Agent 主流程

### 2.1 请求与状态

- [ ] `AnalysisRequest` 支持 symbol、horizon、query_text 和 notify。
- [ ] `AnalysisState` 字段和 reducer 有 contract test。
- [ ] 每次运行生成 business ID、thread ID、run ID 和 request ID。
- [ ] Workspace、Thread、Task、Run、Artifact、Interrupt、Checkpoint 和 EventProjection ID/关系固定。
- [ ] queued/running/waiting_human/succeeded/blocked/failed/cancelled 语义固定。
- [ ] 运行、连接和 UI 状态分离，disconnected 不会把后台 Run 标记 failed。
- [ ] 失败不会 fallback 到 V1 或第二套 graph。

### 2.1.1 事件架构

- [ ] Agent/Graph 使用 `streamEvents(..., { version: "v3" })` typed projections。
- [ ] Agent Server 使用 Protocol v2 `/commands` 和 `/stream/events`。
- [ ] 官方 SDK 完成 sequence replay、ordering、deduplication 和 namespace subscription。
- [ ] 固定 channel 不被 custom event 重复实现。
- [ ] `custom:task_progress/artifact/evidence/usage/notification/quality` 均有版本化 schema。
- [ ] 普通 UI 使用 `stream.subagents`，Graph 诊断才使用 `stream.subgraphs`。
- [ ] 产品数据库不逐条保存 token/event frame，只保存稳定投影和业务记录。

### 2.2 真实交易数据

- [ ] BTC/ETH/SOL 首批标的通过真实交易所公共接口。
- [ ] mark、index、ticker、funding、open interest、order book 可验证。
- [ ] source level 和 freshness 入库并展示。
- [ ] 限流、超时、过期、字段缺失和 symbol mismatch 均 fail-closed。
- [ ] Web Search 不能满足 exchange-native 事实门禁。

### 2.3 Web Research

- [ ] Provider capability probe 验证 built-in web search。
- [ ] 不支持 built-in 时使用明确配置的官方搜索 Tool。
- [ ] Deep Agent 只有 search/fetch 只读权限。
- [ ] 启动测试断言 Deep Agent 最终 Tool/Middleware/Permission 清单；默认 Filesystem 栈没有意外暴露。
- [ ] Research subgraph 使用批准的 checkpointer 模式，并通过并行/恢复测试。
- [ ] Model/Tool call limit、retry、timeout 和 recursion limit 生效。
- [ ] Coordinator、Research、Decision、Integration、Eval 使用各自 Middleware matrix。
- [ ] Custom Middleware hooks 和执行顺序有 contract test。
- [ ] 搜索查询、URL、发布时间、抓取时间、摘要和引用完整入库。
- [ ] 搜索不可用时页面明确显示，不生成伪结果。

### 2.4 Agent 分析

- [ ] 使用 `create_agent`，没有自定义 Agent Loop。
- [ ] 使用 Pydantic Structured Output。
- [ ] 输出包含方向、动作、置信度、价格、风险、失效条件和证据引用。
- [ ] 原始 provider payload 不直接成为产品 DTO。
- [ ] 模型、Prompt Version、Token、时延、成本和观测 ID 入库。

### 2.5 确定性门禁

- [ ] Evidence Gate 覆盖来源、freshness、symbol 和冲突。
- [ ] Risk Gate 覆盖 action、entry、stop、target、leverage、risk ratio 和 TTL。
- [ ] 多 confidence cap 取最低值。
- [ ] 模型无法覆盖 blocked 结果。
- [ ] 通知失败不改变 Decision/RiskVerdict。
- [ ] 所有规则是无网络、无数据库、无模型依赖的纯函数测试。

完成证据：Graph integration test、真实 Provider gated test、数据库记录和 LangSmith/Langfuse Trace。

## 3. 持久化与恢复

- [ ] 使用 PostgreSQL，不以 SQLite 作为生产主库。
- [ ] LangGraph Checkpoint 与 app business schema 分离。
- [ ] SQLAlchemy 2.x + Alembic 管理业务表。
- [ ] 所有业务表含 tenant_id，用户资源含 user_id。
- [ ] Repository 读取必须带 ActorContext。
- [ ] `persist_result` 事务与幂等通过并发测试。
- [ ] 外部成本阶段完成后渐进写入幂等业务投影，节点失败前的有效产物可查询。
- [ ] Checkpoint 与业务投影 reconciliation 规则通过故障注入测试。
- [ ] 通知使用事务 Outbox、确定性 message key、租约和 unknown 状态。
- [ ] Agent Server 重启后 Thread 可恢复。
- [ ] 每类 Run 显式设置 sync/async/exit durability，并通过崩溃窗口测试。
- [ ] waiting_human Interrupt 可恢复和响应。
- [ ] Resume 保持同一 Thread/Checkpoint，但生成新的 Run 并记录 `resume_of_run_id`。
- [ ] Retry 新建 Run 并记录 retry_of_run_id。
- [ ] Graph/Middleware/Provider/Repository 的重试所有权不叠加，Task 总预算生效。
- [ ] Model Factory 显式配置 `max_retries`，与 ModelRetryMiddleware 不形成乘法。
- [ ] Checkpoint 表不被产品 Repository 查询。

完成证据：PostgreSQL integration、重启恢复、重复提交和租户隔离测试。

## 4. 前端产品体验

### 4.1 官方 SDK

- [ ] 每个 Thread 只有一个根 `useStream`。
- [ ] 使用官方 submit/stop/respond/history。
- [ ] 浏览器不保存 LangSmith Secret Key。
- [ ] BFF 注入开发/生产身份和 correlation ID。
- [ ] 刷新和网络断线后可重新附着运行中的 Thread。
- [ ] `disconnect()` 不取消后台 Run，重新附着后无消息或 Tool card 重复。
- [ ] `stop()` 取消当前服务端 Run，和 `disconnect()` 有不同控件、确认和状态结果。
- [ ] 首次创建 Thread 后通过 `onThreadId` 持久化 ID，rejoin 使用同一 ID。
- [ ] Subagent selector 只在对应卡片展开/挂载时订阅 scoped stream。
- [ ] 明确区分客户端内存 submission queue 与 Agent Server 持久 worker queue。
- [ ] 使用官方 multitask strategy 和 checkpoint fork，不建立私有 Agent queue/分支 Runtime。

### 4.2 页面

- [ ] Home 有真实 Watchlist、活跃任务、待处理事项和最近报告。
- [ ] Work 可从 Chat/Analysis 模式提交并实时展示阶段。
- [ ] Work 内 Thread/Task 列表只显示当前用户数据。
- [ ] Run/Artifact Detail 首屏展示结论、价格、风险和状态。
- [ ] 模型分析、交易事实、Web Evidence、风险门禁分区展示。
- [ ] Notification 和用户反馈可见。
- [ ] Home、Work、Monitors、Inbox、Library 和 Settings 形成可用闭环。
- [ ] Coordinator conversation、subagent tree 和 Artifact workspace 信息层级清晰。
- [ ] Settings 保留用户级配置钩子。
- [ ] 用户可以查看、删除、关闭和限定长期 Memory；业务设置不写入 LangGraph Store。
- [ ] 商业发布至少支持 In-app Inbox + Web Push/Email 之一，Bark 不作为唯一正式渠道。
- [ ] Admin/Login 后置页面不阻断开发主链。

### 4.3 状态与可访问性

- [ ] 长耗时操作有进度，不允许重复提交。
- [ ] blocked 与 failed 文案和操作不同。
- [ ] Error Boundary、loading、empty、not-found 完整。
- [ ] 键盘、焦点、ARIA、对比度和 reduced-motion 通过检查。
- [ ] 桌面、平板、移动端无横向溢出和内容遮挡。
- [ ] 普通页面无 `<pre>` 原始 JSON、Python repr 和密钥。
- [ ] Markdown 经过 sanitization，危险 URL/HTML 被拒绝。
- [ ] Tool、reasoning、Structured Output、Artifact 和 Generative UI 使用正式 typed component。
- [ ] Reasoning 默认折叠且不宣称展示 chain-of-thought。
- [ ] Generative UI 只能选择白名单组件和 schema-validated props。
- [ ] 图片、音频、视频和文件附件有 loading/error/unsupported 降级。

完成证据：Playwright DOM assertions、visual snapshots、axe/a11y 检查和移动端深滚动截图。

## 5. Human-in-the-loop

- [ ] Interrupt Payload 有版本化 schema。
- [ ] 前端可以 approve/edit/reject。
- [ ] 多个并行 Interrupt 可以 `respondAll()`。
- [ ] Root 与 subagent Interrupt 均保留 interrupt ID 和 namespace。
- [ ] response 与 State 修正需要同时发生时使用原子 respond update。
- [ ] Interrupt 前无非幂等副作用；节点从开头重执行的测试通过。
- [ ] edit 后 Graph 使用用户输入继续，不重跑已完成副作用。
- [ ] reject 形成明确 cancelled/blocked 业务记录。
- [ ] 页面刷新后仍可处理待确认 Interrupt。
- [ ] Inbox 可以处理原对话页之外的待确认动作，并实时同步回 Thread。
- [ ] 开发默认流程不强制 Interrupt，不阻断主链。

完成证据：Agent Server真实 Interrupt/Resume E2E。

## 6. LangSmith

- [ ] 自动 Trace 覆盖 Graph、Node、Agent、Tool 和 Model。
- [ ] tenant/user/thread/run/environment metadata 完整传播。
- [ ] 所有 child runs 含 thread_id/session_id。
- [ ] Prompt Version 可追踪。
- [ ] 建立最小 Dataset：正常、缺数据、过期、冲突、模型错误、通知错误。
- [ ] 离线 Experiment 可重复运行。
- [ ] Release Gate 包含结构、证据、风险和产品输出指标。
- [ ] Sensitive tenant 可 conditional tracing 或隐藏 I/O。

完成证据：LangSmith 项目链接/导出、Dataset ID、Experiment 结果和 release report。

## 7. Langfuse

- [ ] 官方 CallbackHandler 捕获 LangChain/LangGraph 调用。
- [ ] session_id 与 LangGraph thread_id 对齐。
- [ ] user_id 使用内部匿名 ID。
- [ ] Cost、latency、errors、model、tool 和 environment 可查询。
- [ ] Masking 在发送前处理密钥和 PII。
- [ ] Sampling 策略可配置。
- [ ] 明确选择 Langfuse 100%+retention 或统计采样；若采样，failed/blocked/negative-feedback 由 Product Audit/LangSmith 全量保留。
- [ ] Langfuse 不可用时主流程不失败。
- [ ] 没有 Callback + 手工 Generation 重复记录。

完成证据：Langfuse Trace、Dashboard、断网降级测试和去重检查。

## 8. 多用户正式启用

- [ ] 正式 Auth Provider 实现同一 IdentityProvider 契约。
- [ ] Agent Server resource auth 为 Thread/Run/Store 添加 owner/tenant metadata。
- [ ] Next.js Session 到 Agent Server 身份传播通过。
- [ ] 用户 A 不能读取、恢复、取消或反馈用户 B 的 Run。
- [ ] 租户 A 和租户 B 数据库查询隔离。
- [ ] Operator/Admin 权限有独立 action 和 audit event。
- [ ] 开发模式在生产构建中默认关闭。
- [ ] 无 Authorization 时生产请求 fail-closed。

完成证据：双用户/双租户 API、SDK 和 Playwright 安全测试。

## 9. 长任务与商业化基础

### 9.1 Background、Queue、Cron 与 Webhook

- [ ] Background Run 可在页面关闭后继续，Tasks 页面可重新附着。
- [ ] 同一 Thread 运行中追加消息使用官方 queue/multitask strategy。
- [ ] 用户可同时运行多个 Task，取消语义区分 disconnect/run/task/cron。
- [ ] Scheduled Monitor 使用 Agent Server cron，不使用应用进程内 timer。
- [ ] 用户可从 Artifact 创建 Monitor，定义 thesis、条件、频率、有效期、静默时段和渠道。
- [ ] 每次 Monitor 触发创建新的实时 Task，不复用旧结论冒充当前分析。
- [ ] Webhook 有签名、重放保护、幂等和投递审计。
- [ ] 长任务立即确认接收并持续发布 progress/subagent/artifact/evidence。
- [ ] 长任务完成、失败、等待人工进入 Inbox 和配置的通知渠道。

### 9.2 Workspace、Entitlement 与 Usage

- [ ] Workspace、membership、role 和 owner 模型启用。
- [ ] Entitlement 后端控制模式、模型、并发、搜索、存储、保留期和计划任务。
- [ ] Usage ledger 不可变记录 token/cost/search/runtime/storage/notification。
- [ ] Quota 超限返回稳定错误和升级入口，不以模型文本表示。
- [ ] 外部 customer/subscription/price reference 可保存并审计。
- [ ] Payment、税费、发票和支付方式不在 Agent Runtime 自研。
- [ ] OAuth/Integration secret 使用专用 secret store，不进入 State/Prompt/Trace。

完成证据：background/rejoin/queue/cron/webhook E2E、双 workspace entitlement 测试、usage reconciliation 和 secret scan。

## 10. V1 迁移与清理

- [ ] V2 production code 不 import V1 workflow/agent_swarm/orchestration。
- [ ] V1 业务规则逐条迁移并有 golden test。
- [ ] V1 SQLite 保持只读或一次性 ETL。
- [ ] 没有永久双写 V1/V2。
- [ ] 没有 legacy/candidate/controlled mode switch。
- [ ] 没有 fallback 回 V1 Prompt/Workflow。
- [ ] V1 历史页面明确标记 legacy archive。
- [ ] 旧代码删除清单完成并经 `rg`/import test 验证。

完成证据：静态 import gate、golden tests、ETL report 和删除 diff。

## 11. 自动化 QA

- [ ] Backend unit/integration 全通过。
- [ ] Frontend lint/typecheck/build 全通过。
- [ ] Playwright desktop/mobile 全通过。
- [ ] Visual snapshot 无未审查更新。
- [ ] API Schema/Zod contract 全通过。
- [ ] Graph resume/retry/interrupt/cancel 全通过。
- [ ] Protocol v2 sequence replay、重复 frame、乱序保护和 scoped namespace 测试通过。
- [ ] Queue、fork、time travel、subagent nested/error 和 Artifact version 测试通过。
- [ ] Provider timeout/rate-limit/malformed-output 全通过。
- [ ] Observability outage 不阻断测试通过。
- [ ] Secret scan、dependency audit 和 container scan 通过。
- [ ] 负载测试覆盖并发 Run、长研究和流式连接。
- [ ] 视觉回归覆盖桌面/移动端、深滚动、长文本、动态高度、折叠/展开和重连过程。
- [ ] DOM 深度扫描覆盖重叠、横向溢出、焦点丢失、重复 ID、不可点击控件和错误 aria。

完成证据：CI run、HTML report、trace/video on failure、benchmark report。

## 12. 真实生产证明

- [ ] 公网 HTTPS Next.js 与 Agent Server 可访问。
- [ ] PostgreSQL/Redis 使用持久化和备份。
- [ ] 真实 OpenAI-compatible 模型 Structured Output 成功。
- [ ] 真实 Web Search 返回可验证来源。
- [ ] 真实交易所公共数据满足 exchange-native freshness。
- [ ] 同一次 Run 的模型、行情、搜索、风险、持久化和 Bark 均成功。
- [ ] 同一真实长任务经历断线、后台继续、重连 replay 和完成通知，无重复内容。
- [ ] 同一真实 Run 展示 coordinator、subagent、Tool、Artifact、Evidence 和 Risk 正式组件。
- [ ] Desktop/Mobile hosted visual gate 使用同一真实 Run。
- [ ] 生产错误、超时和恢复演练通过。
- [ ] 至少一个成熟 outcome 被收集和评分。
- [ ] no-trade baseline 和金融指标可查看。
- [ ] Runbook、告警、备份恢复和密钥轮换文档完成。
- [ ] 真实用户/Workspace entitlement、quota 和数据隔离完成安全演练。

完成证据：同一 Run ID 的 API、页面、数据库、通知、LangSmith、Langfuse 和 outcome 证据包。

## 13. 最终完成定义

只有满足以下全部条件才可以声明“V2 最终版本完成”：

- [ ] 第 0-12 节所有 Checklist 均完成。
- [ ] 没有被跳过的 P0/P1。
- [ ] 没有用 mock/local proof 替代 hosted real proof。
- [ ] 没有隐藏失败、空 JSON、generic success 或 fallback success。
- [ ] 没有未批准的自定义 Runtime/Wrapper。
- [ ] 用户可以从浏览器真实完成主流程并读懂结果。
- [ ] 用户体系启用后不需要重写 Graph、表结构和产品 DTO。
- [ ] Deep Research、Scheduled Monitor、Inbox、Outcome Review 和 Scenario Compare 可以在现有 Thread/Task/Artifact/Event 架构上增量启用，不需要第二套 Runtime。
- [ ] 文档、中文注释、实施说明和 Runbook 足以让新维护者排障。
