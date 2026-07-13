# ADR 0001：Agent Runtime、部署和持久化拓扑

> authority_class: approved_normative
>
> 状态：Accepted
>
> 日期：2026-07-12
>
> 批准：用户，2026-07-13

## 背景

V2 必须使用官方 Thread、Run、Checkpoint、Interrupt、Streaming 和 React SDK，避免自建运行时。同时需要 Product PostgreSQL 保存用户、Task、Artifact、Usage 和 Outcome，不能把产品查询绑定到 Agent Server 内部表。

## 决策

- Agent Runtime 使用 LangGraph Agent Server 和官方 Protocol v2。
- 开发使用 `langgraph dev`，集成/容器验证使用 `langgraph up`。
- 生产优先评估并采用官方 LangSmith Deployment；若许可、数据驻留或成本不满足，再新增 ADR 选择自管 Agent Server。
- 浏览器只访问 Next.js BFF；BFF 代理 Agent Server 并注入身份和 correlation metadata。
- Product PostgreSQL 与 Agent Server persistence 使用独立数据库和独立角色；本地可以共用一个 Postgres 实例，但不能共用表或权限。
- Redis、Checkpoint、Store 和 wire replay 由 Agent Server 管理；产品代码不得实现替代品。

## 替代方案

- 独立 FastAPI + Agent Server：边界清楚，但第一阶段增加两套部署和鉴权，不采用。
- CompiledGraph 嵌入自建 FastAPI：会迫使项目重做官方 Server API/stream/recovery，不采用。

## 风险与退出条件

- 实施前核验许可、区域、数据驻留、custom route/auth、Cron、Webhook、备份和 HA。
- 若官方部署不满足，前端仍保持 `@langchain/react`/AgentServerAdapter 契约，替换部署不能改变产品 DTO。
- 未完成上述核验前只能进入开发和集成阶段，不能宣称生产部署已冻结。
