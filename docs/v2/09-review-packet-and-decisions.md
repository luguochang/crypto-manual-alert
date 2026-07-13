# V2 评审包与统一决策表

> 状态：Approved for V2 Final Implementation
>
> 日期：2026-07-13
>
> 目的：让评审者不必先通读全部 3500 行文档，也能明确产品范围、技术裁决、风险和需要批准的事项

## 1. 建议评审顺序

1. 先阅读本文，确认 D01-D15。
2. 阅读 `01-v2-product-and-architecture.md` 的执行摘要、产品范围、总体架构和 Graph 设计。
3. 阅读 `02-official-framework-constraints.md`，确认禁止自研边界。
4. 阅读 `06-c-end-agent-product-blueprint.md`，确认最终 C 端产品范围。
5. 阅读 `08-production-governance-and-nonfunctional.md`，确认数据权威、安全、恢复和 SLO。
6. 阅读 `10-implementation-roadmap.md`，确认实施顺序和每阶段停止条件。
7. 需要核对官方事实时再查 `05` 和 `07`；需要验收条款时查 `03`。

## 2. 一句话方案

V2 是一个以 LangGraph Agent Server 为唯一运行时、以 LangChain Agent/Tool/Middleware 为标准 Agent Harness、以受限 Deep Agents 处理深度研究、以 `@langchain/react` 连接 C 端工作空间、以 PostgreSQL 保存产品权威数据、同时接入 LangSmith 与 Langfuse 的多用户加密市场智能 Agent 产品。

首条必须真实跑通的主链是：

```text
默认开发身份
  -> 创建 Thread/Task
  -> 真实交易所行情
  -> 真实 Web Search
  -> LangChain Structured Output
  -> 确定性 Evidence/Risk Gate
  -> 渐进持久化
  -> 可选通知
  -> @langchain/react 实时展示、断线恢复和历史回看
```

开发黄金主链可先使用服务端固定身份，但 V2 Final 交付必须包含正式 Auth.js/OIDC 用户体系；`tenant_id`、`user_id`、Workspace、ActorContext、资源授权和数据隔离从第一天进入契约。

## 3. 统一决策表

| ID | 决策 | 推荐结论 | 不接受的后果 |
| --- | --- | --- | --- |
| D01 | 产品定位 | 使用 `Crypto Intelligence Agent Workspace`；Manual Alert 只是 `market_analysis` 模式 | 页面和数据模型再次被单一表单锁死 |
| D02 | 首条主链 | 先完整交付真实 `market_analysis`，再启用 Research/Monitor/Inbox/Outcome | 同时铺开全部模式，主链再次失焦 |
| D03 | Agent Runtime | LangGraph Agent Server/官方协议是唯一 Runtime；Next.js BFF 代理浏览器 | 需要自研 Thread/Run/SSE/重放/HITL |
| D04 | Agent Harness | 使用 LangChain `create_agent`、Tool、Structured Output、Middleware | 重新出现私有 Agent Loop 和 Tool 协议 |
| D05 | Deep Agents | 只用于受限研究/委派；不得拥有最终风险、通知和业务库写权限 | pre-1.0 Harness 变成不可替换的生产控制面 |
| D06 | 身份顺序 | 开发黄金主链允许固定开发账号；最终交付必须完成正式 Auth、Workspace Membership 和同一 ActorContext 接入；生产构建禁用开发身份 | 鉴权阻断早期主链，或最终交付仍是单用户伪产品 |
| D07 | Web Search | 能力探测后使用 Provider built-in；不支持时显式切 Tavily；不可用必须失败可见 | 伪搜索、静默 fallback 或无来源结论 |
| D08 | 前端 Runtime | `@langchain/react` v1 是当前连接 live projection 的唯一 Runtime；历史/可查询状态从 Product API 读取；选择 AI Elements/shadcn 作为可编辑视觉层 | assistant-ui/CopilotKit 等形成第二 Runtime |
| D09 | 数据权威 | Product PostgreSQL 是 Task/Run/Artifact/Usage/Feedback/Outcome 权威；Checkpoint 只管执行恢复 | 产品查询依赖 Runtime 内部表，升级和排障失控 |
| D10 | 双观测 | LangSmith 负责原生 Trace/Eval；Langfuse 负责生产成本/会话/运营；集中装配、业务节点零散埋点为零 | 双写、重复 generation、观测故障阻断主链 |
| D11 | V1 处置 | 迁移规则与 golden cases，不迁移 workflow/orchestration/agent_swarm 实现；不长期双写 | 新项目继续背负旧兼容层 |
| D12 | 实施纪律 | 每轮中文实施说明、适当中文注释、官方接口证据、测试和真实运行证据缺一不可 | 代码不可追踪，后续维护再次依赖猜测 |
| D13 | 生产证明 | 接受 `12-production-proof-slo-and-lifecycle.md` 的量化 SLO、hosted Playwright、删除和 Outcome 分级门禁 | 可以用本地 mock、单样本或手工截图冒充生产完成 |
| D14 | 上线边界 | 法律/产品风险评审完成前只允许 Internal Alpha；公开发布需冻结司法辖区、年龄、披露和个性化边界 | 用免责声明替代真正的产品与合规决策 |
| D15 | 生产部署 | 初始生产证明优先 LangSmith Deployment Cloud；进入 Phase 6 前必须完成 ADR 0008 的许可、区域、网络、Auth、成本和退出证据 | 在部署能力未知时把“默认采用”写成已验证事实 |

