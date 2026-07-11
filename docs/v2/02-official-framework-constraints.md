# V2 官方框架使用与禁止自研约束

> 状态：Draft for Review
>
> 目的：把“优先使用现成官方框架”变成代码审查和 CI 可以执行的规则

## 1. 总原则

V2 的业务价值是加密市场事实、证据、风险规则和用户体验，不是重新发明 Agent Runtime。任何通用能力在实现前必须按以下顺序决策：

1. 检查当前锁定版本的 LangChain、LangGraph、Deep Agents、LangSmith、Langfuse 和官方前端 SDK 文档。
2. 检查官方 API Reference、官方示例仓库和 Changelog。
3. 使用 stable API；beta API 必须记录风险；alpha/internal API 默认禁止。
4. 只有官方能力确实不满足需求时，才能写自定义代码。
5. 自定义基础设施必须有 ADR、替代方案比较、删除条件和用户批准。

“我熟悉自己写一套”不是自定义理由。“官方示例不完全符合当前目录结构”也不是自定义理由。

## 2. 官方能力矩阵

| 需求 | 必须优先使用 | 禁止替代实现 |
| --- | --- | --- |
| 模型初始化 | `init_chat_model` / `ChatOpenAI` | 直接 `httpx` 拼模型请求 |
| Tool 定义 | `@tool`、StructuredTool、官方 Provider Tool | 自定义 Tool envelope/registry protocol |
| Agent Loop | `create_agent` | 自定义 while-loop AgentExecutor |
| 复杂研究 Harness | `create_deep_agent` | 自定义 planner + pool + worker runtime |
| Structured Output | `response_format`、Pydantic、ProviderStrategy/ToolStrategy | 正则/字符串提取 JSON |
| Prompt/Tool 动态控制 | LangChain Middleware | 多层 manager/adapter 修改请求 |
| 模型重试 | `ModelRetryMiddleware` / model retries | 每个调用点写 retry loop |
| Tool 重试 | `ToolRetryMiddleware` | Tool 内部吞异常后伪造成功 |
| 调用预算 | `ModelCallLimitMiddleware`、`ToolCallLimitMiddleware` | 自定义 ToolBudget runtime |
| PII/密钥脱敏 | `PIIMiddleware` + Trace masking | 页面层最后再字符串替换 |
| 顶层状态机 | `StateGraph` | LegacyWorkflowState + step runner |
| 条件路由 | conditional edges / `Command` | if/else 隐藏在 orchestration shell |
| 并行 fan-out | Graph parallel branch / `Send` | ThreadPoolExecutor Agent pool |
| Durable Execution | LangGraph Checkpointer / Agent Server | 自建 checkpoint tables/runtime |
| Thread Memory | Checkpointer | 自建 conversation state store |
| Cross-thread Memory | LangGraph Store | 把全部历史塞回 Prompt |
| Human-in-the-loop | `interrupt` / `Command(resume=...)` / HITL Middleware | 自建 pending-action polling 表 |
| Streaming | Agent Server protocol + `@langchain/react` | 手写 SSE 协议和重连状态机 |
| Trace | LangSmith automatic tracing | 自建 spans 覆盖 LangChain Run |
| 生产 LLM 观测 | Langfuse Callback/OTel | 每个 Node 散落 SDK 调用 |
| Dataset/Eval | LangSmith Dataset/Experiment/Evaluator | 只用临时 JSON 文件评测 |
| 前端 Thread/Run | LangGraph SDK / `useStream` | 自建 run polling store |
| Auth Resource Filter | Agent Server Auth handlers | 只在前端隐藏别人的数据 |

## 3. 各框架边界

### 3.1 LangChain

允许：

- Models、Messages、Tools、`create_agent`。
- Structured Output。
- Middleware。
- Provider 官方集成。
- Callback 和 RunnableConfig。

不允许：

- 在 LangChain 外再定义 `ModelRequest`、`ModelResponse` 通用协议。
- 为每个 Provider 建一层本项目私有 SDK。
- 把 LangChain 消息先转成本项目消息，再转回 LangChain 消息。
- 用自定义 parser 重复 Structured Output。

### 3.2 LangGraph

允许：

- 唯一 canonical StateGraph。
- 确定性 Node 与 Agent Node 混合。
- Subgraph、Send、Command、RetryPolicy、Interrupt。
- Checkpointer、Store、Thread 和 Run。
- Agent Server 官方 API 和 Streaming Protocol。

不允许：

- Graph 外再有一套 Workflow Executor。
- 节点内调用另一套隐式 step pipeline。
- 用数据库状态字段模拟 Checkpoint/Interrupt。
- 同时保留 legacy/candidate/controlled 三个生产图。
- 捕获所有异常并转换为普通 State Update。

### 3.3 Deep Agents

允许：

- 只读 Web Research。
- 受限 Subagent Delegation。
- Context Summarization 和研究证据整理。
- 官方 Permission、Middleware 和 Backend 能力。

