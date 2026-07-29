# V2 评审包与统一决策表

> authority_class: mixed
>
> normative_regions: D01,D02,D03,D04,D05,D06,D07,D08,D09,D10,D11,D12,D13,D14,D15
>
> 分类：Mixed（D01-D15 表格行为 Approved normative regions；其余内容为 Informative review packet）
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
6. 阅读 `14-v2-final-implementation-plan.md`，确认当前实施顺序和每阶段停止条件；`10` 仅保留为已取代的历史路线图。
7. 需要核对官方事实时再查 `05` 和 `07`；需要验收条款时查 `03`。

## 2. 一句话方案

V2 是一个以 Aegra 自托管开源 Agent Server 承载官方 LangGraph/Agent Protocol、以 LangChain Agent/Tool/Middleware 为标准 Agent Harness、以受限 Deep Agents 处理深度研究、以 `@langchain/react` 连接 C 端工作空间、以 PostgreSQL 保存产品权威数据、以 OpenTelemetry 接入免费/自托管观测后端并允许可选 LangSmith/Langfuse 适配的多用户加密市场智能 Agent 产品。

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
<!-- normative:start D01 -->
<!-- requirement: decision-d01-product-positioning -->
| D01 | 产品定位 | 使用 `Crypto Intelligence Agent Workspace`；Manual Alert 只是 `market_analysis` 模式 | 页面和数据模型再次被单一表单锁死 |
<!-- normative:end D01 -->
<!-- normative:start D02 -->
<!-- requirement: decision-d02-first-mainline -->
| D02 | 首条主链 | 先完整交付真实 `market_analysis`，再启用 Research/Monitor/Inbox/Outcome | 同时铺开全部模式，主链再次失焦 |
<!-- normative:end D02 -->
<!-- normative:start D03 -->
<!-- requirement: decision-d03-agent-runtime -->
| D03 | Agent Runtime | Aegra 自托管开源 Agent Server 承载官方 LangGraph/Agent Protocol Runtime；Next.js BFF 代理浏览器 | 需要自研 Thread/Run/SSE/重放/HITL，或依赖商业 Agent Server 授权 |
<!-- normative:end D03 -->
<!-- normative:start D04 -->
<!-- requirement: decision-d04-agent-harness -->
| D04 | Agent Harness | 使用 LangChain `create_agent`、Tool、Structured Output、Middleware | 重新出现私有 Agent Loop 和 Tool 协议 |
<!-- normative:end D04 -->
<!-- normative:start D05 -->
<!-- requirement: decision-d05-deep-agents -->
| D05 | Deep Agents | 只用于受限研究/委派；不得拥有最终风险、通知和业务库写权限 | pre-1.0 Harness 变成不可替换的生产控制面 |
<!-- normative:end D05 -->
<!-- normative:start D06 -->
<!-- requirement: decision-d06-identity-order -->
| D06 | 身份顺序 | 开发黄金主链允许固定开发账号；最终交付必须完成正式 Auth、Workspace Membership 和同一 ActorContext 接入；生产构建禁用开发身份 | 鉴权阻断早期主链，或最终交付仍是单用户伪产品 |
<!-- normative:end D06 -->
<!-- normative:start D07 -->
<!-- requirement: decision-d07-web-search -->
| D07 | Web Search | 能力探测后使用 Provider built-in；不支持时显式切 Tavily；不可用必须失败可见 | 伪搜索、静默 fallback 或无来源结论 |
<!-- normative:end D07 -->
<!-- normative:start D08 -->
<!-- requirement: decision-d08-frontend-runtime -->
| D08 | 前端 Runtime | `@langchain/react` v1 是当前连接 live projection 的唯一 Runtime；历史/可查询状态从 Product API 读取；选择 AI Elements/shadcn 作为可编辑视觉层 | assistant-ui/CopilotKit 等形成第二 Runtime |
<!-- normative:end D08 -->
<!-- normative:start D09 -->
<!-- requirement: decision-d09-data-authority -->
| D09 | 数据权威 | Product PostgreSQL 是 Task/Run/Artifact/Usage/Feedback/Outcome 权威；Checkpoint 只管执行恢复 | 产品查询依赖 Runtime 内部表，升级和排障失控 |
<!-- normative:end D09 -->
<!-- normative:start D10 -->
<!-- requirement: decision-d10-observability -->
| D10 | 观测 | OpenTelemetry 通过集中出口写入已验证的免费/自托管后端；LangSmith/Langfuse 仅作可选适配且不得成为运行前提 | 双写、重复 generation、付费依赖或观测故障阻断主链 |
<!-- normative:end D10 -->
<!-- normative:start D11 -->
<!-- requirement: decision-d11-v1-migration -->
| D11 | V1 处置 | 迁移规则与 golden cases，不迁移 workflow/orchestration/agent_swarm 实现；不长期双写 | 新项目继续背负旧兼容层 |
<!-- normative:end D11 -->
<!-- normative:start D12 -->
<!-- requirement: decision-d12-implementation-discipline -->
| D12 | 实施纪律 | 每轮中文实施说明、适当中文注释、官方接口证据、测试和真实运行证据缺一不可 | 代码不可追踪，后续维护再次依赖猜测 |
<!-- normative:end D12 -->
<!-- normative:start D13 -->
<!-- requirement: decision-d13-production-proof -->
| D13 | 生产证明 | 接受 `12-production-proof-slo-and-lifecycle.md` 的量化 SLO、hosted Playwright、删除和 Outcome 分级门禁 | 可以用本地 mock、单样本或手工截图冒充生产完成 |
<!-- normative:end D13 -->
<!-- normative:start D14 -->
<!-- requirement: decision-d14-launch-boundary -->
| D14 | 上线边界 | 法律/产品风险评审完成前只允许 Internal Alpha；公开发布需冻结司法辖区、年龄、披露和个性化边界 | 用免责声明替代真正的产品与合规决策 |
<!-- normative:end D14 -->
<!-- normative:start D15 -->
<!-- requirement: decision-d15-production-deployment -->
| D15 | 生产部署 | 使用 ADR 0011 的 Aegra 自托管开源 Profile；生产验收仍必须完成 hosted preflight、退出/恢复证据、三路 Task 0 串行复审、新 manifest 与 attestation，商业 LangSmith Deployment 不得成为前提 | 在部署能力未知、商业许可不满足或治理转换未完成时把本地 Compose 写成生产完成 |
<!-- normative:end D15 -->