## 4. 推荐 ADR 结论

| ADR | 推荐 | 评审重点 |
| --- | --- | --- |
| `0001-agent-runtime-deployment.md` | 开发 `langgraph dev`，集成 `langgraph up`，生产优先官方 LangSmith Deployment；产品数据库独立权限边界 | 许可、区域、退出方案 |
| `0002-web-search-provider.md` | capability probe + built-in/Tavily 显式选择，不允许静默降级 | 自定义模型端点是否支持 Responses web search |
| `0003-identity-and-auth-bootstrap.md` | 非生产固定身份；生产推荐 Auth.js + BFF 短期内部令牌 + Agent Server resource auth | 是否接受 Auth.js 作为默认正式方案 |
| `0004-frontend-presentation-stack.md` | `@langchain/react` 唯一 Runtime，AI Elements/shadcn 作为视觉层 | 是否需要 assistant-ui 的额外能力 |
| `0005-observability-and-prompt-source.md` | LangSmith 自动 Trace + Langfuse CallbackHandler；Prompt 首版以代码评审版本为发布源 | 是否在首版就远程拉取 Prompt |
| `0006-production-slo-retention-and-outcome.md` | 采用量化 SLO、30/365 天默认保留、删除演练和分级 Outcome 样本门禁 | 数值是否需要按部署成本调整 |
| `0007-launch-and-financial-product-boundary.md` | 法律评审前保持 Internal Alpha，不向公众宣称投资建议或收益能力 | 首发地区、最低年龄和字段展示边界 |
| `0008-production-deployment-profile.md` | 初始生产证明推荐官方 Cloud；不满足证据门禁时停在 Internal Alpha 并评审自管方案 | 许可、区域、出站网络和成本 |

## 5. 评审时应拒绝的提案

- “先照 V1 结构搬过去，后面再换 LangGraph”。
- “为了统一，自己再包一层 Agent Runtime/Tool Registry/LLM Client”。
- “前端先把 Graph State 或 JSON 全打印出来，后面再产品化”。
- “正式鉴权后置，所以当前先不带 tenant/user 字段”。
- “LangSmith/Langfuse 都手工埋一遍，更保险”。
- “Deep Agents 能做全部事情，所以让它决定 allowed 并直接写数据库”。
- “测试通过就算生产完成，不需要 hosted 真实模型/搜索/行情/通知/视觉证据”。

## 6. 批准方式

评审者可以回复：

```text
批准 D01-D15；ADR 0001-0007 按推荐结论；ADR 0008 按证据门禁推进；允许进入实施计划细化。
```

也可以只修改单项：

```text
D07 修改为 Tavily 固定主 Provider；其余批准。
```

没有明确批准前：

- 不创建 V2 应用代码。
- 不添加依赖。
- 不创建数据库迁移。
- 不搭建前端页面。
- 只允许继续修订 `docs/v2/`。

## 7. 评审完成定义

- D01-D15 全部有 Approved 或明确替代结论。
- ADR 0001-0007 已变更为 Accepted；ADR 0008 在生产发布前继续执行证据门禁。
- ADR 0008 在进入 Production Proof 前有完整证据并 Accepted；此前最多到 Internal Alpha/Beta 技术准备，不宣称生产部署完成。
- 产品、Graph、数据、前端、观测、测试和 V1 删除边界之间没有矛盾。
- `10-implementation-roadmap.md` 的阶段顺序和停止条件获批。
- 才能进入逐文件、逐测试的实施计划，不得直接开始编码。
