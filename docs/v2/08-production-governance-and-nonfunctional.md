# V2 生产治理与非功能规范

> 状态：Proposed，待用户批准
>
> 日期：2026-07-12
>
> 目的：冻结生产级数据权威、幂等、重试、观测、安全、保留和量化验收边界

## 1. 为什么需要独立规范

官方 Agent 框架解决运行时、事件、恢复和交互能力，但不会替产品决定：哪一份数据是权威、失败前如何保存中间结果、通知是否会重复、多个重试层如何避免成本爆炸、双观测平台如何去重、用户数据保存多久、系统承诺什么 SLO，以及金融分析的合规和评测边界。

这些问题如果留到实现阶段临时决定，即使使用 LangChain 官方接口，仍会形成一套难以维护和证明的生产系统。

## 2. 部署决策门禁

开始实现生产部署前必须完成 ADR：

```text
docs/v2/adr/0001-agent-runtime-deployment.md
```

ADR 必须冻结：

- LangSmith Deployment/Agent Server 的具体部署形态和许可。
- Cloud、自托管或混合方案。
- 部署区域、数据驻留和出站网络。
- Agent Server、PostgreSQL、Redis、对象存储和 Next.js 的故障域。
- custom routes、Auth、Protocol v2、Cron、Webhook 和备份能力是否可用。
- custom route auth、auth-first middleware order、系统路由隔离和未使用路由关闭方式。
- HA、容量、滚动升级和版本兼容组。
- 成本上限和退出方案。
- 何时允许转为自管 Runtime，以及迁移不会改变前端/业务契约的证明。

设计默认采用 Agent Server + Next.js BFF，但“默认采用”不等于跳过上述许可和生产能力核验。

## 3. 数据权威与持久化时机

### 3.1 System of Record

| 数据 | 唯一权威 | 其他系统的角色 |
| --- | --- | --- |
| Graph 执行状态/Interrupt/Checkpoint | LangGraph Checkpointer | 产品表只保存可查询投影 |
| Thread 长期 Agent memory | LangGraph Store | 业务设置不得写入 Store |
| 用户/Workspace/Entitlement/设置 | Product PostgreSQL | Graph 通过 ActorContext/Runtime 只读获取 |
| Task/Run/状态转换 | Product PostgreSQL | Agent Server ID 作为关联字段 |
| 市场快照/证据/模型结构化输出 | Product PostgreSQL/Object Storage | Checkpoint 只保存 ID 和必要摘要 |
| Artifact/版本 | Product PostgreSQL/Object Storage | Event stream 发布最新投影 |
| 原始实时 wire event | Agent Server buffer | 可选短期技术归档，不作为产品历史 |
| Trace | LangSmith 为 Agent 调试权威 | Langfuse 为生产运营与成本视图 |
| Prompt 发布版本 | LangSmith Prompt/代码版本二选一 ADR | Langfuse 只观察使用情况，不成为第二发布源 |
| Feedback | Product PostgreSQL | 单向同步到 LangSmith Dataset/Langfuse score |
| Outcome | Product PostgreSQL | 同步到评测 Dataset，不从观测平台反写 |
| Usage Ledger | Product PostgreSQL immutable ledger | LangSmith/Langfuse 用于核对和分析 |

### 3.2 渐进持久化

不能等到最后 `persist_result` 才保存所有业务数据。每个外部成本或不可重建阶段完成后，通过幂等业务投影写入：

```text
Task accepted
Market snapshot collected
Research evidence accepted/rejected
Agent structured output completed
Evidence gate decided
Risk gate decided
Final artifact committed
Notification planned/sent
Run completed/failed/blocked/cancelled
```

Graph Node 不直接散落 SQL。采用单一 Product Projection service/repository，在节点边界或官方 lifecycle/custom extension consumer 中执行幂等写入。每条状态转换具有 `task_id`、`run_id`、`checkpoint_id`、`sequence/version`、`occurred_at` 和 payload schema version。