## 4. 推荐 ADR 结论

| ADR | 推荐 | 评审重点 |
| --- | --- | --- |
| `0001-agent-runtime-deployment.md` | 开发可用 `langgraph dev`；集成和生产采用 ADR 0011 的 Aegra 自托管开源 Runtime，产品数据库保持独立权限边界 | 许可、区域、退出方案和 Aegra 版本兼容 |
| `0002-web-search-provider.md` | capability probe + built-in/Tavily 显式选择，不允许静默降级 | 自定义模型端点是否支持 Responses web search |
| `0003-identity-and-auth-bootstrap.md` | 非生产固定身份；生产推荐 Auth.js + BFF 短期内部令牌 + Agent Server resource auth | 是否接受 Auth.js 作为默认正式方案 |
| `0004-frontend-presentation-stack.md` | `@langchain/react` 唯一 Runtime，AI Elements/shadcn 作为视觉层 | 是否需要 assistant-ui 的额外能力 |
| `0005-observability-and-prompt-source.md` | OpenTelemetry 集中出口 + 免费/自托管后端；LangSmith/Langfuse 仅作可选适配；Prompt 首版以代码评审版本为发布源 | 免费后端、数据驻留与可选适配的许可边界 |
| `0006-production-slo-retention-and-outcome.md` | 采用量化 SLO、30/365 天默认保留、删除演练和分级 Outcome 样本门禁 | 数值是否需要按部署成本调整 |
| `0007-launch-and-financial-product-boundary.md` | 法律评审前保持 Internal Alpha，不向公众宣称投资建议或收益能力 | 首发地区、最低年龄和字段展示边界 |
| `0008-production-deployment-profile.md` | 已由 ADR 0011 取代；其中区域、网络、Auth、Persistence、HA/SLO、成本和退出项目仅作为 Aegra hosted 证据输入 | 不得恢复商业 Agent Server 前提 |
| `0009-canonical-agent-and-research-harness.md` | canonical Agent 与受限 Research Harness 复用官方 LangChain/Deep Agents 边界 | 禁止第二套通用 Agent loop |
| `0010-task13-restricted-deep-research-harness.md` | Deep Research 委派保持最小权限、预算和结果验证 | 子 Agent 不得绕过 Risk/HITL |
| `0011-aegra-self-hosted-agent-server.md` | 采用 Apache-2.0 Aegra 自托管 Runtime，保留官方 SDK/Protocol/Graph 边界 | durability、HA、Auth、升级与退出证据 |

## 5. 评审时应拒绝的提案

- “先照 V1 结构搬过去，后面再换 LangGraph”。
- “为了统一，自己再包一层 Agent Runtime/Tool Registry/LLM Client”。
- “前端先把 Graph State 或 JSON 全打印出来，后面再产品化”。
- “正式鉴权后置，所以当前先不带 tenant/user 字段”。
- “LangSmith/Langfuse 都手工埋一遍，更保险”。
- “Deep Agents 能做全部事情，所以让它决定 allowed 并直接写数据库”。
- “测试通过就算生产完成，不需要 hosted 真实模型/搜索/行情/视觉证据”。

## 6. 批准方式

评审者可以回复：

```text
批准 D01-D15；ADR 0001-0007、0009-0011 按推荐结论；ADR 0008 由 ADR 0011 取代；允许进入实施计划细化。
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
- ADR 0001-0007、0009-0011 已变更为 Accepted；ADR 0008 保持 Superseded，且不得重新成为商业授权前提。
- Aegra hosted Profile 在进入 Production Proof 前具备完整的许可、区域、网络、Auth、Persistence、HA/SLO、成本和退出证据；此前最多到 Internal Alpha/Beta 技术准备，不宣称生产部署完成。
- 产品、Graph、数据、前端、观测、测试和 V1 删除边界之间没有矛盾。
- `14-v2-final-implementation-plan.md` 的阶段顺序和停止条件获批；`10` 不再作为当前执行权威。
- 才能进入逐文件、逐测试的实施计划，不得直接开始编码。
