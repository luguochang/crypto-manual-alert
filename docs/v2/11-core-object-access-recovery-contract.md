# V2 核心对象、权限与恢复契约

> 状态：Proposed，评审必读
>
> 日期：2026-07-12
>
> 目的：冻结容易在实现阶段产生第二套状态机的对象基数、权限、恢复和前端降级规则

## 1. 发布层级与页面边界

| 层级 | 对外性质 | 可见页面 | 不允许出现 |
| --- | --- | --- | --- |
| Technical Slice | 仅开发/CI | 单个受控 Work 测试页 | Home/Inbox/Monitor 空壳导航 |
| Internal Alpha | 内部用户 | Work、Task/Run Detail、最小 Library | 未实现的 Monitor/Billing/Admin 入口 |
| External Beta | 邀请用户 | Home、Work、Inbox、Library、Settings | 无授权诊断页、伪共享/伪配额 |
| Commercial GA | 正式发布 | 全部批准模式和商业能力 | 未量化 SLO、未完成法律/安全评审 |

首条 `market_analysis` 属于 Internal Alpha 垂直切片。最终信息架构可以先设计，但页面只有在有真实数据、操作和状态闭环时才进入导航。

## 2. 核心对象与基数

```text
Workspace 1 -- n Thread
Thread    1 -- n Task
Task      1 -- n Run
Run       1 -- n SubagentInvocation
Task/Run  1 -- n ArtifactVersion
Run       0 -- n Interrupt
Run       0 -- n ProductEventProjection
```

- Thread：长期会话和上下文容器，不等于一次执行。
- Task：用户可理解的工作单元；一次 market analysis、research 或 compare 各是一个 Task。
- Run：Task 的一次不可变执行尝试。Retry、Resume、Fork 都产生新 Run。
- Message：属于 Thread，并保存产生/消费它的 Task/Run 关联。
- Artifact：属于 Task，可由多个 Run 产生版本；committed version 不可变。
- Interrupt：属于具体 Run/checkpoint/namespace，解决后不可再次响应。

一个普通聊天消息可以只更新 Thread；当它启动 Tool、分析、研究或外部成本时必须创建 Task。一个 Task 同一时间默认只有一个 active Run；并行 Scenario Compare 使用多个子 Task，而不是让一个 Task 有多个互相竞争的权威 Run。

## 3. 通用产品表

必须存在：

- `agent_threads`
- `agent_tasks`
- `agent_runs`
- `task_commands`
- `messages`
- `subagent_invocations`
- `artifacts` / `artifact_versions`
- `interrupt_inbox`
- `product_event_projections`

模式表如 `analysis_results`、`research_reports` 只保存业务结果，不复用为通用 Run 表。

`task_commands` 是唯一允许的持久 pending-input/admission 层，字段至少包含 command ID、thread/task、actor、type、payload hash、sequence、status、lease owner/expiry、attempt 和 idempotency key。Dispatcher 只把命令翻译成官方 Server command/Run，不执行 Graph Node、不保存 Graph State、不实现 Tool/Agent Loop；同一 Thread 默认按 sequence 串行派发，取消和删除有明确终态。

## 4. 操作语义

| 用户动作 | Thread | Task | Run | Artifact |
| --- | --- | --- | --- | --- |
| Continue chat | 同一 | 无成本时可无新 Task | 按需 | 引用已有 |
| Start analysis/research | 当前或新建 | 新建 | 新建 | draft |
| Resume interrupt | 同一 | 同一 | 新建 resume Run | 延续 draft/new version |
| Retry failure | 同一 | 同一 | 新建 retry Run | 新版本 |
| Edit/regenerate | 同一 | 同一 | 从 checkpoint 新 Run | 新版本，成为 canonical continuation |
| Scenario compare | 新 lineage Thread | 新 Task | 新 Run | 并列不可变版本 |
| Cancel run | 同一 | 可能仍可重试 | 当前 Run cancelled | 保留已提交版本 |
| Cancel task | 同一 | cancelled | active Run 取消 | 保留历史，停止继续生成 |

## 5. ACL 与可见性

Visibility 枚举：

```text
private
workspace
restricted
```

- 默认 `private`，仅 owner user 和授权 operator 可访问。
- `workspace` 允许当前 Workspace Member 按 role 访问。
- `restricted` 使用显式 principal/role 列表，用于敏感 Artifact、运维和合规记录。
- Thread 的可见性是 Task/Run/Message 默认值；子资源可以收紧，不能无审批扩大。
- Artifact 分享不会自动分享来源 Thread 的所有消息；只分享 Artifact、允许的 Evidence 和最小 lineage。
- 成员移除后立即失去 Workspace 资源访问，历史审计记录保留匿名内部 ID。
- Inbox 默认只投递给任务 owner；委派必须创建 assignment 和审计事件。
- Operator 只能访问被授权资源；Platform Admin 跨租户动作需要显式 action、理由和审计。

## 6. Development Auth 硬门禁

