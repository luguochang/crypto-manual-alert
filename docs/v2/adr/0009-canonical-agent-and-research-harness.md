# ADR 0009: Canonical Agent Boundary And Research Harness

> authority_class: approved_normative
>
> 状态：Accepted
>
> 批准日期：2026-07-17
>
> 批准人：用户（V2 active goal 明确允许受限 Deep Agents 方案或正式 fallback）

## Context

V2 必须只有一个生产 LangGraph 和一个可审计的 Agent Harness 边界。当前市场分析需要结构化 `MarketAnalysis`，Research 需要调用一个只读 Web Search provider、保存 provider citation，并把引用事实抽取为 `ResearchBundle`。Evidence、Risk、HITL、持久化和通知均由确定性 Graph/Product 边界负责。

锁定的 `deepagents==0.6.12` 官方 `create_deep_agent` 默认包含 todo、filesystem、`execute` 和 `task`。`HarnessProfile.excluded_tools` 和 `GeneralPurposeSubagentProfile(enabled=False)` 可以收窄工具面，但当前 Research 不需要文件系统、代码执行、任务委派、长期 memory 或复杂 planning。为单次有界搜索引入 Deep Agents 会增加 pre-1.0 permission、middleware 和升级面，而不会增加产品能力。

## Decision

1. `backend/langgraph.json` 只注册 `crypto_alert_v2.graph:graph_factory`，它是唯一生产 Graph；生产包不得导出 import-time compiled Graph。
2. 市场分析继续使用官方 LangChain `create_agent` 和 `ToolStrategy(MarketAnalysis)`。
3. Research 使用唯一的官方 LangChain `create_agent` Harness：provider adapter 先取得可验证 citation，Agent 只从该证据抽取 `ResearchBundle`；结果必须通过 URL allowlist 校验。
4. 不在当前 release 激活 `create_deep_agent`，也不保留第二套 Deep Agents runtime。未使用的 `deepagents` 依赖从 release dependency 和 lockfile 移除。
5. 删除未被 canonical graph 引用的 `graph/nodes` 手写 runtime；禁止重新引入自由文本 JSON parser、第二个 Agent factory 或第二个 Graph builder。
6. Evidence/Risk、Product command、Agent Server Thread/Run、HITL 和前端 streaming 继续分别由确定性领域函数、Product PostgreSQL、官方 LangGraph/SDK 和 `@langchain/react` 所有。

## Alternatives

- **立即使用 Deep Agents**：拒绝。当前没有 subagent、long-context 或 filesystem 产品需求，收益不足以覆盖权限和升级风险。
- **手写 planner/pool/runtime**：禁止。LangChain/LangGraph 已提供 Agent loop、Graph、HITL、streaming 和 durability 边界。
- **直接模型 HTTP 请求和 JSON parser**：禁止。Structured Output 已由 `ToolStrategy` 和 Pydantic 提供。

## Verification

- Framework ownership test 断言 Agent Server 仅注册一个 `graph_factory`。
- `crypto_alert_v2.graph` 只导出 `create_graph` 和 `graph_factory`，不得导出模块级 compiled `graph`。
- `python -m crypto_alert_v2.workers` 是唯一 Worker 进程入口，`commands/worker.py` 不得存在。
- 只有 `agents/market_analysis.py` 和 `agents/research.py` 可以导入 `create_agent`。
- canonical production source 不得导入 `crypto_alert_v2.graph.nodes`。
- `graph/nodes` 目录必须不存在。
- release dependencies 不得包含 inactive `deepagents`。
- Agent factory 不得使用 `json.loads` 解析模型输出。

## Reintroduction Trigger

只有当产品出现明确的只读多阶段研究、受控 subagent delegation 或长上下文管理需求时，才可以通过新的 ADR 重新引入 Deep Agents。新实现必须证明最终 effective tools 不包含 `write_file`、`edit_file`、`execute`；禁用默认 general-purpose subagent；无同步 subagent 时不暴露 `task`；filesystem backend 为 deny-all/non-executing；并通过权限、预算、stream 和升级回归测试。

## Consequences

Canonical runtime 更小，框架边界更清楚，依赖和攻击面减少。未来引入 Deep Agents 需要显式迁移，而不是通过一个隐藏 import 形成双 runtime。
