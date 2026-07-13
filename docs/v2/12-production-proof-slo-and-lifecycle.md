# V2 生产证明、SLO 与数据生命周期契约

> 状态：Approved
>
> 日期：2026-07-12
>
> 批准：用户，2026-07-13；通过 D13 与 V2 Final 规格/计划一并纳入实施权威

## 1. 量化 SLO 初始基线

| 指标 | Internal Alpha | External Beta | Commercial GA |
| --- | ---: | ---: | ---: |
| API/Agent Server 月度 availability | 测量，不承诺 | 99.5% | 99.9% |
| 请求确认 p95 | <= 1s | <= 1s | <= 1s |
| 首个可见阶段事件 p95 | <= 3s | <= 3s | <= 3s |
| market analysis p95 | <= 150s | <= 120s | <= 120s |
| market analysis hard deadline | 180s | 180s | 180s |
| reconnect 成功率 | >= 98% | >= 99% | >= 99.5% |
| 重复产品事件率 | < 0.1% | < 0.05% | < 0.01% |
| Structured Output 成功率 | >= 97% | >= 99% | >= 99.5% |
| allowed 结果 Evidence 引用完整率 | 100% | 100% | 100% |
| checkpoint/recovery 成功率 | >= 95% | >= 99% | >= 99.5% |
| 跨租户/secret 泄漏 | 0 | 0 | 0 |

每个指标必须记录环境、样本数、时间窗、测量查询和失败后的发布规则。未达到阈值时不能用平均值或单次成功覆盖。

## 2. Hosted Playwright 证明

生产视觉证据必须满足：

- `baseURL` 是公网 HTTPS 部署，不是 localhost、private IP 或隧道到本地 fixture。
- 禁止 `page.route`、HAR mock、mock model/search/market/notification endpoint 和静态 seed 结果。
- 报告记录 frontend URL、Agent Server URL、Git commit、容器 image digest、配置 profile、开始/结束时间。
- API gate 先创建真实 Run，桌面和移动端 Playwright 都打开同一个 `task_id/run_id/artifact_id`。
- 保存 HTML report、JUnit、desktop/mobile screenshot、trace、video 和失败网络日志。
- DOM 断言验证真实 model、search、exchange-native market、risk、database 和 notification proof ID 一致。
- 测试后从产品 API、数据库只读查询和 LangSmith/Langfuse 验证同一 correlation ID。

手工截图、本地 Playwright、fixture hosted runtime 或不同 Run 的桌面/移动截图均不能满足此门禁。

## 3. 渐进持久化与 Domain Event

每个外部成本阶段提交完整、可恢复的 domain payload：

```text
market.snapshot.committed
research.evidence.committed
agent.output.committed
evidence.verdict.committed
risk.verdict.committed
artifact.committed
notification.planned
run.terminal
```

事件至少包含 `event_id`、`task_id`、`run_id`、`checkpoint_id`、`schema_version`、`payload_ref/hash`、`sequence` 和时间。Graph State 保存 ID/摘要；Product DB/Object Storage 保存完整业务 payload。`commit_final_artifact` 只提交最终聚合，不承担前面阶段的补救性大写入。

## 4. Run 状态映射

Agent Server/Checkpointer 是执行活性的权威，Product PostgreSQL 是用户状态与审计权威。映射器必须版本化：

| Runtime | Product Run |
| --- | --- |
| pending/queued | queued |
| running | running |
| interrupt | waiting_human |
| success | succeeded/blocked，取决于业务 verdict |
| cancelled | cancelled |
| error | failed |
| 无 active run 但有可恢复 checkpoint | `running` + `recovery_status=pending` |
| 无 active run 且不可恢复 | `failed` + `failure_code=orphaned` |

`degraded`、`recovery_pending` 和 `orphaned_failed` 都不是 Run 状态：完整度通过 `completion_scope + warnings + artifact completeness` 表达，恢复过程通过 `recovery_status`表达，不可恢复原因通过 `failure_code=orphaned` 表达。最大投影延迟：运行中 5 秒，终态 2 秒；超过阈值告警并进入 reconciliation。

## 5. 不可变行情与 Web Evidence

市场事实必须保存：

- venue、symbol、endpoint/operation。
- exchange server timestamp、client received timestamp、时钟偏差。
- 原始响应 hash、标准化 schema/version、关键原始字段或受控对象存储引用。
- freshness policy/version 和 source level。

Web Evidence 必须保存：

- query、最终 URL、redirect chain、HTTP status、抓取时间、页面发布时间。
- 内容 snapshot 或合规允许的 excerpt/object reference、content hash、parser version。
- 标题、作者/来源、引用片段、与结论的 evidence relation。

URL 后续失效时仍能证明模型和门禁当时使用了什么内容；受版权/隐私限制时至少保存 hash、引用片段和抓取元数据。

## 6. 数值化重试合同