- 仅 `local/test` 环境。
- 仅 loopback bind 和 loopback Origin/Host。
- preview/staging/production 检测到开发身份时启动失败。
- 默认角色 `member`，无 owner/operator/admin。
- 真实管理、成员、计费、跨租户、生产 Integration 和高敏感通知关闭。
- 授权测试至少包含 user-a/user-b、tenant-a/tenant-b 和 operator fixture。

## 7. 长任务重连与页面重建

客户端恢复分三层：

1. SDK hydration：读取 Thread 当前 state/history。
2. Product reconstruction：始终读取 Task/Run snapshot、Artifact 和分页 `product_event_projections` 形成稳定历史。
3. SDK live stream：hydration 后由官方 Transport 处理其支持的 replay/ordering，并覆盖当前运行投影。

每个 projection 保存 `run_id`、`sequence/version`、`event_type`、`summary payload`、`occurred_at`。不保存每个 token，但必须足以重建阶段、Tool/Subagent 摘要、Artifact 版本、风险和错误时间线。

React v1 没有公开 replay-gap 信号，因此前端不自行检测 sequence gap。页面先显示“正在恢复任务记录”，完成 durable reconstruction 后再接入 live stream；stream error 时保留稳定历史并查询 Product Task 状态。历史只保存摘要时明确标记“实时逐字流未长期保留”。

## 8. 崩溃与 Orphan Recovery

- `agent_runs` 保存 `last_heartbeat_at`、`recovery_deadline_at`、官方 run/checkpoint ID。
- reconciliation worker 对比 Product DB 与官方 active run/checkpoint。
- 可恢复：创建 resume Run，旧 Run 标记 superseded。
- 不可恢复：旧 Run 标记 `orphaned_failed`，保留已提交 Artifact，向用户提供 Retry。
- 禁止把无 active runtime 的记录永久留在 `running`。
- 自动恢复次数、deadline、RTO/RPO 和用户文案由环境 SLO 冻结。

## 9. Interrupt 生命周期与竞态

- Interrupt 只能 `approve/edit/respond/reject/cancel/expire`。
- `dismiss/ignore` 仅适用于非阻塞通知，不能改变 waiting_human Graph。
- expire 由服务端根据 policy 触发，并提交 timeout response 或取消 Run。
- 请求携带 interrupt ID、namespace、checkpoint ID 和 response version。
- `(interrupt_id, checkpoint_id, response_version)` 是幂等键。
- 第一个成功响应获胜；其余返回 `INTERRUPT_ALREADY_RESOLVED`。
- 多个同 checkpoint Interrupt 使用一次 `respondAll()`。
- Interrupt 前无非幂等副作用，恢复从节点开头重执行的行为必须有测试。

## 10. View Model 与 Schema 兼容

每个产品 View Model 包含：

- `schema_version`
- `status`
- `completeness`
- `warnings`
- `source_refs`
- 稳定用户字段

兼容规则：

- 当前版本和前一 minor schema 可直接渲染。
- 缺少可选字段显示局部 skeleton/unknown，不隐藏整个记录。
- 缺少关键字段显示可读“结果不完整”，保留可用行情、证据和风险。
- 未知 Tool 渲染通用安全卡片：名称、状态、时间、脱敏摘要；不展示 raw payload。
- 未知 Generative UI 组件拒绝渲染并回退 Artifact 摘要。
- 旧 Artifact 提供只读 migration/view adapter；诊断 JSON 仅授权角色可见。

## 11. 移动端交互契约

- Work 首屏只有当前任务、结论摘要、状态和输入，不复制桌面三栏。
- Thread/Task 列表、Artifact、Evidence、Risk 使用全屏层级和稳定返回栈。
- Inbox 深链接返回来源 Task；跨设备回到 Task Detail。
- 后台任务状态和 Inbox badge 常驻但不遮挡输入。
- 支持中文 IME、safe area、44px 触控目标、横竖屏、附件和离线重连。
- 深滚动期间 sticky 元素不能遮挡结论、风险或操作。

## 12. 可访问性契约

目标为 WCAG 2.2 AA：

- 流式 token 不逐 token 进入 assertive live region；按语义段落节流播报。
- 新消息和阶段更新不抢输入焦点。
- Interrupt 对话打开后聚焦标题/首控件，关闭或处理后恢复触发元素。
- waiting_human 超时支持延长或重新打开，不能只靠倒计时。
- blocked、failed、warning 不只用颜色区分。
- 图表、价格区间和 Evidence Timeline 提供文字表格或摘要。
- reduced-motion 关闭非必要动画，连接状态变化不闪烁。
- 自动化 axe + Playwright 键盘流程 + 人工屏幕阅读器抽查作为发布证据。

## 13. 评审结论

本契约获批前，不得开始数据库、Auth、React Thread、Inbox、Fork 或长任务实现。任何实现与本契约冲突时先修文档/ADR，不通过兼容 wrapper 同时保留两套语义。