### 3.3 恢复一致性

- Checkpoint 比业务投影新：恢复前补投影，使用版本号幂等 upsert。
- 业务投影比 Checkpoint 新：禁止倒退；标记 reconciliation required 并人工/后台校正。
- Resume 创建新 Run，Task 不变，记录 `resume_of_run_id`。
- Retry 创建新 Run，记录 `retry_of_run_id`。
- Fork 创建新分支 Run/Artifact，记录 `forked_from_checkpoint_id`。
- 任何 reconciliation 不修改不可变历史，只追加修正事件。

### 3.4 Durability 与 Subgraph Persistence

| 场景 | Durability | 规则 |
| --- | --- | --- |
| Protocol v2 普通人工分析/研究 | 服务端有效默认，基线 `async` | 调用面不支持 per-run 覆盖，记录实际配置并通过恢复测试 |
| 服务端创建且 API 明确支持的高价值任务 | `sync` 可选 | 只在类型/OpenAPI 证明可表达时使用；通知仍走事务 Outbox |
| 服务端纯离线计算 | `exit` 可选 | 只在支持的调用面使用，禁止用于 HITL/长任务 |

Protocol v2 UI Run 使用并记录 Agent Server 有效默认 durability；当前接口不能表达 per-run `sync/exit`。传统 Run API 或服务端内部调用只有在锁定类型/OpenAPI 证明支持时才可显式选择。Research subgraph 默认 `checkpointer=None` 继承父图；per-thread `checkpointer=True` 需要单独 ADR、固定 namespace、禁止同 subgraph 并行调用和专项恢复测试。

## 4. 状态机

### 4.1 Task 状态

```text
queued -> running -> waiting_human -> running
queued -> cancelled
running -> succeeded | blocked | failed | cancelled
waiting_human -> blocked | cancelled | running
```

### 4.2 Run 状态

```text
created -> queued -> running
running -> waiting_human | succeeded | blocked | failed | cancelled
waiting_human -> responded
responded -> superseded_by_resume_run
running -> recovery_pending -> superseded_by_resume_run | orphaned_failed
```

`agent_runs` 是通用不可变执行尝试；模式结果存入独立结果表。Agent Server/Checkpointer 是执行活性的权威，Product PostgreSQL 是用户可查询状态转换和审计的权威；二者通过版本化映射投影，不允许各自独立决定最终状态。

### 4.3 Artifact 状态

```text
draft -> streaming -> committed
draft|streaming -> failed
committed -> superseded_by_new_version
```

Committed version 不可变。更新创建新的 `artifact_version`，不能原地覆盖用户已经引用或导出的内容。

### 4.4 Monitor 状态

```text
draft -> active -> paused -> active
active|paused -> expired | disabled
active -> degraded -> active|paused|disabled
```

每次触发产生独立 Task/Run；Monitor 只保存 definition 和 trigger history，不保存“可复用的实时结论”。

### 4.5 Inbox Event 状态

```text
unread -> read -> resolved
unread|read -> expired | dismissed
```

Interrupt projection 的 resolved/expired 必须由官方 Thread snapshot 对账，不能仅靠前端点击更新。

- `dismissed` 只适用于非阻塞通知。
- Interrupt 不支持静默 ignore；reject/cancel/expire 必须驱动 Graph 到明确终态或恢复动作。
- `expired` 由服务端策略和 Graph timeout response 产生，不能由客户端单方面设置。
- 多设备响应以 interrupt/checkpoint/version 幂等键进行乐观并发控制。

### 4.6 Entitlement 状态

```text
trial|active -> grace -> suspended -> cancelled
```

每个 Task 保存创建时的 entitlement snapshot；套餐变化影响新调用和后续预算，不篡改历史 usage。

连接展示状态不属于 Task/Run 状态机。React v1 可直接使用的公开状态以锁定 types 为准，例如 `error/isLoading/isThreadLoading/hydrationPromise`；`optimistic/hydrating/streaming` 也不得写入业务状态。

