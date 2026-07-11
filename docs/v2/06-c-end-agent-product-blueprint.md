# V2 C 端 Agent 产品蓝图

> 状态：Proposed，待用户批准
>
> 日期：2026-07-11
>
> 范围：定义最终商业产品，不包含实现代码和视觉稿

## 1. 产品定义

V2 的最终产品不是“把一次分析结果显示得更漂亮”，而是一个多用户加密市场智能 Agent 工作空间：用户可以在同一会话中提出问题、发起结构化市场分析、委派深度研究、设置持续监控、处理中断、查看报告与证据、比较分支并复盘历史结果。

一句话定义：

> 面向需要事实、证据和风险约束的加密市场用户，提供可实时交互、可后台持续、可审计和可复盘的人工决策辅助 Agent。

产品永久保持 manual-only。系统可以研究、分析、提醒和复盘，但不自动下单、撤单、转账或提现。

## 2. 不被 V1 限制的设计原则

1. `market_analysis` 是第一条价值链，不是唯一页面或唯一 Graph 能力。
2. 用户操作围绕 Thread、Task 和 Artifact，而不是围绕后端 JSON endpoint。
3. 短对话和长任务使用同一 Agent Runtime，但具有不同的 UI、通知和恢复策略。
4. Subagent 是可观察的产品委派，不是为了展示技术复杂度。
5. 业务结果、证据和风险规则必须可读；原始协议和 Trace 只在诊断入口出现。
6. 所有流式、恢复、Interrupt、Queue、Fork 和 Subagent 状态优先使用官方 SDK。
7. 商业化能力进入权限和数据边界，但不能在主流程未跑通前堆出一个空的订阅后台。
8. Generative UI 负责组合受控组件，不允许模型生成任意可执行前端代码。
9. Agent 的不确定性必须显式展示，不能把失败、缺证据或外部依赖不可用包装成成功。
10. 每个用户可见结论都能追溯到事实、来源、模型调用、规则和运行版本。

## 3. 目标用户与角色

| 角色 | 主要目标 | 核心权限 |
| --- | --- | --- |
| Individual User | 获取实时分析、研究、提醒和复盘 | 创建个人 Thread/Task、查看自己的 Artifact |
| Workspace Member | 共享研究与任务结果 | 访问授权 Workspace 资源 |
| Analyst/Operator | 维护监控、处理失败和质量反馈 | 管理计划任务、诊断授权资源 |
| Workspace Owner | 管理成员、配额、订阅和集成 | entitlement、billing reference、成员与审计 |
| Platform Admin | 系统运维和合规支持 | 显式跨租户 action，所有操作审计 |

第一阶段使用固定开发 Owner 身份，但数据模型和后端授权必须始终按上述角色边界设计。

## 4. 产品模式

### 4.1 Interactive Chat

- 支持连续追问、引用历史 Artifact 和启动其他模式。
- 支持 Markdown、Tool card、受控 reasoning block、附件和引用。
- 运行中可以追加消息，由客户端 submission queue、Agent Server worker queue 和 multitask strategy 分层处理；客户端队列不承诺刷新后持久化。

### 4.2 Market Analysis

- 真实交易所数据、Web Research、结构化模型分析、确定性证据和风险门禁。
- 结论必须包含可操作但人工执行的 action、confidence、价格、失效条件和证据。
- blocked 与 failed 是不同产品状态。

### 4.3 Deep Research

- Coordinator 可委派多个只读 Research Subagent。
- 用户看到计划、subagent 状态、来源、阶段进度和渐进 Artifact。
- 长任务可离开页面继续运行，完成或等待人工时进入 Inbox。

### 4.4 Scheduled Monitor

- 使用 Agent Server cron/background run 周期执行。
- 监控事件、价格条件、数据源健康或历史 outcome，不执行交易。
- 支持暂停、恢复、手动触发、下一次运行和失败历史。

### 4.5 Alert Inbox