| 调用 | 唯一 owner | 最大 attempt | deadline/budget |
| --- | --- | ---: | --- |
| Model transient | ModelRetryMiddleware | 2 | 单次 60s，Task model calls <= 4 |
| Structured repair | Structured Output strategy | 1 repair | 不再嵌套 ModelRetry |
| Web Search | ToolRetryMiddleware | 3 | 总计 30s，尊重 Retry-After |
| Market GET | Market adapter | 3 | 总计 10s，必须仍满足 freshness |
| PostgreSQL transaction | Repository | 2 | 总计 5s，serialization/deadlock only |
| Notification Outbox | worker | 5 | 指数退避，24h 后 terminal/unknown |
| Webhook | delivery worker | 5 | 进入 DLQ |

所有 attempt 写入 ledger，保存 owner、原因、延迟、Retry-After、成本和结果。Provider SDK `max_retries=0` 或明确计入上述 attempt，不能形成乘法。

## 7. Notification Outbox

- message key 有数据库唯一约束：`workspace + task + channel + type + decision_version`。
- 相同 key 不同 payload hash 是冲突，进入人工审计，禁止覆盖。
- lease 包含 owner、expires_at 和 fencing token；旧 worker 不能在租约失效后提交状态。
- 超时无法确认是否送达标记 `unknown`，默认不自动补发。
- 人工补发创建新的 attempt，但保持同一 logical notification 和审计链。
- Graph 只创建 `planned`，不直接调用 Bark。

## 8. LangSmith/Langfuse 去重合同

Product DB `observability_links` 保存：

- correlation ID、task/run/node/agent/tool/model call ID。
- LangSmith root/child run ID。
- Langfuse trace/observation ID。
- attempt、resume/retry lineage。

一次模型 attempt 在每个平台恰有一个 generation/LLM child；Retry 是新 child，Resume 是新 root Run 并引用原 Run。Tool 内模型调用必须有独立 call ID。集成测试按 call ID 查询两平台，断言 cardinality，而不是只看名称。

## 9. 保留、导出与删除

初始默认：

| 数据 | 默认保留 |
| --- | --- |
| Product Task/Run/Decision/Usage | 365 天 |
| Artifact/Evidence | 365 天，可由套餐缩短 |
| Checkpoint/technical projections | Task 完成后 30 天 |
| Agent Store memory | 用户控制，删除立即进入队列 |
| Raw Prompt/Response | 默认不保存 |
| 应用日志 | 30 天 |
| LangSmith/Langfuse I/O | 30 天，敏感租户可禁用 |
| 在线备份 | 35 天轮换 |
| 财务/安全审计最小字段 | 按适用法律单独保留 |

账户/Workspace 删除 E2E 必须覆盖 Product DB、Object Storage、Checkpoint、Store、搜索索引、LangSmith、Langfuse、日志和备份删除队列。在线系统 30 天内完成；备份在 35 天轮换内完成，合法保留例外必须对用户披露。导出包含 schema/version/hash 清单并校验完整性。

## 10. Outcome 分级门禁

- Pipeline proof：至少 1 个成熟可评分 outcome，只证明采集、成熟和评分链路。
- External Beta 报告：至少 50 个样本，覆盖首发 3 个标的和至少 14 天；仅展示描述性指标和宽置信区间。
- GA 金融质量报告：至少 200 个样本，覆盖至少 30 天、3 个标的、不同 regime；报告 calibration、Brier、MFE/MAE、fees/slippage/funding 和 no-trade baseline。
- 若样本不足或结果显著差于 baseline，不得宣称金融质量已证明；产品仍可作为研究辅助，但必须展示限制。

## 11. V1 迁移和生产制品清理

必须建立机器可读 manifest：

```text
v1_rule_id -> v2_rule_id -> golden_test -> status
v1_table -> v2_table/legacy_readonly -> row_count/checksum -> status
v1_path -> migrate/delete/archive -> verification
```

生产镜像和依赖扫描禁止包含 V1 `workflow`、`orchestration`、`agent_swarm`、`research_pipeline`、旧 LLM clients、ToolExecutor、telemetry runtime 和前端 fallback 实现。Legacy 只读页面若保留，必须独立制品或静态归档，不进入 V2 Runtime image。

## 12. 实施说明可审计性

- 每个实现 slice 创建新的说明文件，不覆盖历史文件。
- 文件名含日期和唯一 slice ID；front matter 保存 commit/PR、owner、phase、status。
- CI 校验代码变更必须关联一份新增说明；文档-only 和机械依赖更新可显式豁免。
- 说明中的命令、Trace/Run/截图链接必须可访问，测试结果必须含退出码和数量。
- 若本轮没有真实运行，只能标记 slice 未达到真实证据出口，不能把该阶段记为完成。

## 13. 完成门禁

只有本契约、`03-v2-delivery-checklist.md`、Accepted ADR 和真实 hosted evidence 同时通过，才允许使用“生产可交付”描述。任何单一绿色测试、单个 outcome、本地 Docker 或手工截图均不是替代证据。