部分成功通过 `completion_scope`、warnings 和 artifact completeness 表达，不增加含糊的 `partial_success` 通用状态。

## 5. 重试所有权与预算

同一次外部调用只能由一层拥有重试。禁止 Graph Retry、Middleware Retry、Provider SDK Retry 和恢复逻辑同时叠加。

| 错误/动作 | 重试所有者 | 最大策略 | 总预算 | 幂等要求 |
| --- | --- | --- | --- | --- |
| Model transient | `ModelRetryMiddleware` | 最多 2 attempt | 单次 60s，Task model calls <= 4 | 无副作用 |
| Structured output invalid | Structured Output strategy | 最多 1 次 repair | 不与 ModelRetry 嵌套 | 保留失败样本 |
| Search transient | `ToolRetryMiddleware` | 最多 3 attempt | 总计 30s，尊重 Retry-After | 查询可重复 |
| Market GET transient | Market adapter | 最多 3 attempt | 总计 10s 且仍满足 freshness | 只读 |
| Graph node infrastructure | Graph RetryPolicy | 最多 2 attempt | task deadline 内 | node 幂等 |
| PostgreSQL transient | Repository transaction | 最多 2 attempt | 总计 5s，仅 serialization/deadlock | transaction/idempotency key |
| Notification | Outbox worker | 最多 5 attempt | 24h 后 terminal/unknown | deterministic message key |
| Webhook delivery | Delivery worker | 最多 5 attempt + DLQ | endpoint policy 内 | event ID |

每个 Task 具有最大 wall time、model calls、tool calls、search calls、tokens、cost 和 recursion。超过任一预算必须形成明确 `budget_exhausted`，不能静默切换廉价模型后继续输出最终风险结论。

Model Factory 必须显式记录 Provider/model integration 的 `max_retries`。启用 `ModelRetryMiddleware` 时关闭或限制 SDK 自带 retry，避免默认网络/429/5xx 重试与 Middleware/Graph 形成乘法。

## 6. 通知与外部副作用幂等

Bark 等通知不假设 Provider 支持 idempotency key。使用事务 Outbox：

```text
planned -> leased -> sending -> delivered
                         -> failed_retryable -> planned
                         -> failed_terminal
                         -> unknown
```

- `planned` 与最终业务结果在同一数据库事务创建。
- deterministic message key = workspace + task + channel + notification type + decision version。
- Worker 使用租约防并发重复发送。
- 发送超时且无法判断对方是否收到时标记 `unknown`，不自动无限重发。
- `unknown` 可人工确认或按渠道策略进行至多一次补发。
- 通知失败、unknown 或重复抑制不能改变 RiskVerdict。
- 所有 webhook/notification payload 脱敏并记录 hash，不默认保存完整 secret-bearing request。
- Agent Server webhook 只作为非关键完成提示，不假设具备业务所需的密码学签名和可靠投递保证；可靠 webhook 一律通过 Product Outbox、签名、重放保护、重试、DLQ 和审计。

## 7. LangSmith 与 Langfuse 去重

### 7.1 资产归属

| 资产 | 权威系统 |
| --- | --- |
| Agent/Graph/Tool/Model Trace 调试 | LangSmith |
| Dataset/Experiment/Release Evaluation | LangSmith |
| 生产 Session/User/Cost/Latency Dashboard | Langfuse |
| 业务反馈原始记录 | Product DB |
| Outcome 与金融质量 | Product DB + LangSmith Dataset snapshot |
| Prompt 发布 | 单独 ADR，只允许一个发布源 |

### 7.2 埋点策略

