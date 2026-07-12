# ADR 0004：前端 Runtime 与视觉组件

> 状态：Proposed
>
> 日期：2026-07-12

## 背景

前端需要成熟的 Agent 流式、Thread、Tool、Interrupt、Subagent 和重连能力，同时必须形成加密市场业务界面，不能直接复刻通用聊天模板或再建一套状态 Runtime。

## 决策

- `@langchain/react` v1 是 Thread/Run/stream 的唯一客户端状态源。
- `@langchain/langgraph-sdk` 负责官方 Server API 和类型。
- 每个 Thread 只挂载一个根 `useStream`，业务组件通过 selector hooks 读取。
- 视觉层推荐 AI Elements + shadcn/ui，原因是组件可编辑、不会强制第二个 Agent Runtime，便于建立 Market/Evidence/Risk/Artifact 专用组件。
- Agent Chat UI、Deep Agents UI、Open Canvas 和 Agent Inbox 只作为交互参考，不直接复制其旧 SDK 代码。
- Generative UI 只能从版本化白名单组件注册表选择 schema-validated props。

## 不采用

- assistant-ui 作为第二 Thread/Message Runtime。
- CopilotKit/AG-UI 与 Protocol v2 双协议并存，除非后续 ADR 证明必要。
- Redux/Zustand 保存 Graph Runtime 副本。
- 前端解析 raw wire frame 或 Provider chunk 生成业务状态。

## 评审点

若必须采用 assistant-ui，只允许把它做 presentation adapter；必须证明状态、branch、interrupt 和 message ownership 仍完全来自 `@langchain/react`。
