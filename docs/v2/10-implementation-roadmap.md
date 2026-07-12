# V2 评审后实施路线图

> 状态：Proposed，等待设计评审批准
>
> 日期：2026-07-12
>
> 边界：这是阶段路线图，不是开始编码的授权

## 1. 总规则

- 每阶段只在上一阶段退出条件全部满足后开始。
- 每阶段先写测试和本轮实施说明，再写实现。
- 每阶段必须引用实际使用的官方接口和锁定版本。
- 任意通用自研 Runtime/Wrapper 需求先停工写 ADR。
- Mock 只证明契约；阶段完成必须有对应层级的真实证据。
- 所有失败必须保留并修复，不得通过 fallback、skip 或 generic success 掩盖。

## 2. Phase 0：官方 Skeleton 与协议证明

目标：证明官方框架、Agent Server、React SDK、PostgreSQL/Redis 和默认身份可以最小闭环。

交付：

- 独立 V2 应用目录和锁定依赖。
- 一个 canonical `StateGraph`，一个 `create_agent` 节点，一个 typed custom projection。
- `langgraph dev` 和容器化 `langgraph up` 基线。
- Next.js BFF 和单根 `useStream` 页面。
- 固定 `dev-tenant/dev-user` ActorContext。
- Thread 创建、流式 token/tool/value、停止、刷新重连、历史恢复。
- LangSmith Trace 与 Langfuse Callback 同时可见且不重复手工 generation。

退出条件：

- 浏览器提交一次请求并获得真实模型 Structured Output。
- 刷新后重新附着同一 Thread，无重复消息。
- Agent Server 重启后 Thread/Checkpoint 可恢复。
- 生产模式未带身份时 fail-closed，开发身份不能在生产配置启用。
- 没有自定义 SSE、Thread Store、Agent Loop 或 LLM HTTP Client。

## 3. Phase 1：真实 Market Analysis 主链

目标：先完成用户最关心的真实业务闭环。

交付：

- 交易所原生市场快照 Tool。
- Web Search capability probe、built-in/Tavily 显式路由和 Evidence schema。
- LangChain Structured Output 的 MarketAnalysis。
- 纯函数 Evidence Gate 和 Risk Gate。
- Product PostgreSQL 渐进投影、Artifact、Usage 和 Outbox。
- Bark 通知适配与 unknown/sent/failed 状态。
- 前端业务组件展示行情、证据、模型结论、风险门禁和通知。

退出条件：

- 同一个真实 Run 具有模型、行情、搜索、风险、数据库和通知证据。
- 普通页面没有原始 JSON/Python repr/密钥。
- 外部阶段失败时已完成产物仍可查询；Run 状态准确为 failed/blocked，降级通过 completion scope、warnings 和 Artifact completeness 表达。
- 模型不能覆盖确定性 blocked 结果。
- Playwright 桌面和移动端覆盖 pending、success、blocked、partial、failed、reconnect。

## 4. Phase 2：Agent UX、Artifact 与 HITL

目标：从“一次分析表单”升级为可持续使用的 Agent 工作空间。

交付：

- Home、Work、Task/Run/Artifact Detail、Inbox、Library 的首版闭环。
- Tool card、Subagent tree、Evidence timeline、Risk panel、Artifact Inspector。
- approve/edit/reject/respondAll 和待处理 Interrupt Inbox。
- checkpoint fork、retry、scenario compare 基础。
- Markdown 安全、附件降级、可访问性和移动端深滚动。

退出条件：

- Interrupt 刷新后仍可处理，响应后 Graph 正确恢复。
- Subagent 只按展开组件建立 scoped subscription。
- `disconnect`、`stop run`、`cancel task` 的含义和 UI 不混淆。
- Visual regression 和 DOM 扫描无重叠、溢出、重复 ID 和焦点断点。

## 5. Phase 3：长任务、队列、Monitor 与 Inbox

目标：支持页面关闭后继续的研究和周期任务。

交付：