- LangSmith 使用 LangChain/LangGraph 自动 tracing。
- Langfuse 使用 ADR 0005 冻结的单一 CallbackHandler；如需切换 OTel fan-out，必须新增替代 ADR 并同步修改验收。
- Langfuse 使用当前推荐的 OTel masking 接口（实施时核对 `mask_otel_spans`），不依赖 legacy `mask` 配置。
- 禁止 Callback + 手工 generation 重复记录同一调用。
- 两个平台共享内部 correlation IDs，但各自拥有独立 trace ID。
- 采样决策、masking、queue size、flush timeout 和 exporter failure 由集中 Observability bootstrap 配置。
- 任一 exporter queue 满或服务不可用时丢弃观测数据并计数告警，不能阻断业务。
- Product DB `observability_links` 保存稳定 model/tool call ID 到 LangSmith child run 和 Langfuse observation 的映射。CI/集成测试按 call ID 断言每个 attempt 在每个平台恰有一条记录；Retry 是新 child，Resume 是新 root Run。
- Langfuse head sampling 不能在结束后补回失败 Trace：要么 100% 采集后用 retention 控制成本，要么只做统计采样，并由 Product Audit/LangSmith 全量保留 failed/blocked/negative-feedback/security 事件。

## 8. 数据分类与保留

| 数据类别 | 默认保留 | 可关闭 I/O | 删除要求 |
| --- | --- | --- | --- |
| Checkpoint | Task 完成后默认 30 天 | 否，运行必需 | Thread 删除后级联/合规保留 |
| Agent Store memory | 用户可控 | 可禁用 | 支持逐 namespace 删除 |
| 业务 Task/Run/Decision | 默认 365 天 | 不适用 | 账户/Workspace 删除策略 |
| Evidence/Artifact | 默认 365 天，可由套餐缩短 | 可限制正文 | 对象与索引一致删除 |
| Raw Prompt/Response | 默认不保存 | 是 | 开启时必须短保留 |
| LangSmith/Langfuse I/O | 租户策略 | 是 | 平台 retention/删除 API |
| Logs | 默认 30 天 | 敏感内容禁止 | 自动过期 |
| Backups | 默认 35 天轮换 | 不适用 | 删除传播到备份轮换周期 |
| Usage/Billing/Audit | 法律和财务要求 | 不适用 | 最小字段、合法保留 |

“零保留”必须按数据类别定义，不能只关闭 Trace input/output 后仍保存完整业务证据和模型输出却称为零保留。用户必须能够导出、删除和查看保留策略；合法保留和备份删除延迟必须明确披露。账户/Workspace 删除必须有跨 Product DB、Object Storage、Checkpoint、Store、LangSmith、Langfuse、日志和备份轮换的 E2E，在线系统 30 天内完成，备份在 35 天轮换内传播。

## 9. 威胁模型

### 9.1 主要威胁

- Prompt injection、工具诱导和恶意网页内容。
- SSRF、DNS rebinding、内网探测、重定向绕过和超大响应。
- Stored/reflected XSS、危险 Markdown URL 和 Artifact 注入。
- OAuth/API key 泄漏到 Prompt、State、Trace、日志或前端。
- 跨租户 IDOR、Thread/Run/Store 越权和管理员滥用。
- Tool entitlement 绕过、模型选择高成本 Tool 和预算消耗攻击。
- Webhook 伪造、重放和通知轰炸。
- 依赖供应链、容器、CI secret 和 Prompt/模型版本污染。

### 9.2 强制控制

- URL reader 禁止私网/metadata IP，解析后和每次 redirect 后重新校验 DNS/IP。
- 搜索/网页内容视为不可信数据，和 system/tool instructions 隔离。
- Markdown/Artifact 经过 sanitization、CSP 和安全链接策略。
- Secret Manager 保存密钥，Graph State 和产品 DTO 只引用 secret ID。
- Agent Server resource auth + Product Repository tenant filter + 数据库 RLS/复合约束形成多层隔离。
- Tool 列表在后端按 role/entitlement/Agent role 动态裁剪。
- Admin 跨租户操作需要显式 action、reason、审计和 break-glass 流程。
- 依赖、容器、IaC、secret 和 SAST/DAST 扫描进入发布门禁。