- 聚合待处理 Interrupt、已触发提醒、后台任务完成、失败恢复和配额告警。
- 用户无需回到原聊天页即可 approve/edit/respond/ignore。
- Inbox 是产品投影，Interrupt 权威状态仍在 LangGraph。

### 4.6 Outcome Review

- 后台采集成熟窗口后的真实市场结果。
- 展示 hit、Brier、PnL、MFE、MAE、no-trade baseline 和证据质量。
- 用户反馈和真实 outcome 进入评测数据集，不直接修改历史结果。

### 4.7 Scenario Compare

- 从 checkpoint fork 不同 query、horizon、假设或提示版本。
- 展示分支来源、共享事实、差异结论、成本和风险变化。
- 原历史不可变，分支是新的 Run/Artifact 版本。

## 5. 信息架构

一级导航按用户目的组织，不暴露所有内部运行对象：

```text
Home
  Market brief / Watchlist / Active tasks / Pending items
Work
  Chat / Analysis / Deep research / Scenario compare
  Thread list / Task status / Artifact inspector
Monitors
  Price / Event / Thesis / Data-source health
Inbox
  Interrupt / Alert / Completion / Failure recovery / Quota
Library
  Reports / Research / Scenario comparisons / Outcomes / Saved evidence
Settings
  Profile / Memory / Notifications / Privacy
  Workspace / Members / Usage / Subscription / Integrations
Admin (authorized only)
```

`Thread`、`Task`、`Run`、`Subagent` 和 `Checkpoint` 是必须稳定的内部/产品对象，但不都占一级导航。桌面 Work 采用三栏：左侧 Thread/Task，中间对话与运行时间线，右侧 Artifact/Evidence/Risk Inspector；移动端转换为分层页面。个人用户只有一个 Workspace 时默认不显示 Workspace 切换器。

产品增加 crypto 领域锚点：Watchlist、Asset/Topic context，以及用户手动录入或只读导入的持仓上下文。持仓上下文只用于风险和关注问题，不授权交易，也不能让模型假设为实时账户事实。

普通用户不进入 LangGraph Studio、LangSmith 或 Langfuse。产品页通过稳定 View Model 展示需要的信息，诊断角色才可跳转到脱敏 Trace。

## 6. 核心用户旅程

### 6.1 首次激活

1. 用户确认 manual-only、风险披露和数据使用范围。
2. 选择 Watchlist、关注主题和通知偏好；模型/Provider 高级设置默认隐藏。
3. 从真实资产上下文直接发起第一次分析，不先要求理解 Thread、Run、Trace 或 Workspace。
4. 一次会话内形成首个可读 Artifact，并给出追问、创建 Monitor 和保存到 Library 的入口。

### 6.2 首次真实分析

1. 用户在 Chat 或 Analyze 输入 symbol、horizon 和关注问题。
2. UI 立即 optimistic 显示请求，并获得 Thread/Task 标识。
3. 页面显示行情采集、研究、分析、门禁和持久化阶段。
4. Coordinator 的消息与 subagent 卡片分开渲染。
5. Evidence 和 Artifact 随运行渐进更新，不等待最后一次性返回 JSON。
6. 成功后首屏展示结论、风险和关键证据；详情提供来源、规则和诊断入口。
7. 用户可追问、反馈、设置监控或从 checkpoint 创建比较分支。

### 6.3 长研究离开后返回

1. 用户发起 Deep Research，系统立即确认 Task 已创建。
2. 用户关闭页面；`disconnect()` 只断开 UI，后台 Run 继续。
3. Coordinator 和 subagent 持续写入官方事件流、checkpoint 和稳定 Artifact 投影。
4. 用户返回 Tasks 或原 Thread，SDK 使用 sequence replay 重新附着。
5. UI 不重复消息和 Tool card，恢复到最新阶段。
6. 完成、失败或等待人工时，Inbox 和配置的通知渠道收到事件。

### 6.4 人工处理 Interrupt

