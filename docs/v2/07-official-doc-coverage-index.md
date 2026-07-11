# V2 LangChain 官方文档覆盖索引

> 状态：Proposed，待用户批准
>
> 基线日期：2026-07-11
>
> 入口：[LangChain documentation index](https://docs.langchain.com/llms.txt)

## 1. 覆盖方法

`llms.txt` 是 LangChain 全站文档索引，包含 OSS Framework、LangSmith Deployment、API Reference、CLI、管理后台和大量与本产品无关的平台接口。正确的“完整读取”不是把每个 billing/admin endpoint 机械复制到设计中，而是：

1. 完整扫描 `llms.txt` 的页面清单，建立文档族 inventory。
2. 对与 V2 架构、产品、运行时、安全和商业化直接相关的文档逐页深读。
3. 对间接相关页面记录采用条件和排除理由。
4. 对纯平台管理、重复语言版本和无关 API Reference 标记 out-of-scope。
5. 实施每个切片前重新读取对应页面、API Reference、Changelog 和 Migration Guide。

本文件防止两类问题：遗漏高级官方能力，以及只看旧示例后照抄过时 API。

## 2. 文档族覆盖

| 文档族 | 覆盖级别 | V2 结论 |
| --- | --- | --- |
| LangChain Agents/Models/Messages/Tools | 深读 | Agent loop、模型、Tool、消息使用官方 API |
| Structured Output | 深读 | Decision/Research 输出使用 Pydantic/JSON Schema 策略 |
| Built-in/Custom Middleware | 深读 | 按 Agent role 组装，领域扩展只用官方 hooks |
| LangChain Event Streaming | 深读 | 进程内统一 `streamEvents(..., version v3)` |
| LangGraph Graph/Persistence/Interrupts | 深读 | canonical graph、checkpoint、store、HITL |
| LangGraph Event Streaming | 深读 | typed projection、custom transformer、namespace |
| Deep Agents | 深读 | 研究、subagent、context 管理；权限严格限制 |
| Deep Agents Event/Frontend Streaming | 深读 | `stream.subagents` 与 scoped selectors |
| LangChain Frontend Patterns | 深读 | message/tool/reasoning/structured output/generative UI/HITL |
| React/JS SDK repository docs | 深读 | `useStream` v1、selectors、queue、media、fork、channels |
| Agent Server Protocol v2 | 深读 | command/event POST、background run、sequence replay |
| Agent Server Auth/Resource Auth | 深读 | identity、owner/tenant metadata 和后端过滤 |
| Background Runs/Crons/Webhooks | 深读 | 长任务、计划任务、完成通知和集成 |
| LangSmith Observability/Evaluation | 深读 | tracing、threads、dataset、feedback、release gate |
| LangSmith Billing/Admin APIs | 选择性 | 仅理解部署账户边界，不作为产品 billing 实现 |
| A2A/MCP/OAuth | 选择性 | 保留未来集成边界，不进入首条主流程 |
| Fleet/Managed Deep Agents | 选择性 | 作为托管部署能力参考，不绑定核心业务模型 |
| 重复 Python/JavaScript 页面 | 交叉核对 | Python 负责后端实现，JS 负责事件与前端 SDK |
| 无关 API Reference | Out-of-scope | 不影响 V2 设计，实施涉及时再纳入 |

## 3. Agent 与 Runtime

### 3.1 LangChain Agent

- [Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output)
- [Models](https://docs.langchain.com/oss/python/langchain/models)
- [Tools](https://docs.langchain.com/oss/python/langchain/tools)

强制结论：

- 使用 `create_agent`，禁止自定义 Agent while-loop。
- 模型通过 LangChain Provider integration，禁止通用私有 LLM Client。
- Tool 使用官方 schema 和 ToolRuntime，禁止自定义 envelope/registry protocol。
- 最终输出使用 Structured Output；领域风险 gate 仍为确定性纯函数。

### 3.2 LangGraph Runtime

- [Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)

强制结论：

- 全系统只有一个 canonical graph。
- Checkpoint 管执行恢复，Store 管跨 Thread 记忆，业务表管产品查询。
- Interrupt/Resume 使用官方 Command 和 Server API。
- 并行使用 Graph branch/`Send`，禁止 ThreadPool Agent Runtime。
- Run 显式选择 durability；subgraph 明确 per-invocation/per-thread persistence，不能依赖默认值。
- Interrupt 恢复从节点函数开头重执行，副作用和非确定性操作必须拆分。

## 4. Event Streaming

### 4.1 进程内 Event Streaming v3

- [LangChain Event Streaming](https://docs.langchain.com/oss/javascript/langchain/event-streaming)
- [LangGraph Event Streaming](https://docs.langchain.com/oss/javascript/langgraph/event-streaming)
- [Deep Agents Event Streaming](https://docs.langchain.com/oss/javascript/deepagents/event-streaming)

当前官方主接口：

```ts
const stream = await agent.streamEvents(input, { version: "v3" });
```

核心 typed projection：

```text
stream.messages
stream.toolCalls
stream.values
stream.output
stream.subgraphs
stream.subagents        Deep Agents
stream.extensions.<name>
```

Message stream 可提供 `text`、Provider 支持时的 `reasoning`、`toolCalls`、`output` 和 `usage`。Tool stream 提供执行生命周期、input、output、error。只在需要完整到达顺序或调试未知 channel 时迭代 raw event。

产品规则：

- 普通 C 端 UI 使用 `stream.subagents`，因为它表达 Deep Agents 的产品级 task delegation。
- `stream.subgraphs` 用于 Graph 结构和诊断，不直接等同用户可理解的专家任务。
- Reasoning 只渲染 Provider 公开返回且政策允许的 block/summary，不宣称 chain-of-thought。
- Custom transformer 用于 artifact、evidence、usage 和 progress，不重建固定协议。

### 4.2 Agent Server Protocol v2

- [Protocol v2 Command](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-command)
- [Protocol v2 Event Stream](https://docs.langchain.com/langsmith/agent-server-api/streaming/protocol-v2-event-stream-sse)

当前官方 endpoint：

```text
POST /threads/{thread_id}/commands
POST /threads/{thread_id}/stream/events
```

关键行为：

- `run.start` 和 `input.respond` 在 worker queue 中启动后台 Run。
- event stream 可按 `channels`、`namespaces` 和 `depth` 过滤。
- reconnect 在请求体传最后收到的 `since` sequence，服务端先 replay 再进入 live。
- endpoint 是 POST-only，原生 `EventSource` 的 `Last-Event-ID` 自动恢复不适用。
- WebSocket 使用同一 command/event envelope，并支持动态 subscribe/unsubscribe。
- Replay buffer 是有界运行时能力；产品历史和审计不能依赖无限 wire event replay。

Protocol v2/Event Streaming 属于需要单独记录稳定性和兼容组的高级能力。实施时至少同时锁定并验证 Agent Server/API 镜像、`langgraph-sdk` 和 `@langchain/langgraph-sdk`，不能只锁 React 包。当前官方页面给出的最低兼容基线包括 `langgraph-api>=0.10.0`、JS SDK `>=1.9.15`、Python SDK `>=0.4.0`；最终以实施日文档和锁定版本为准。

固定 channel：

```text
values
updates
messages
tools
lifecycle
input
tasks
custom
custom:<name>
```

强制使用官方 SDK/Transport 实现 replay、ordering、deduplication 和 namespace subscription。

## 5. React SDK 与高级前端能力

- [`@langchain/react`](https://github.com/langchain-ai/langgraphjs/tree/main/libs/sdk-react)
- [React SDK Docs](https://github.com/langchain-ai/langgraphjs/tree/main/libs/sdk-react/docs)
- [LangGraph JS SDK](https://github.com/langchain-ai/langgraphjs/tree/main/libs/sdk)
- [LangChain Frontend Overview](https://docs.langchain.com/oss/javascript/langchain/frontend/overview)
- [Deep Agents Subagent Streaming](https://docs.langchain.com/oss/javascript/deepagents/frontend/subagent-streaming)

根 `useStream` 负责：

```text
values
messages
toolCalls
interrupt / interrupts
error
isLoading
threadId
subagents
subgraphs
submit()
stop()
disconnect()
respond()
respondAll()
```

新 Thread 首次提交后必须通过 `onThreadId` 保存服务端 ID。恢复/切换 Thread 时重新挂载同一 `threadId`，由 SDK hydrate/reattach。`disconnect()` 只断开客户端订阅；`stop()` 默认取消当前服务端 Run。`isThreadLoading`、运行 `isLoading`、optimistic projection 和 reconnect 不能合并成一个产品状态。

实施时必须复核并优先使用以下 selector/能力：

```text
useValues
useMessages
useToolCalls
useMessageMetadata
useSubmissionQueue
useExtension
useChannel
useChannelEffect
useAudio
useImages
useVideo
useFiles
useMediaURL
```

高级 submit 语义包括 `multitaskStrategy`、`forkFrom`、`runId`、`threadId`、`metadata`、`config`、`interruptBefore`、`interruptAfter`。具体签名在锁定依赖版本后从 TypeScript types 和官方 API Reference 再确认，不在业务 wrapper 中冻结一份复制类型。

`useSubmissionQueue` 是客户端内存能力，刷新和切换 Thread 后不能作为 durable queue。Agent Server worker queue 才承担后台 Run。`multitaskStrategy` 的默认值和各枚举行为必须以锁定 SDK types 为准并写入测试，禁止依赖默认 rollback 或旧文档示例。

Fork 使用锁定版本的 `useMessageMetadata(...).parentCheckpointId` 和 `submit(..., { forkFrom: checkpointId })` 形状。若官网示例与已发布包 TypeScript types 不一致，以锁定包 types 和 SDK 仓库文档为准，并在实施说明记录差异。

Subagent snapshot 只负责 discovery。`useMessages(stream, subagent)`、`useToolCalls(stream, subagent)`、`useValues(stream, subagent)` 在组件挂载时建立 scoped subscription；未展开的 subagent 不应产生不必要 wire traffic。

## 6. Frontend Pattern 文档

以下官方文档族必须在对应实现切片前逐页复核：

```text
/oss/*/langchain/frontend/overview
/markdown-messages
/tool-calling
/reasoning-tokens
/structured-output
/generative-ui
/human-in-the-loop
/headless-tools
/join-rejoin
/message-queues
/branching-chat
/time-travel
```

LangGraph/Deep Agents 补充页面：

```text
/oss/*/langgraph/frontend/overview
/graph-execution
/custom-stream-channels
/oss/*/deepagents/frontend/overview
/subagent-streaming
/todo-list
/sandbox
```

设计采用：Markdown sanitization、typed Tool card、reasoning 折叠、渐进 Structured Output、受控 Generative UI、HITL、join/rejoin、queue、branch/fork、time travel、multimodal、subagent 和 Artifact。

## 7. Middleware

- [Built-in Middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [Custom Middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)
- [Deep Agents Customization](https://docs.langchain.com/oss/python/deepagents/customization)
- [Going to Production](https://docs.langchain.com/oss/python/deepagents/going-to-production)

已纳入设计的官方 Middleware：

```text
SummarizationMiddleware
HumanInTheLoopMiddleware
ModelCallLimitMiddleware
ToolCallLimitMiddleware
ModelFallbackMiddleware
PIIMiddleware
TodoListMiddleware
LLMToolSelectorMiddleware
ToolRetryMiddleware
ModelRetryMiddleware
LLMToolEmulator
ContextEditingMiddleware
ProviderToolSearchMiddleware
ShellToolMiddleware
FilesystemFileSearchMiddleware
FilesystemMiddleware
SubagentMiddleware
RubricMiddleware (beta)
```

不是所有 Middleware 都应启用。角色矩阵见 `02-official-framework-constraints.md`。Shell/Filesystem 在当前生产产品禁用；Tool Emulator 仅用于测试；Rubric 只作为评测信号；Decision Agent 禁止 silent model fallback。

Deep Agents 的默认栈可能自动包含 Filesystem/Subagent/Summarization/Patch Tool Calls。实施必须断言最终 Tool/Middleware/Permission 清单；完全禁用 filesystem 时允许改用 `create_agent` Research Harness。

自定义 hooks：

```text
before_agent
before_model
after_model
after_agent
wrap_model_call
wrap_tool_call
```

Custom Middleware 可增加 state、tools 和 stream transformers。执行顺序必须有 contract test：before 正序、after 逆序、wrap 嵌套。

## 8. HITL、Queue、Fork 与长任务

- [Human-in-the-loop using server API](https://docs.langchain.com/langsmith/add-human-in-the-loop)
- [Time Travel](https://docs.langchain.com/langsmith/human-in-the-loop-time-travel)
- [Background Runs](https://docs.langchain.com/langsmith/background-run)
- [Cron Jobs](https://docs.langchain.com/langsmith/cron-jobs)
- [Create Background Run API](https://docs.langchain.com/langsmith/agent-server-api/thread-runs/create-background-run)

设计结论：

- Interrupt 使用 `respond()`；同一 checkpoint 的并行 Interrupt 使用一次 `respondAll()`。
- Root `stream.interrupts` 只代表 root namespace；完整 Thread/subagent Interrupt 从官方 Thread snapshot 读取，并携带 interrupt ID 与 namespace 恢复。
- 响应和 State 修正需要原子提交时使用 `respond(response, { update })`。
- 页面离开使用 disconnect/rejoin，不等同 cancel。
- 运行中用户输入区分 client submission queue、Server worker queue 和 multitask strategy。
- 编辑和重新生成使用 checkpoint fork/`forkFrom`。
- 定时监控使用 Agent Server cron，不使用应用进程内 timer。
- Interrupt 恢复保持同一 Thread/Checkpoint 连续性，但产生新的可追踪 Run；业务记录通过 `resume_of_run_id` 关联。

## 9. 官方前端集成选项

- [Frontend Integrations Overview](https://docs.langchain.com/oss/python/langchain/frontend/integrations/overview)
- [AI Elements](https://docs.langchain.com/oss/python/langchain/frontend/integrations/ai-elements)
- [assistant-ui](https://docs.langchain.com/oss/python/langchain/frontend/integrations/assistant-ui)
- [CopilotKit](https://docs.langchain.com/oss/python/langchain/frontend/integrations/copilotkit)
- [OpenUI](https://docs.langchain.com/oss/python/langchain/frontend/integrations/openui)

结论：

- `@langchain/react` 保持唯一 Runtime 状态源。
- AI Elements 或 assistant-ui 只作为 presentation/component 层，实施前 ADR 二选一。
- CopilotKit 只有明确需要 AG-UI/shared state/frontend tools 时引入。
- OpenUI 只用于受控报告/Artifact，不替代确定性风险视图。

## 10. Auth、商业化与集成边界

- [Agent Auth](https://docs.langchain.com/langsmith/agent-auth)
- [Authentication and Access Control](https://docs.langchain.com/langsmith/auth)
- [Resource Authorization](https://docs.langchain.com/langsmith/resource-auth)
- [Auth Service v2 API](https://docs.langchain.com/api-reference/auth-service-v2/authenticate)
- [MCP OAuth Provider APIs](https://docs.langchain.com/api-reference/auth-service-v2/create-mcp-oauth-provider)

LangChain/LangSmith 提供 Agent 身份、资源授权和 OAuth 集成能力，但不等于完整 C 端订阅账单系统。V2 自己保存 workspace、membership、entitlement、usage ledger 和外部 subscription reference；支付核心使用成熟支付平台。

Run 授权继承父 Thread，`threads.create_run` 负责 admission；Store 必须由后端重写 tenant/user namespace。Custom routes 使用 auth-first `/app/*`/`/internal/*`，禁止 shadow Agent Server 系统路由。

## 11. 官方参考应用

- [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui)
- [Deep Agents UI](https://github.com/langchain-ai/deep-agents-ui)
- [Open SWE](https://github.com/langchain-ai/open-swe)
- [Open Canvas](https://github.com/langchain-ai/open-canvas)
- [Agent Inbox](https://github.com/langchain-ai/agent-inbox)
- [Agent Auth Payments](https://github.com/langchain-ai/agent-auth-payments)
- [Open Deep Research](https://github.com/langchain-ai/open_deep_research)

这些仓库是产品模式和集成参考，不是当前 API 的权威来源。尤其 Deep Agents UI 等项目可能使用旧 SDK；实施必须以当前 docs、types 和 changelog 为准。

## 12. 实施前复核门禁

每个实现切片必须在实施说明中记录：

- 对应 `llms.txt` 页面和读取日期。
- 锁定包版本和 API Reference 链接。
- stable/beta/alpha 状态。
- 官方 API 能否完整满足需求。
- 是否存在旧示例与当前 types 不一致。
- 采用的官方接口和没有采用的候选方案。
- 如需自定义代码，对应 ADR 和删除条件。

以下变化触发架构重新评审：

- Protocol v2 channel/command breaking change。
- `@langchain/react` selector 或 subagent discovery breaking change。
- Deep Agents 进入 1.0 或改变 delegation/permission 模型。
- Agent Server 许可、部署或数据驻留不能满足产品要求。
- LangSmith/Langfuse tracing 产生重复、隐私或成本不可接受问题。

## 13. 诚实边界

- 本次已完整扫描 `llms.txt` 索引，并深读所有直接影响 V2 架构的文档族；没有声称逐字阅读每个与产品无关的管理 API 页面。
- 官方文档和 SDK 更新速度较快，本文记录的是 2026-07-11 设计基线，不替代实施时的版本复核。
- GitHub 示例仓库只证明成熟交互模式存在，不能证明其依赖和 API 适合直接复制。
- 设计中出现的 API 名称必须以锁定版本的 types/reference 为最终依据，禁止为了保持本文文字而包装过时接口。
