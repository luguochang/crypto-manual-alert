# ADR 0011：Aegra 自托管开源 Agent Server

> authority_class: approved_normative
>
> 状态：Accepted
>
> 日期：2026-07-21
>
> 批准：用户，2026-07-21（明确拒绝商业授权并要求选择可复用开源项目）

## 背景

V2 需要持久化 Thread、Run、Checkpoint、Interrupt、后台执行和 Protocol v2
streaming，同时必须继续使用官方 LangChain、LangGraph、Deep Agents、checkpointer、
SDK 和 React 边界。官方商业 Agent Server 的完整自托管能力需要
`LANGGRAPH_CLOUD_LICENSE_KEY` 或具备部署权限的 LangSmith 账户，不符合本项目的
非商业授权要求。

项目不能用自建 FastAPI Runtime 重新实现 checkpoint、interrupt、SSE replay、stream
dedup、worker queue 或通用 Agent loop，因此需要选择已有开源 Agent Protocol Server。

## 决策

- 生产候选 Agent Server 选择 Aegra `0.9.24`，`aegra-api==0.9.24` 和
  `aegra-cli==0.9.24` 均固定在 `backend/uv.lock`；许可证为 Apache-2.0。
- Aegra 只拥有 Agent Protocol Server、PostgreSQL persistence、Redis broker/worker、
  lease/reaper、SSE replay、Cron 和 Auth handler 装载。业务 Graph 继续使用官方
  LangGraph，Agent 继续使用官方 LangChain/Deep Agents，客户端继续使用官方 Python/
  JavaScript SDK 与 `@langchain/react`。
- 生产配置为 `backend/aegra.json`，只注册唯一 canonical `crypto_analysis` Graph、
  Auth 和 Product custom app。`backend/aegra.task8-qa.json` 只用于隔离的 durability/
  multi-interrupt 验证，不进入生产配置。
- Product PostgreSQL 与 Aegra PostgreSQL 保持不同数据库和角色；Redis、checkpoint、
  Run replay 和 worker recovery 由 Aegra/官方 LangGraph checkpointer 管理，产品代码不
  创建替代实现。
- Docker Compose 不再要求 `LANGGRAPH_CLOUD_LICENSE_KEY`。模型、Tavily、LangSmith、
  Langfuse 和通知凭据仍按实际启用能力分别配置；Aegra 本身不要求商业许可证。
- ADR 0008 的 LangSmith Deployment Cloud 推荐目标被本 ADR 取代。ADR 0001 中
  `langgraph dev` 仍只作为开发 smoke；其商业镜像构建和 hosted 优先条款由本 ADR
  supersede。

## 兼容边界

- Aegra `0.9.24` 接收但不执行官方 Runs 请求中的 `durability`、
  `stream_resumable` 和 `if_not_exists` 字段。不得把字段序列化测试描述成
  server-effective `sync/exit` durability。
- Aegra 的生产耐久证据必须直接覆盖 PostgreSQL checkpoint、Redis worker lease、
  reaper recovery、同一 Thread/Run 恢复和 Protocol `since` replay。
- 当前 Protocol `state.fork` 仍返回 `unknown_command`；Product checkpoint fork 继续
  通过官方 Runs `checkpoint_id` 边界实现，并保持兼容例外为未关闭状态。
- root `checkpoints` channel、跨实例 replay TTL、并行/嵌套 interrupt、cancel/retry 和
  多租户过滤必须由 live contract 持续验证；不允许在业务 wrapper 中补一套协议。

## 已有证据

- Aegra local executor 已完成真实 Tavily、真实模型、Deep Agents、required HITL、
  Artifact commit 和 Desktop/Pixel 7 Product 主链，结果为 `2 passed`、`0 skipped`。
- 本地 Redis worker kill/restart 证明：Run 在首个 LangGraph checkpoint 后被强杀，
  Aegra lease reaper 重新入队同一 Run；原 checkpoint 保留，最终
  `prepared_count=1`、`completion_count=1`、terminal `succeeded`。
- 同一恢复 Run 的官方 `ProtocolSseTransportAdapter` 两次 `since` replay 返回
  `4 -> 3` 个事件，`seq/event_id/method` 完全一致。
- 镜像 verifier 已证明生产镜像包含固定 Aegra/LangGraph SDK 版本，不包含
  `langgraph-api`、in-memory runtime、pytest、测试目录或 `.env`。

以上均为本地 self-hosted 证据，不是 hosted TLS/OIDC、HA、PITR/DR、正式 SLO、
不可变 release candidate 或外部安全审计。当前仍为 `V2: PARTIAL`，
`Production Ready: NO`。

## 替代方案

- 官方 LangSmith Deployment/商业 Agent Server：因用户明确拒绝商业授权，不采用。
- AG-UI LangGraph integration：适合请求级 UI/HITL transport，但当前稳定包没有完整
  持久 Run scheduler、Redis worker lease/reaper 和 Agent Protocol SDK surface，不采用
  为主 Server。
- LangServe、Dify、Flowise、Langflow：不提供本项目锁定的 Agent Protocol v2、
  LangGraph SDK、checkpoint/interrupt/replay 完整兼容面，不采用。
- 自建 FastAPI + CompiledGraph：会重复实现通用 Runtime，违反框架边界，不采用。

## 升级与退出

- 升级 Aegra 前必须重新运行 OpenAPI、Auth、checkpoint、worker kill/reaper、SSE
  replay、HITL、Product mainline 和镜像供应链验证。
- 若 Aegra 后续不能满足安全、HA、恢复或协议门禁，只能新增 ADR 选择另一个现成开源
  Agent Protocol Server；不得在项目内逐步演化成自研 Runtime。
- Product DTO、BFF 和前端保持官方 SDK/Protocol 边界，以便更换 Server 时不重写产品层。