1. 高风险外部动作或计划变更触发官方 Interrupt。
2. Inbox 显示原因、建议动作、影响、证据和 schema 对应控件。
3. 用户 approve、reject、edit 或 respond；多个并行中断可统一 `respondAll()`，subagent Interrupt 必须携带 interrupt ID 和 namespace。
4. 需要同时修正 State 时使用原子 respond update。
5. 原 Thread 恢复，所有页面实时同步，不创建隐藏的新任务。

### 6.5 编辑并比较结果

1. 用户选择历史消息或 checkpoint，点击编辑/重新生成。
2. 编辑/重生成可在同一 Thread 通过 `forkFrom` 形成新的 canonical continuation，旧 checkpoint 历史仍可审计，但不能把同一 Thread 描述成永久并列的两条产品分支。
3. 长期 Scenario Compare 创建新的产品 Task/Thread lineage，并记录 `forked_from_thread_id` 与 `forked_from_checkpoint_id`。
4. 新旧任务共享已声明可复用的事实，其余节点按规则重跑。
5. Compare View 展示输入、证据、结论、风险、成本和版本差异，两个 Artifact 均不可变保留。

### 6.6 从结论创建 Monitor

1. 用户在 Analysis/Research Artifact 选择“持续关注”。
2. 设置条件、频率、有效期、静默时段和通知渠道。
3. 每次触发创建新的实时分析 Task，不能复用旧结论冒充当前结论。
4. 触发、降噪、失败和暂停进入 Monitors/Inbox，并可追溯到原 thesis。

### 6.7 Outcome 信任闭环

1. 观察窗口成熟后，Inbox 提示用户查看 Outcome。
2. Library 展示实际走势、假设失效点、Brier/MFE/MAE、no-trade baseline 和数据完整性。
3. 用户反馈进入评测数据集，历史 Artifact 保持不可变。

### 6.8 配额与升级

1. 昂贵研究或 Monitor 创建前显示预计额度和当前余额。
2. 超限时保留用户输入和 Task draft，后端阻止执行并提供升级入口。
3. 外部支付完成并更新 entitlement 后继续原 draft，不要求用户重新填写。

## 7. Agent 交互组件

| 组件 | 必须状态 | 数据来源 |
| --- | --- | --- |
| Message | streaming、complete、error、edited | `messages` selector |
| Tool Card | queued、running、approval、success、error | `toolCalls` selector |
| Subagent Card | discovered、running、complete、error | `stream.subagents` + scoped selectors |
| Task Progress | queued、active stage、waiting、complete | `custom:task_progress` extension |
| Evidence Panel | loading、verified、conflict、expired | `custom:evidence` + business API |
| Artifact Workspace | creating、updating、versioned、failed | `custom:artifact` + artifact API |
| Interrupt Card | pending、responding、resolved、stale | `interrupts` / `respond` |
| Usage Indicator | estimated、actual、quota warning | `custom:usage` + usage ledger |
| Connection Banner | connected、reconnecting、offline | SDK transport state |

所有组件必须处理空值、部分结果、长文本、移动端、键盘、屏幕阅读器和 reduced-motion。不得用 `<pre>` 原样显示模型或 Tool JSON 作为正式体验。

## 8. Artifact 与 Generative UI

Artifact 是独立于对话消息的持久产品对象，适合：

- 市场分析报告。
- 事件时间线和证据集。
- 场景比较。
- Outcome 复盘。
- 可导出的 Markdown/PDF/结构化数据。

首批固定 Artifact type：

```text
analysis_report
research_report
evidence_bundle
scenario_comparison
outcome_review
```

每个 Artifact 具有 owner、workspace、task、run、schema version、content version、source references、status 和 visibility。

Artifact 渐进更新只作用于未 committed 的 draft/streaming version；一旦 committed，任何修正都创建新版本并保留 lineage。分享和导出权限以 committed version 为单位。

Generative UI 采用受控组件注册表：模型只能选择诸如 `MarketSnapshotPanel`、`EvidenceTimeline`、`RiskDecisionPanel`、`ScenarioComparison` 等组件及其 schema-validated props。组件版本由产品代码控制；未知组件、未知 props、脚本、HTML 和任意 JSX 必须拒绝。