默认禁止：

- Shell、REPL、任意代码执行。
- 产品代码仓库写权限。
- 数据库写工具。
- 通知工具。
- 交易所私有 API。
- 最终 action、allowed、leverage、risk budget 决策。
- 无限 recursion、无限模型调用和无限 Web Search。

原因：Deep Agents 当前是 pre-1.0。V2 通过窄的 `ResearchBundle` 契约隔离其版本变化，未来可以替换 Harness 而不影响主图和业务表。

### 3.4 LangSmith

允许：

- 自动 Trace 和少量 `traceable` domain span。
- Metadata、Tags、Thread 聚合。
- Dataset、Experiment、Online Evaluation。
- Studio 和 Debug。
- Conditional Tracing 和输入输出隐藏。

禁止：

- 把 LangSmith 当业务数据库。
- 前端直接读取 LangSmith 作为产品运行历史。
- 在每个 Node 手工创建重复 Run。
- 将 API Key、Bark Key、Authorization、Cookie 写入 metadata。

### 3.5 Langfuse

允许：

- LangChain CallbackHandler。
- OTel root/domain span。
- Session、User、Cost、Latency、Prompt、Feedback、Sampling 和 Masking。
- Cloud 或 Self-hosted。

禁止：

- 业务节点依赖 Langfuse 成功后才能返回。
- 同一 LangChain 调用同时用 Callback 和手工 generation 重复记录。
- 把用户邮箱、密钥或完整敏感请求作为默认 trace attribute。

### 3.6 官方前端 SDK

必须：

- 每个 Thread 只挂载一个根 `useStream`。
- 使用 SDK 的 `messages`、`toolCalls`、`interrupts`、`values` 和 selector hooks。
- 使用官方 submit/stop/respond/thread history 能力。
- 使用官方 Transport 或 AgentServerAdapter。

禁止：

- 再写 Redux/Zustand Graph Runtime 副本。
- 用多个组件分别建立同一 Thread 的流连接。
- 把 Provider chunk 直接拼成页面业务对象。
- 在浏览器保存 LangSmith Secret/API Key。

## 4. 自定义代码允许范围

V2 允许自定义的代码必须属于以下业务领域：

- 交易所行情标准化和 source/freshness 判定。
- Web Evidence 业务字段和来源质量规则。
- 交易风险、动作、价格、杠杆、TTL 和 confidence cap。
- 产品业务表和 Actor-aware Repository。
- Bark 通知格式与幂等策略。
- 面向用户的 View Model 和产品组件。
- 多用户业务权限规则。
- Outcome 和金融质量评测。

即使属于允许范围，也应实现为：

- 小型纯函数。
- Pydantic Model。
- LangChain Tool。
- LangGraph Node。
- Agent Server custom route。
- React 产品组件。

不能借“业务定制”重新创建通用 Runtime。

## 5. Wrapper Budget

### 5.1 一层规则

官方接口外最多一层有业务含义的装配：

```text
允许：Graph Node -> ChatOpenAI
允许：Agent factory -> create_agent
允许：Market Tool -> CCXT/Exchange API
禁止：Graph Node -> Service -> Manager -> Adapter -> Client -> ChatOpenAI
```

### 5.2 Pass-through Wrapper 禁止

只转发参数、改名或捕获后重新抛出同一异常的 wrapper 必须删除。Wrapper 必须至少提供一种明确价值：

- 业务校验。
- 安全边界。
- 稳定 DTO 映射。
- 幂等/事务。
- Provider capability 隔离。

### 5.3 Factory 数量

- 一个 Model Factory。
- 一个 Agent Factory 模块。
- 一个 canonical Graph Builder。
- 一个 Observability 装配入口。
- 每个外部 Provider 一个业务 Adapter，不再套统一 Provider Runtime。

## 6. 禁止出现的模式

生产代码禁止新增以下名称或等价职责，除非 ADR 明确批准：

- `AgentExecutor`
- `WorkflowRuntime`
- `WorkflowExecutor`
- `PlanRunner`
- `AgentPoolRunner`
- `ToolExecutor`
- `ToolRegistry`，仅为复制 LangChain registry 时
- `LLMClient`，仅为复制模型 SDK 时
- `CheckpointStore`
- `StreamingManager`
- `MessageEnvelope`
- `ShadowWorkflow`
- `LegacyAdapter`
- `CompatibilityWrapper`

名称不同但职责相同，也视为违规。

## 7. 依赖和版本约束

- 使用 lockfile 锁定精确解析版本。
- Python 使用 `uv.lock`；前端使用单一 package manager 和 lockfile。
- LangChain/LangGraph 使用同一兼容版本组。
- Deep Agents 0.x 必须锁定 minor/patch，不允许无人审查的自动升级。
- 每次升级先读官方 Changelog 和 Migration Guide。
- 禁止依赖私有 `_` API。
- alpha API 必须隔离在单文件 Adapter 后，并有替换测试。
- beta API 必须在实施说明中记录升级风险。

