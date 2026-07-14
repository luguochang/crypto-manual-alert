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
- 开发 smoke 使用 `langgraph dev`。集成/容器验证使用官方 `langgraph build` 从锁定的 Agent Server image digest 构建应用镜像，再由项目 Compose 注入独立 PostgreSQL/Redis URI 并启动；产品代码不得替代 Agent Server Runtime。
- 生产优先评估并采用官方 LangSmith Deployment；若许可、数据驻留或成本不满足，再新增 ADR 选择自管 Agent Server。
- 浏览器只访问 Next.js BFF；BFF 代理 Agent Server 并注入身份和 correlation metadata。
- Product PostgreSQL 与 Agent Server persistence 使用独立数据库和独立角色；本地可以共用一个 Postgres 实例，但不能共用表或权限。
- Compose 自管集成环境中，`PRODUCT_POSTGRES_*` 与 `AGENT_POSTGRES_*` 配置服务端数据库/角色；覆盖这些值时，调用方必须同时提供与之匹配且已完整 percent-encode 的 `COMPOSE_PRODUCT_DATABASE_URL` 与 `COMPOSE_AGENT_POSTGRES_URI`。Compose 不从原始用户名或密码拼接 URI，也不承诺独立覆盖两侧后仍可连接。
- Redis、Checkpoint、Store 和 wire replay 由 Agent Server 管理；产品代码不得实现替代品。

## 替代方案

- `langgraph up`（CLI 0.4.31）：能生成同一官方 Runtime，但固定将 API 端口发布到所有 host interface，且不能追加最终的 loopback override；本地受控集成拓扑暂不采用。CLI 提供 host-IP 控制后重新评估。
- 独立 FastAPI + Agent Server：边界清楚，但第一阶段增加两套部署和鉴权，不采用。
- CompiledGraph 嵌入自建 FastAPI：会迫使项目重做官方 Server API/stream/recovery，不采用。

## 风险与退出条件

- 实施前核验许可、区域、数据驻留、custom route/auth、Cron、Webhook、备份和 HA。
- 若官方部署不满足，前端仍保持 `@langchain/react`/AgentServerAdapter 契约，替换部署不能改变产品 DTO。
- 未完成上述核验前只能进入开发和集成阶段，不能宣称生产部署已冻结。