OpenUI 类能力可用于生成报告和探索性 dashboard，但不能取代确定性的风险、交易事实和最终决策组件。

## 9. 前端框架选择

运行时状态层固定为：

- `@langchain/react` v1。
- `@langchain/langgraph-sdk`。
- Agent Server Protocol v2 official transport。

视觉组件有两个候选，实施前通过 ADR 二选一：

| 方案 | 优点 | 风险 | 推荐场景 |
| --- | --- | --- | --- |
| AI Elements | shadcn 风格、组件可直接编辑、容易与业务组件统一 | Thread/branch 管理需由官方 SDK 自行组合 | 产品需要强视觉控制时优先 |
| assistant-ui | 完整 headless chat runtime、附件、branching、thread UX 成熟 | 必须避免与 `@langchain/react` 形成双 Runtime | 仅作为 presentation adapter 明确可行时 |

CopilotKit 只有在明确需要 AG-UI、shared state 或 frontend tools 时才引入；否则会增加第二套协议和状态适配。OpenUI 只作为 Artifact renderer 候选，不作为整个应用 Runtime。

## 10. 长任务与并发模型

- 每个用户可同时创建多个 Task；每个 Task 有明确 owner、priority、status 和 budget。
- 前台 stream 不是任务生命周期，`disconnect()` 只停止 UI 订阅；`stop()` 默认取消当前服务端 Run。
- 同一 Thread 的新消息使用客户端 submission queue 或显式 multitask strategy；需要跨刷新/设备持久保证的输入进入服务端 command/worker queue。
- 取消必须区分：停止 UI 订阅、取消当前 Run、取消整个 Task、暂停 Cron。
- Background Run、Cron 和 Webhook 均使用官方 Server 能力和幂等业务 handler。
- Task Center 支持按状态、模式、symbol、时间和 owner 查询。
- 失败必须保存分类、已完成阶段、可恢复 checkpoint 和建议动作。

## 11. 商业化基础

### 11.1 Workspace 与 Entitlement

Entitlement 至少控制：

- 可用产品模式。
- 模型等级和 Provider。
- 并发 Task 数。
- 每月模型 Token、搜索、Artifact 存储和通知额度。
- Thread/Trace/Artifact 保留期。
- Scheduled Monitor 数量和最小频率。
- Team、Admin、诊断和导出能力。

所有限制必须在 Agent Server/Auth/Tool/Middleware 或业务 Repository 后端执行，不能只在前端禁用按钮。

### 11.2 Usage Ledger

每次 Run 记录不可变用量：model tokens/cost、search calls、market calls、artifact bytes、runtime duration、notification attempts。账单聚合可以重算，原始 ledger 不覆盖。

### 11.3 Billing Boundary

V2 只保存 external customer/subscription/price reference、entitlement snapshot 和 webhook audit。价格、税费、支付方式和发票由 Stripe 等成熟支付平台管理，Agent Runtime 不实现支付核心。

### 11.4 Integrations

首批开发验证可以使用 Bark，但商业 C 端至少需要 In-app Inbox 加 Web Push 或 Email 之一。最终边界支持 Slack/Discord/Telegram、webhook 和 MCP/OAuth 数据源。所有 OAuth token 进入专用 secret store，不能进入 Graph State、Prompt、Trace 或业务 JSON。

### 11.5 用户可控 Memory

- 用户可以查看、删除、关闭和限定长期 Memory 的作用域。
- Workspace setting、entitlement、通知和隐私配置只在 Product DB，不写入 LangGraph Store。
- Store 只保存明确允许的偏好或 Agent memory，namespace 包含 workspace/user/purpose。
- Memory 不能把历史价格、旧方向、旧新闻或过期结论重新当作 live evidence。

## 12. 安全与可信边界

- 永久禁止自动交易和交易/提现密钥。
- 市场执行事实只来自 exchange-native 或批准的成熟市场数据适配器。
- Web Search 只能提供事件和研究上下文。
- Tool 权限按 workspace、role、entitlement 和 Agent role 动态过滤。
- PII、密钥、Cookie 和 Authorization 在模型、流、Trace 和日志出口前脱敏。
- Headless browser/device Tool 默认禁用；若未来启用，必须 sandbox、域名 allowlist、HITL 和审计。
- 任何外部写副作用都需要幂等、权限、预算和必要的 HITL。
- 不能展示或声称保存模型私有 chain-of-thought。