## 8. 静态架构门禁

实现阶段必须加入以下 CI 检查：

### 8.1 Import Contracts

使用 `import-linter` 或等价成熟工具约束：

- `domain` 不依赖 LangChain、LangGraph、FastAPI、SQLAlchemy 和观测 SDK。
- `tools` 可以依赖 domain 和外部 Provider，不能依赖 api/frontend。
- `graph` 可以依赖 agents/tools/domain，不能依赖具体页面 DTO。
- `api` 可以调用 graph 和 repository，不能修改 Graph 内部 State。
- `observability` 不被 domain 依赖。

### 8.2 Framework Ownership Test

CI 检查：

- `StateGraph(` 只能出现在 canonical graph builder 和测试 fixture。
- `create_agent(` / `create_deep_agent(` 只能出现在 agent factory 和测试。
- `ChatOpenAI(` / `init_chat_model(` 只能出现在 model factory 和测试。
- Langfuse Callback 初始化只能出现在 observability 装配入口。
- 产品代码禁止直接 import V1 `crypto_manual_alert.workflow`、`agent_swarm`、`orchestration`。

### 8.3 Forbidden Network Calls

- Agent/Graph 模块禁止直接使用 `httpx`、`requests` 调模型 API。
- Web Search 必须通过已批准的 LangChain Provider Tool。
- 市场 Tool 可使用成熟 SDK 或受控 `httpx` Adapter，但必须有 contract test。

### 8.4 Schema Gate

- Agent 最终输出必须有 Pydantic schema。
- Tool 输入必须有类型和描述。
- 前端所有 API/Stream 产品投影必须有 Zod schema 或 SDK 推断类型。
- 禁止 `dict[str, Any]` 穿越超过一个模块边界。

## 9. ADR 强制流程

遇到官方框架不满足需求时，先创建：

```text
docs/v2/adr/NNNN-<decision>.md
```

ADR 必须回答：

1. 具体需求是什么。
2. 已检查哪些官方文档/API/Issue。
3. 为什么官方能力不能满足。
4. 比较过哪些现成库。
5. 自定义代码最小范围是什么。
6. 如何测试、观测和删除。
7. 升级到官方能力的触发条件是什么。
8. 用户是否批准。

没有 ADR 不得新增通用基础设施。

## 10. 中文注释规范

用户要求代码可追踪、可读，因此 V2 采用“适当中文注释”，不是每行翻译。

必须写中文注释或 Docstring 的位置：

- 风险规则为什么阻断或降级。
- 数据 freshness、source rank、confidence cap 的业务不变量。
- 幂等、事务和恢复边界。
- LangGraph 中不直观的 reducer、Command、Send 和 Interrupt 选择。
- 安全、隐私、租户隔离和权限判断。
- 官方 API 存在反直觉配置或版本限制时。

不应写注释的位置：

- 变量赋值的逐字翻译。
- 函数名已经清楚表达的简单操作。
- 已经过时的历史实现说明。
- 大段注释保留废弃代码。

注释必须解释“为什么”和“不变量”，不能只描述“做了什么”。

示例：

```python
# Web 搜索只能补充事件背景，不能替代交易所原生价格事实。
if snapshot.source_level != SourceLevel.EXCHANGE_NATIVE:
    return RiskVerdict.block("execution_facts_not_exchange_native")
```

## 11. 每轮实施说明

每个实现切片必须新增或更新：

```text
docs/v2/implementation/YYYY-MM-DD-<phase>-<slice>.md
```

内容必须包括：

- 本轮目标和不做什么。
- 本轮使用的官方接口及链接。
- 修改文件和职责。
- 数据/状态/API 契约变化。
- 测试命令和实际结果。
- 截图/Trace/Run ID 等证据。
- 未解决问题和下一轮入口。
- 是否新增自定义封装，以及理由/ADR。

Agent 每轮对用户的最终回复也必须给出同样的高层摘要，不能只说“已完成”。

## 12. Code Review Checklist

每次 Review 必须先回答：

- [ ] 官方框架是否已有对应能力？
- [ ] 是否出现第二套状态、重试、流式或 Checkpoint 控制面？
- [ ] 自定义 wrapper 是否有业务价值？
- [ ] Agent 是否越权决定风险或执行副作用？
- [ ] 多用户字段是否完整传播？
- [ ] 模型/Tool 输出是否结构化并持久化？
- [ ] 普通前端是否出现 raw JSON？
- [ ] 观测失败是否会阻断业务？
- [ ] 中文注释是否解释了关键不变量？
- [ ] 本轮实施说明是否完整？

## 13. 违反约束时的处理

- CI 直接失败，不以“后续重构”放行。
- 先删除违规自研层，再继续功能开发。
- 若确有框架缺口，停止实现并提交 ADR 给用户批准。
- 禁止为兼容尚未发布的代码保留 legacy wrapper。
