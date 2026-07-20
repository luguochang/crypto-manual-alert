# ADR 0010: Task 13 Restricted Deep Research Harness

> authority_class: approved_normative
>
> 状态：Accepted
>
> 批准日期：2026-07-19
>
> 批准人：用户（V2 最终目标明确要求采用 LangChain/LangGraph/Deep Agents
> 官方能力，并完成 background Deep Research 与可维护生产链路）

## Context

ADR 0009 在同步单次 Research 场景下选择 LangChain `create_agent`，并规定只有
产品出现明确的只读多阶段研究、受控 subagent delegation 或长上下文管理需求时，
才可以重新评估 Deep Agents。Task 13 的 background Deep Research、官方
`stream.subagents`、嵌套人工审核和长任务恢复已经构成该触发条件。

截至本 ADR，稳定版 `deepagents==0.6.12` 官方文档确认：Deep Agents 是建立在
LangChain `create_agent` 与 LangGraph runtime 之上的 agent harness；受限运行应
使用 `HarnessProfile.excluded_tools`、
`GeneralPurposeSubagentProfile(enabled=False)`、显式 declarative subagent、
`FilesystemPermission` 和 `StateBackend`，而不是手写 planner、agent loop、
subagent pool 或文件系统 wrapper。

## Decision

1. 市场分析主流程继续使用 ADR 0009 的轻量 LangChain `create_agent` Research，
   不因 Task 13 重写已通过的同步主链。
2. Task 13 Deep Research 可以使用唯一的官方 `create_deep_agent` factory，所有权
   固定在 `agents/research_harness_selection.py`。
3. Deep Research 主 Agent 不接收业务工具；只允许通过 `task` 调用一个显式的
   `verified-source-researcher`。该 subagent 只能接收 Product 注入的只读、可验证
   Search Tool。
4. 禁用默认 `general-purpose` subagent；隐藏 `ls/read_file/write_file/edit_file/
   delete/glob/grep/execute`；文件系统读写使用 `FilesystemPermission` deny-all；
   backend 固定为 thread-scoped `StateBackend`。
5. Deep Agents 与 LangChain fallback 必须由一个显式 deployment mode 二选一。
   任何单次 factory 调用、部署配置或 Product Task 都不得同时激活两个 harness。
6. 两条路径都使用 Pydantic `ToolStrategy` structured output、模型调用上限、统一
   secret/PII middleware 和有界 transport retry。模型不能直接返回 URL 或原始
   provider payload，只能引用 Search Tool 分配的 source index。
7. `backend/langgraph.json` 继续只注册 `graph_factory`。Deep Research 必须作为
   canonical production Graph 内的受控分支接入，不注册第二个生产 Graph、服务、
   queue 或 Runtime。
8. 本 ADR 只批准 harness 基础边界。Task 13 在 Product admission、background
   persistence、subagent streaming、HITL、disconnect/rejoin 和 Desktop/Pixel 7
   zero-mock 证据完成前保持 `not_started` 或 `partial`，不得宣称生产可用。

## Rejected Alternatives

- **继续用同步 Research 冒充 Deep Research**：拒绝；无法交付 Task 13 的多阶段、
  subagent、长上下文和 background 产品能力。
- **同时运行 Deep Agents 与自研/旧 Research runtime**：拒绝；会重新形成双
  Agent Loop 和不可审计路由。
- **开放默认文件系统、execute 或 general-purpose subagent**：拒绝；超出只读
  金融研究权限边界。
- **为 Deep Research 注册第二个 Agent Server Graph**：拒绝；破坏 canonical
  Graph 和 Product command admission。

## Verification

- `test_research_harness.py` 锁定依赖、profile、工具面、权限、调用预算和二选一
  factory 行为。
- `test_research_harness_fallback.py` 锁定 typed citation-index schema，拒绝 raw URL
  和 provider payload 字段。
- `test_canonical_framework_boundary.py` 只允许该 selector 导入
  `create_deep_agent`，并继续断言 Agent Server 仅注册一个 `graph_factory`。
- 后续 Task 13 integration/Playwright 必须证明实际 Product Task 只激活选定
  harness，并通过官方 subagent stream、background recovery 和用户可见证据门禁。

## Consequences

Task 13 获得官方长任务 harness，同时保留现有短分析主链的稳定性。依赖面会增加
Deep Agents 的稳定版传递依赖，因此每次升级必须重跑 permission、effective tool、
middleware order、stream 和 structured output 合约。当前只有 factory foundation
通过，不改变 `V2 PARTIAL / Production Ready: NO`。