- Background Run、官方 multitask strategy、持久 Task/Command admission。
- Deep Agents 受限 research subgraph，预算、深度、Tool 和权限固定。
- Agent Server cron、Monitor、Webhook、完成/失败通知和 Inbox。
- 长任务 rejoin、progress、artifact version 和 subagent 状态。

退出条件：

- 页面关闭后任务继续，重新登录/重连后可恢复。
- Cron 每次创建新的实时 Task，不复用旧结论。
- Deep Agents 无可用文件、Shell、数据库写入、通知和风险裁决权限；若 filesystem tool 因 Harness 必需而存在，调用必须 deny-all，且 general-purpose subagent 已关闭。
- 重试所有权和总预算经过故障注入验证。

## 6. Phase 4：观测、评测和结果闭环

目标：建立可以持续改进而不污染生产主链的质量系统。

交付：

- LangSmith Dataset、Experiment、Evaluator 和 Release Gate。
- Langfuse session/user/cost/latency/error dashboard、masking 和 sampling。
- 产品 Feedback、Correction、Outcome Collector 和 no-trade baseline。
- Prompt/Graph/Rule/Schema version 全链路关联。

退出条件：

- 正常、缺数据、过期、冲突、模型错误、通知错误样本均可回放。
- 观测平台不可用不阻断业务。
- 至少一个成熟 outcome 进入版本化评测协议，只证明管道；Beta/GA 的金融质量报告满足 `12-production-proof-slo-and-lifecycle.md` 的分级样本门禁。
- 发布门禁能阻止结构、证据、风险或产品投影回归。

## 7. Phase 5：正式用户与商业化基础

目标：启用正式身份，而不重写已经跑通的 Graph 和产品 DTO。

交付：

- Auth.js 正式身份、Workspace、membership、role 和 resource auth。
- Entitlement、quota、usage ledger、subscription reference 和 integration secret。
- 用户设置、Memory 控制、数据导出/删除和审计。
- 跨租户安全测试和管理员操作审计。

退出条件：

- 用户 A 无法读取、恢复、取消或反馈用户 B 的资源。
- 切换正式 IdentityProvider 不修改 Graph State schema。
- 配额和权限在后端 admission 强制，不能只靠 UI 隐藏。
- 默认开发身份在生产构建中不可启用。

## 8. Phase 6：生产证明与 V1 清理

目标：达到真正可交付，而不是本地可演示。

交付：

- 公网 HTTPS Next.js + Agent Server。
- 生产 PostgreSQL/Redis/Object Storage、备份、恢复、告警和 Runbook。
- Hosted real model/search/market/notification/visual proof。
- 负载、故障、密钥轮换、跨租户和恢复演练。
- V1 业务规则迁移完成，Runtime/兼容层删除清单完成。

退出条件：

- `03-v2-delivery-checklist.md` 全部通过。
- 同一真实 Run 通过 API、桌面、移动端、Trace、数据库和通知证据核验。
- 无 P0/P1、无 silent fallback、无未批准自研 Runtime。
- V2 production code 不 import V1 workflow/orchestration/agent_swarm。
- 文档、中文注释、实施说明和 Runbook 能支持新维护者独立排障。

## 9. 每阶段必须提交的证据

- `docs/v2/implementation/YYYY-MM-DD-<phase>-<slice>.md`。
- 变更文件和职责清单。
- 官方文档/API 链接与锁定版本。
- 测试命令、退出码、通过/跳过/失败数量。
- 真实 Run/Thread/Trace/Artifact ID。
- Playwright 截图或视频、视觉基准和 DOM 扫描结果。
- 新增自定义封装审计；若存在，对应 Accepted ADR。
- 未完成项、责任边界和下一阶段入口。

## 10. 停止条件

出现以下任何情况必须停止实现并回到评审：

- 需要建立第二套 Agent Runtime、Event Bus、Checkpoint、HITL 或前端 Graph Store。
- 官方 API 与设计文档不一致或已废弃。
- Deep Agents 权限无法按设计限制。
- Agent Server 部署、许可、数据驻留或 Auth 不能满足要求。
- 需要永久兼容 V1 或双写 V1/V2。
- 无法用测试和真实证据证明阶段出口。