## 13. 分阶段启用而不推倒架构

| 阶段 | 必须上线 | 预留但不阻断 |
| --- | --- | --- |
| Foundation | Workspace/identity 字段、Thread/Task/Run、Protocol v2、usage 基础 | 正式登录、支付 |
| Main Flow | Home、Work、Inbox、Library、Market Analysis、真实数据/搜索/模型、风险门禁、analysis_report Artifact | Deep Research、Cron |
| Agent UX | Tool/Subagent/HITL/Artifact、rejoin、移动端 | 多模态、Generative UI 扩展 |
| Async | Tasks、Inbox、queue、background、cron、webhook | 多渠道集成 |
| Commercial | Auth、entitlement、quota、usage、subscription reference | Team/enterprise features |
| Quality | LangSmith/Langfuse、feedback、dataset、outcome | 高级实验和自动评测 |

“预留”必须体现为稳定 ID、表字段、接口边界和权限点，不等于创建空页面、假接口或未使用抽象。

## 14. 参考产品结论

| 参考 | 应借鉴 | 不直接照搬 |
| --- | --- | --- |
| Agent Chat UI | Thread、Tool、Markdown、Artifact、Interrupt、API proxy | 通用聊天信息架构 |
| Deep Agents UI | Todo、Subagent、审批、checkpoint rerun | 旧 SDK API 和代码仓库工具权限 |
| Open SWE | 长任务、运行中追加消息、并行任务、持久 sandbox、集成入口 | 软件工程专用 sandbox 和写权限 |
| Open Canvas | Chat + Artifact、版本、长期记忆、快速动作 | 文档编辑器作为全部产品中心 |
| Agent Inbox | 异步 HITL、独立收件箱、approve/edit/respond/ignore | 与 Graph Interrupt 分离的第二权威状态 |
| Agent Auth Payments | Auth、订阅、credits、RLS、web/agents 分离 | 将示例支付模型直接当生产账本 |
| Open Deep Research | 多搜索 Provider、可配置研究、计划批准、Dataset eval | 无风险门禁的纯研究输出 |

## 15. 产品完成定义

V2 只有同时满足以下条件才可称为成熟商业产品：

- 用户可以从同一工作空间完成短对话、结构化分析和后台长任务。
- 断线、刷新、跨页面和多设备返回后，运行状态一致且无重复事件。
- Coordinator、Subagent、Tool、Artifact、Interrupt、Evidence、Risk 和 Usage 都有正式产品组件。
- 每个结果可追溯到来源、模型、Prompt、规则、Run、Checkpoint 和观测记录。
- 多用户授权、workspace 隔离、entitlement 和 quota 在后端生效。
- 真实模型、搜索、行情、数据库、通知、视觉回归和成熟 outcome 均有同一 Run 的证据。
- 没有第二套 Agent Runtime、Event Bus、Checkpoint、HITL 或前端 Graph Store。
- 没有自动交易、隐瞒失败、空 JSON、generic success 或 silent fallback。

## 16. 需要用户评审的决策

1. 最终产品定位是否接受“Crypto Intelligence Agent Workspace”，而不是沿用 Manual Alert 作为产品名称和信息架构。
2. 首条交付仍以 `market_analysis` 为主，但是否接受 Thread/Task/Artifact/Usage 等最终对象第一天建立。
3. 前端视觉层在 AI Elements 与 assistant-ui 中实施前二选一，是否接受 `@langchain/react` 永远作为唯一 Runtime 状态源。
4. 是否接受 Deep Agents 只负责受限研究与委派，最终风险与副作用永远由确定性 Graph Node 控制。
5. 是否接受商业化先建立 entitlement/usage/subscription reference，再分阶段接入正式支付和团队能力。
