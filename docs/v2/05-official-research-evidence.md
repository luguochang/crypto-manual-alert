# V2 官方文档调研证据矩阵

> authority_class: verified_evidence_index
>
> 调研日期：2026-07-12
>
> 分类：Verified evidence index（提供官方来源证据，不单独新增产品规范）
>
> 来源限制：只引用 LangChain、LangGraph、Deep Agents、LangSmith、Langfuse 官方文档、官方 GitHub 仓库和官方包注册表。
>
> 使用方式：实施每个阶段前重新核验对应链接和锁定版本；本文不是永久版本保证。

## 1. 版本与稳定性

| 结论 | 官方证据 | V2 决策 |
| --- | --- | --- |
| LangChain/LangGraph 1.0 是 LTS | [Versioning](https://docs.langchain.com/oss/python/versioning) | 生产主链使用 1.x stable API |
| Stable API 保持 major 内向后兼容 | [Versioning - API stability](https://docs.langchain.com/oss/python/versioning#api-stability) | 禁止依赖 `_` internal API |
| Deep Agents 是 pre-1.0，minor 版本可能变化 | [Versioning - pre-1.0](https://docs.langchain.com/oss/python/versioning#pre-1-0-packages) | 锁定版本并隔离在 ResearchBundle 边界 |
| 2026-07-11 PyPI `langchain` 为 1.3.13 | [PyPI](https://pypi.org/project/langchain/) | 实施时重新读取并生成 lockfile |
| 2026-07-11 PyPI `langgraph` 为 1.2.9 | [PyPI](https://pypi.org/project/langgraph/) | 实施时重新读取并生成 lockfile |
| 2026-07-11 PyPI `deepagents` 为 0.6.12 | [PyPI](https://pypi.org/project/deepagents/) | 禁止宽松 `>=` 无上界升级 |
| 2026-07-11 NPM `@langchain/react` 为 1.0.26 | [NPM Registry](https://registry.npmjs.org/%40langchain%2Freact/latest) | 前端采用 v1 API，不复制旧 hook |
| 2026-07-12 NPM `@langchain/protocol` 为 0.0.18 | [NPM Registry](https://registry.npmjs.org/%40langchain%2Fprotocol/latest) | 仍为 pre-1.0，必须锁定并做 OpenAPI/SDK schema contract test |

## 2. LangChain Agent Framework

### 2.1 `create_agent`

官方事实：

- Agent 是 Model + Harness，核心是模型调用 Tool 的循环。
- `create_agent` 是官方高度可配置 Harness。
- Model、Tools、System Prompt 和 Middleware 直接传给 factory。

来源：

- [Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [`create_agent` API](https://reference.langchain.com/python/langchain/agents/factory/create_agent)

V2 采用：

- 市场分析 Agent 使用 `create_agent`。
- 不再实现 `AgentRunner`、Agent Loop、Tool dispatch 和通用 result envelope。
- Agent Factory 只负责注入模型、Tool、Prompt、Structured Output 和 Middleware。

### 2.2 `create_agent` 与 LangGraph 的关系

官方事实：

- LangChain 建立在 LangGraph 之上。
- Middleware hooks 运行在 `create_agent` 返回的 compiled LangGraph 内。
- 整个 Agent 可以作为更大 StateGraph 的 Node 或 Subgraph。

来源：

- [Middleware - use inside LangGraph](https://docs.langchain.com/oss/python/langchain/middleware#use-middleware-inside-a-langgraph-workflow)
- [Products](https://docs.langchain.com/oss/python/concepts/products)

V2 采用：

- 顶层使用显式 StateGraph。
- `create_agent` 作为分析 Node，不在外面再包一层 Agent Runtime。

### 2.3 Structured Output

官方事实：

- `create_agent(response_format=...)` 支持 Pydantic、dataclass、TypedDict 和 JSON Schema。
- LangChain 根据模型能力选择 ProviderStrategy 或 ToolStrategy。
- 最终校验结果位于 Agent State 的 `structured_response`。
- `strict` 能力和最低版本要求必须按 Provider 核验。

来源：

- [Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output)

V2 采用：

- `ResearchBundle`、`DecisionDraft`、`SpecialistFinding` 使用 Pydantic。
- 禁止从自然语言中用正则截 JSON。
- Provider capability probe 决定是否允许 strict/provider-native 模式。

### 2.4 Prebuilt Middleware

官方当前提供：

- Summarization。
- Human-in-the-loop。
- Model call limit。
- Tool call limit。
- Model fallback。
- PII detection。
- Todo list。
- LLM tool selector。
- Tool retry。
- Model retry。
- LLM tool emulator。
- Context editing。
- Provider tool search。
- Shell tool、File search / Filesystem。
- Subagent。
- Rubric grading，当前 beta。

来源：

- [Prebuilt Middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)

V2 采用：

- 预算、重试、PII 和 HITL 优先使用官方 Middleware。
- 禁止复制 V1 `ToolBudget`、统一 retry shell 和 PII 最后端字符串过滤。
- Model fallback 默认不用于最终风险主链，避免不同模型静默改变决策语义。
- Middleware 必须按 Coordinator、Research、Decision、Integration 和 Eval 角色装配，而不是把所有 Middleware 全局堆叠。
- Tool emulator 只用于测试；Shell/Filesystem 在当前生产产品禁用；Rubric 只提供评测信号。

### 2.5 Custom Middleware

官方事实：

- Node-style hooks：`before_agent`、`before_model`、`after_model`、`after_agent`。
- Wrap-style hooks：`wrap_model_call`、`wrap_tool_call`。
- Middleware 可以声明 state、tools 和 scope-aware stream transformers。
- before hooks 正序执行，after hooks 逆序执行，wrap hooks 嵌套执行。

来源：

- [Custom Middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)

V2 采用：

- 租户权限、entitlement、usage、证据引用完整性等领域扩展只能通过官方 hooks 实现。
- Middleware 顺序必须有 contract test，禁止依赖未记录的偶然顺序。
- Stream transformer 用于 typed business extension，不创建第二套 EventBus。

## 3. LangGraph Runtime

### 3.1 定位

官方事实：

- LangGraph 是低层编排框架和 Runtime。
- 核心能力是 Durable Execution、Streaming、Human-in-the-loop 和 Persistence。
- LangGraph 不负责 Prompt 或固定 Agent 架构。

来源：

- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)

V2 采用：

- LangGraph 拥有唯一生产主图、节点路由、并行、恢复和中断。
- 领域规则保持普通 Python，不塞进 Prompt。

### 3.2 Checkpointer 与 Store

官方事实：

- Checkpointer 保存单个 Thread 的 Graph State Snapshot，用于短期记忆、HITL、time travel 和 fault tolerance。
- Store 保存跨 Thread 的应用数据，用于长期记忆。
- 调用 Graph 时通过 `configurable.thread_id` 绑定 Thread。
- InMemorySaver 不能用于重启后持久化。
- Agent Server 自动处理 persistence infrastructure。

来源：

- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [Stores](https://docs.langchain.com/oss/python/langgraph/stores)

V2 采用：

- Agent Server 管 Checkpoint/Store；如果自管 Runtime，使用官方 PostgreSQL Checkpointer。
- 产品业务记录使用独立 SQLAlchemy schema，不查询 Checkpoint 表。
- `thread_id` 使用 UUID，避免超长和跨租户冲突。
- 传统 Run API/进程内调用可选择 `sync`、`async` 或 `exit`；当前 Protocol v2 `run.start` 和 React `submit()` 不暴露该字段，UI 路径必须记录服务端有效默认值，不能虚构 per-run 配置。
- Research subgraph 默认 `checkpointer=None` 继承父图；per-thread persistence 需要单独批准和并行限制。

### 3.3 Interrupt / Resume

官方事实：

- `interrupt(payload)` 暂停执行并返回 resumable interrupt。
- 使用 `Command(resume=...)` 或 SDK command 恢复。
- Server API、Python SDK、JavaScript SDK 均支持。

来源：

- [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Human-in-the-loop using server API](https://docs.langchain.com/langsmith/add-human-in-the-loop)

V2 采用：

- 所有人工批准使用官方 Interrupt。
- 禁止自建 pending action polling 和恢复状态机。

### 3.4 Streaming

官方事实：

- Python LangChain/Deep Agents 当前提供 `stream_events/astream_events(version="v3")`，Python LangGraph 同时提供 `stream/astream` 与 `stream_mode`；JavaScript 对应 camelCase `streamEvents`。
- 通用 projection 包括 messages、toolCalls、values、output、subgraphs 和 extensions。
- Deep Agents 额外提供 `stream.subagents`，每个 handle 具有 name、taskInput、messages、toolCalls、values、nested subagents 和 output。
- `stream.subagents` 表达产品级 task delegation；`stream.subgraphs` 表达 Graph execution structure。
- Agent Server Protocol v2 通过 command endpoint 启动后台 Run，通过 event endpoint 观察事件。
- Event endpoint 按 channel/namespace/depth 订阅，并通过 `since` sequence replay 重连。
- Protocol v2 SSE endpoint 是 POST-only，浏览器原生 `EventSource` 自动恢复不适用。

来源：

- [LangChain Event Streaming](https://docs.langchain.com/oss/javascript/langchain/event-streaming)
- [LangGraph Event Streaming](https://docs.langchain.com/oss/javascript/langgraph/event-streaming)
- [Deep Agents Event Streaming](https://docs.langchain.com/oss/javascript/deepagents/event-streaming)
- [Protocol v2 Command](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-command)
- [Protocol v2 Event Stream](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-event-stream-sse)

V2 采用：

- Python 进程内使用 Event Streaming v3 与 `astream/stream_mode`，Agent Server 使用 Protocol v2，React 使用 SDK selectors；实现必须使用对应语言的正确方法名。
- Token/Message、Tool、lifecycle、input、tasks 和 checkpoint pointer 使用锁定协议版本提供的官方 channel；具体集合由 OpenAPI/protocol types contract test 决定。
- 阶段进度、Artifact、Evidence、Usage、Notification 和 Quality 使用版本化 `custom:<name>` extension。
- 不手写 SSE reconnect、sequence replay、dedup、namespace parser、chunk assembler 和 run polling。
- 产品数据库不逐条保存 wire frame，只保存稳定业务投影。

## 4. Deep Agents

### 4.1 与 LangChain/LangGraph 的真实关系

官方事实：

- `deepagents` 是独立库，建立在 LangChain Agent building blocks 之上。
- 使用 LangGraph Runtime 提供 durable execution、streaming 和 HITL。
- 它是 Harness，增加 planning、filesystem、subagent 和 context management。

来源：

- [Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Products](https://docs.langchain.com/oss/python/concepts/products)

V2 采用：

- 不把三者写成同一个库，但利用它们的正式层次关系。
- Deep Agent 作为研究 Subgraph，输出窄的 `ResearchBundle`。

### 4.2 `create_deep_agent`

官方公开参数包含 Model、Tools、System Prompt、Subagents、Middleware、Backend、Permissions、Checkpointer 和 Store 等。

官方默认栈还会装配 Filesystem、Subagent、Summarization 和 Patch Tool Calls 等 Middleware/Tools，不能通过省略参数推断已关闭。

来源：

- [Customization](https://docs.langchain.com/oss/python/deepagents/customization)
- [`create_deep_agent` API](https://reference.langchain.com/python/deepagents/graph/create_deep_agent)

V2 采用：

- 只配置 search/fetch tools 和受限 subagents。
- 不启用代码执行和产品仓库写入。
- 通过官方 Middleware 限制模型/Tool 调用。
- 启动测试断言最终 Tool/Middleware/Permission 清单；完全禁用 filesystem 时允许改用 `create_agent` Research Harness。

### 4.3 Permissions 的限制

官方事实：

- `permissions=` 只覆盖 built-in filesystem tools。
- 自定义 Tool、MCP Tool 和 sandbox arbitrary execute 不自动受 filesystem permission 保护。
- 默认未匹配规则可能允许，因此规则顺序和 deny-all tail 很重要。

来源：

- [Deep Agents Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)

V2 采用：

- 最安全策略是不向 Research Agent 暴露 filesystem/sandbox tools。
- 所有自定义/MCP Tool 仍要单独权限和审计，不能误以为 `permissions=` 已覆盖。

## 5. OpenAI-compatible 与 Web Search

官方事实：

- `ChatOpenAI` 支持 Tool Calling、Structured Output 和 Responses API。
- 当使用 Responses 特性时，可通过 `{"type": "web_search"}` 启用 built-in web search。
- OpenAI-compatible endpoint 是否实现该能力不能由 URL 推断。

来源：

- [ChatOpenAI Integration](https://docs.langchain.com/oss/python/integrations/chat/openai)

V2 采用：

- 用户配置的兼容 endpoint 直接通过 `ChatOpenAI(base_url=...)` 接入，不写私有 LLM Client。
- 启动 capability probe 实测 Tool、Structured Output、Streaming 和 Web Search。
- Web Search 不支持时显式切换到批准的 LangChain 官方 Tool，不做静默 fallback。

## 6. 官方前端和人机交互

### 6.1 `@langchain/react`

官方仓库当前事实：

- v1 提供 v2-native `useStream`。
- 支持自动 re-attach、Thread state、Messages、Tool Calls、Interrupts、Submission Queue、Subagents、Subgraphs、Media 和 custom transport。
- 推荐每个 Thread 挂载一个 root hook，其余使用 selector hooks。
- 根 stream 提供 submit、stop、disconnect、respond、respondAll 等控制能力。
- `useExtension`、`useChannel` 和 `useChannelEffect` 分别适合最新 typed projection、原始有界时间线和无 rerender side effect。
- Subagent snapshot 仅用于 discovery；`useMessages/useToolCalls/useValues(stream, subagent)` 在组件挂载时懒订阅 scoped stream。

来源：

- [`@langchain/react` README](https://github.com/langchain-ai/langgraphjs/tree/main/libs/sdk-react)
- [React SDK docs](https://github.com/langchain-ai/langgraphjs/tree/main/libs/sdk-react/docs)

V2 采用：

- 直接使用 `@langchain/react` v1。
- 使用官方 queue、multitask strategy、forkFrom、checkpoint history 和 media selector。
- Agent Chat UI 只作为产品交互参考，不照搬其中可能较旧的 import 和版本。

### 6.2 LangGraph JavaScript SDK

官方仓库当前事实：

- SDK 管理 assistants、threads、runs、crons 和 store。
- 新版推荐 Thread-centric streaming；旧 generator streaming API 标记为兼容保留。
- 默认 SSE，可切 WebSocket 或 custom AgentServerAdapter。

来源：

- [LangGraph JS SDK](https://github.com/langchain-ai/langgraphjs/tree/main/libs/sdk)

V2 采用：

- 新代码使用 Thread-centric/React v1 接口。
- 禁止按旧教程新写 `joinStream/reconnectOnMount` 状态机。
- 禁止直接使用原生 EventSource 连接 Protocol v2 POST endpoint。

### 6.3 Agent Chat UI

官方仓库事实：

- 是连接带 `messages` key 的 LangGraph Server 的 Next.js UI。
- 支持 Thread、流式消息、Tool、Artifact 和生产 API proxy 参考。
- README 明确生产浏览器不能要求每个用户持有 LangSmith API Key，应使用 server-side proxy/auth。

来源：

- [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui)

V2 采用：

- 借鉴 Thread UI、Tool 状态、Artifact 和 BFF 方式。
- 不把通用聊天页面直接当成交易决策产品；业务结果使用专门组件。

### 6.4 官方 Frontend Patterns 与集成

官方文档覆盖：

- Markdown messages、Tool calling、Reasoning tokens、Structured Output。
- Generative UI、Human-in-the-loop、Headless tools。
- Join/Rejoin、Message queues、Branching chat、Time travel。
- AI Elements、assistant-ui、CopilotKit 和 OpenUI 集成。

来源：

- [Frontend Overview](https://docs.langchain.com/oss/javascript/langchain/frontend/overview)
- [Frontend Integrations](https://docs.langchain.com/oss/python/langchain/frontend/integrations/overview)
- [Deep Agents Subagent Streaming](https://docs.langchain.com/oss/javascript/deepagents/frontend/subagent-streaming)

V2 采用：

- `@langchain/react` 保持唯一 Runtime 状态源。
- AI Elements 或 assistant-ui 只作为视觉/交互组件层，实施前 ADR 二选一。
- Generative UI 使用受控组件注册表，不执行任意 JSX。
- Reasoning 只展示 Provider 返回且允许显示的 block/summary。
- Headless browser/device tool 默认禁用，未来启用必须 sandbox、allowlist、HITL 和审计。

### 6.5 长任务与异步能力

官方事实：

- `run.start`、`input.respond` 创建后台执行。
- Agent Server 提供 background runs、crons 和 webhook 相关能力。
- Submission queue 和 multitask strategy 处理运行中追加输入。
- Checkpoint/fork/time travel 支持编辑、重新生成和分支比较。

来源：

- [Background Runs](https://docs.langchain.com/langsmith/background-run)
- [Cron Jobs](https://docs.langchain.com/langsmith/cron-jobs)
- [Time Travel](https://docs.langchain.com/langsmith/human-in-the-loop-time-travel)

V2 采用：

- 页面断开不取消后台 Task。
- Scheduled Monitor 使用官方 Cron，不使用应用进程 timer。
- Inbox 是 Interrupt/Task 的产品投影，不成为第二权威状态。
- 编辑和重生成使用 checkpoint fork，不覆盖历史结果。

## 7. Agent Server Auth 与默认用户

官方事实：

- Agent Server `Auth` 支持 authentication handler 和 resource authorization handler。
- authorization handler 可给 Thread/Run 等资源加入 owner metadata 并返回查询 filter。
- Runtime Config 可获得 authenticated user ID。
- Run 读取/列表权限继承父 Thread；`threads.create_run` 负责 Run admission。
- Store 隔离需要后端重写 namespace，不能只依赖 metadata filter。

来源：

- [Authentication and access control](https://docs.langchain.com/langsmith/auth)
- [Make conversations private](https://docs.langchain.com/langsmith/resource-auth)

V2 采用：

- 开发模式返回固定 `ActorContext`，让主流程先跑通。
- 正式模式替换 handler，不修改 Graph State 或业务 DTO。
- 即使开发模式也写入 tenant/user 字段，防止后期数据库重构。
- custom routes 启用 auth-first，使用 `/app/*`/`/internal/*`，禁止覆盖 Agent Server 系统路径。

## 8. LangSmith

### 8.1 自动 Trace

官方事实：

- LangChain/LangGraph 可通过环境变量启用 LangSmith tracing。
- Metadata 和 Tags 可在 invocation/tracing context 中注入。

来源：

- [Tracing Quickstart](https://docs.langchain.com/langsmith/observability-quickstart)
- [Metadata and Tags](https://docs.langchain.com/langsmith/add-metadata-tags)

V2 采用：

- 使用自动 Trace，不在每个 Node 手工创建重复 Run。
- 注入内部 tenant/user/thread/run/environment metadata。

### 8.2 Thread 聚合

官方事实：

- 使用 `session_id` 或 `thread_id` metadata 聚合多次 Trace。
- Thread metadata 必须传播到 child runs，否则 token/cost/filter 不完整。

来源：

- [Threads](https://docs.langchain.com/langsmith/threads)

V2 采用：

- 所有 LangChain child runs 传播同一 LangGraph thread ID。

### 8.3 多租户和隐私

官方事实：

- `tracing_context` 支持按请求开关、不同 project、metadata 和 I/O redaction。
- 官方文档明确列出 per-tenant configuration 和 sensitive operations 场景。

来源：

- [Conditional Tracing](https://docs.langchain.com/langsmith/conditional-tracing)
- [Data Storage and Privacy](https://docs.langchain.com/langsmith/data-storage-and-privacy)

V2 采用：

- 租户隐私策略在 request scope 决定，而不是全局 mutable client。
- 零保留租户可禁用 Trace 或隐藏输入输出。

## 9. Langfuse

### 9.1 LangChain/LangGraph Callback

官方事实：

- Langfuse 通过 LangChain 标准 CallbackHandler 自动捕获 LLM、Tool、Retriever 和 Agent 调用。
- LangGraph 使用相同 callback 方式。
- Deep Agents 也有官方集成示例。

来源：

- [LangChain & LangGraph Integration](https://langfuse.com/integrations/frameworks/langchain)
- [Deep Agents Integration](https://langfuse.com/integrations/frameworks/langchain-deepagents)

V2 采用：

- 每次 Graph invocation 注入一个 Langfuse CallbackHandler。
- 不同时手工创建重复 generation。

### 9.2 Session、User、Trace

官方事实：

- `session_id` 聚合跨 Trace 会话。
- 支持 deterministic/custom Trace ID 和分布式 Trace。
- 支持 user ID、tags 和 metadata 传播。

来源：

- [Sessions](https://langfuse.com/docs/observability/features/sessions)
- [Trace IDs and Distributed Tracing](https://langfuse.com/docs/observability/features/trace-ids-and-distributed-tracing)

V2 采用：

- `session_id = LangGraph thread_id`。
- `user_id` 使用内部 UUID，不发送邮箱。
- request ID 用于跨 Next.js/Agent Server/Provider 关联。

### 9.3 Masking 与 Sampling

官方事实：

- Mask function 在数据发送前处理 input、output 和 metadata。
- Sampling 在 Trace 级进行，被采样的 Trace 保留全部 observations/scores。
- Head sampling 在 Trace 创建时决定，不能在 Run 结束后把 failed/blocked Trace 补采回来。
- JS/TS SDK 尊重 OpenTelemetry sampling。

来源：

- [Masking](https://langfuse.com/docs/observability/features/masking)
- [Sampling](https://langfuse.com/docs/observability/features/sampling)

V2 采用：

- 密钥和 PII 在出口前脱敏。
- Langfuse 选择 100%+retention 或统计采样；若采样，失败、blocked、负反馈和 release proof 由 Product Audit/LangSmith 全量保留。

## 10. 成熟 C 端 Agent 参考

| 官方/开源项目 | 已验证能力 | V2 采用边界 |
| --- | --- | --- |
| [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) | Thread、Tool、Markdown、Artifact、Interrupt、API proxy | 借鉴交互，不把通用 Chat 直接当最终产品 |
| [Deep Agents UI](https://github.com/langchain-ai/deep-agents-ui) | Todo、Subagent、审批、文件/Artifact、checkpoint rerun | 只作 UX 参考，不复制旧 SDK API |
| [Open SWE](https://github.com/langchain-ai/open-swe) | 长任务、运行中追加消息、并行任务、持久 sandbox、集成 | 借鉴任务模型，不引入代码写权限 |
| [Open Canvas](https://github.com/langchain-ai/open-canvas) | Chat + Artifact、版本、记忆、快速动作 | 借鉴 Artifact，不变成文档编辑器产品 |
| [Agent Inbox](https://github.com/langchain-ai/agent-inbox) | 异步 HITL Inbox、accept/edit/respond/ignore | Inbox 只做官方 Interrupt 投影 |
| [Agent Auth Payments](https://github.com/langchain-ai/agent-auth-payments) | Auth、Stripe、credits、RLS、web/agents 分离 | 借鉴商业边界，不复制示例账本 |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | 多 Provider、搜索/MCP、研究配置、Dataset eval、计划批准 | 借鉴研究与评测，保留本项目风险门禁 |

这些参考共同说明成熟 C 端 Agent 不是单一聊天框，而是 Thread、Task、Inbox、Artifact、Subagent、HITL、长任务、设置、权限和反馈组成的工作空间。

## 11. V1 审计证据

只读仓库审计确认：

- V1 `pyproject.toml` 没有 LangChain/LangGraph。
- 手写主链位于 `workflow/legacy_decision_workflow.py`。
- 自定义 Agent runtime 位于 `agent_swarm/` 和 `orchestration/`。
- 自定义 research planner/executor 位于 `research_pipeline/`。
- 多套模型 HTTP 客户端分布在 `decision/final_engine.py`、`research_pipeline/llm_support.py`、`agent_swarm/shadow_llm_client.py` 和 realtime search provider。
- 最新 migration 仍未完成 hosted prod-actionable、真实 Bark、hosted visual proof 和 matured outcome。

V2 结论：迁移业务规则和 golden cases，不迁移上述 Runtime 实现。

## 12. 调研限制与诚实边界

- 本次完整扫描 `https://docs.langchain.com/llms.txt` 的文档索引，并深读所有与 V2 架构直接相关的页面族；没有声称逐字阅读每个无关的管理后台/API Reference 页面。
- 官方事实由官方 Markdown、API Reference、GitHub README、PyPI 和 NPM 注册表交叉核对。
- 官方示例仓库可能滞后于 SDK，因此产品模式可参考，API 必须以锁定版本的 docs/types/changelog 为准。
- 实施前仍需再次读取官方 Changelog，因为 Deep Agents 和前端 SDK 更新速度较快。
- 完整覆盖方法和实施前复核清单见 `07-official-doc-coverage-index.md`。