## 10. 金融产品边界

manual-only 不等于没有产品风险。正式上线前必须由产品/法律角色确认：

- 服务适用司法辖区和最低年龄。
- 市场信息、研究辅助和个性化投资建议的边界。
- 杠杆、入场、止损、止盈等字段允许在哪些套餐/地区展示。
- 用户首次使用和高风险功能的风险披露/确认。
- 不保证收益、历史表现不代表未来、数据延迟和模型错误披露。
- 禁止针对未支持产品、缺少事实或不满足风险问卷的个性化结论。
- 免责声明不能替代确定性风险门禁和审计。

实施阶段不得自行假设法律结论；未完成审核时产品保持内部/测试环境。

## 11. 量化 SLO 与发布阈值

具体数值在性能基线完成后通过 ADR 冻结，但以下指标不得缺失：

| 类别 | 必须定义 |
| --- | --- |
| Availability | API、Agent Server、stream、database 月度目标与错误预算 |
| Latency | request acknowledgement、首个可见事件、主流程 p50/p95/p99、长任务上限 |
| Stream | reconnect 成功率、重复事件率、乱序率、最大恢复窗口 |
| Quality | Structured Output 成功率、证据引用完整率、blocked/failed 误分类率 |
| Freshness | 每类行情和事件的最大可接受 age |
| Cost | 单 Run token/search/cost 上限和 workspace 月预算 |
| Capacity | 并发 Run、并发 stream、queue depth、worker saturation |
| Recovery | RTO、RPO、checkpoint 恢复成功率、通知 outbox 恢复 |
| Security | P0/P1 漏洞门槛、secret leak 为零、跨租户测试为零失败 |
| UX | Core Web Vitals、可访问性、视觉差异阈值、无重叠/横向溢出 |

任何指标未定义环境、样本量、时间窗和失败后的发布规则，都不能作为“工业级”验收证据。

## 12. Outcome 评测协议

“至少一个成熟 outcome”只能证明采集链路，不证明金融质量。Outcome protocol 必须版本化定义：

- prediction timestamp 和不可使用的未来信息。
- symbol、venue、horizon、maturity window 和价格源。
- action/blocked/no-trade label。
- entry/stop/target 命中顺序。
- 手续费、滑点和 funding 假设。
- hit、Brier、calibration、PnL、MFE、MAE 和 no-trade baseline。
- 最小样本量、分层样本、置信区间和异常市场分组。
- 模型/Prompt/规则版本变化后的可比性。
- 数据缺失、交易暂停和极端行情处理。

上线质量门禁必须同时考虑安全、证据质量、校准和 no-trade baseline，不能只优化名义 PnL。

## 13. 实施与发布变更记录

涉及数据库、身份、观测、通知或部署的实施说明还必须记录：

- Migration forward/rollback 和数据影响。
- Feature flag、canary 和回滚触发条件。
- Retention/隐私/安全审查。
- 成本和容量变化。
- Dashboard、alert、Runbook 和 on-call 变化。
- 发布批准人和证据链接。

## 14. 需要用户评审的决策

1. 是否接受产品在法律/风险边界确认前只作为内部和测试环境，不以“非投资建议”一句话替代审核。
2. 是否接受 Product PostgreSQL 作为 Task/Run/Artifact/Usage/Feedback/Outcome 权威，Checkpoint/Store/Trace 不承担产品查询。
3. 是否接受通知必须采用事务 Outbox，并将超时未知状态暴露给用户/运维。
4. 是否接受 LangSmith 与 Langfuse 各自单一职责，并通过 ADR 选择唯一 Prompt 发布源和 Langfuse 接入方式。
5. 是否接受实现前必须冻结部署许可、数据驻留、RTO/RPO、SLO 和 Outcome protocol，而不是用“生产级”作为无数值口号。
