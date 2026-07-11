# V2 最终交付 Checklist

> 状态：Draft for Review
>
> 原则：主流程优先，但最终产品范围不缩水。所有阶段均通过后才能声明 V2 可交付。

## 0. 设计批准

- [ ] 用户批准产品范围和 manual-only 边界。
- [ ] 用户批准 Agent Server + Next.js BFF 架构。
- [ ] 用户批准 Deep Agents 只用于受限研究域。
- [ ] 用户批准默认开发身份和正式 Auth 后置策略。
- [ ] 用户批准 LangSmith + Langfuse 职责划分。
- [ ] 用户批准 V1 只读归档、业务语义迁移、基础设施实现废弃。
- [ ] `docs/v2/` 不存在 `TODO`、`TBD` 和模糊完成条件。

完成证据：设计文档提交及用户明确确认。

## 1. Clean V2 Skeleton

- [ ] V2 应用目录不复制 V1 `src/crypto_manual_alert`。
- [ ] Python 使用最新兼容的 LangChain/LangGraph 1.x stable 版本并锁定。
- [ ] Deep Agents 锁定明确 0.x 版本。
- [ ] 前端使用 `@langchain/react` 和 `@langchain/langgraph-sdk`。
- [ ] `langgraph.json` 和单一 canonical graph 可被 `langgraph dev` 加载。
- [ ] PostgreSQL、Redis、Next.js 和 Agent Server 可在本地启动。
- [ ] 固定开发租户/用户能够进入 Runtime Context。
- [ ] LangSmith/Langfuse 可关闭，关闭后主链仍能运行。
- [ ] Import Contracts 和 forbidden-pattern CI 已启用。
- [ ] 第一份实施说明已创建。

完成证据：本地启动命令、health check、Graph schema、开发身份和 CI 输出。

## 2. Agent 主流程

### 2.1 请求与状态

- [ ] `AnalysisRequest` 支持 symbol、horizon、query_text 和 notify。
- [ ] `AnalysisState` 字段和 reducer 有 contract test。
- [ ] 每次运行生成 business ID、thread ID、run ID 和 request ID。
- [ ] queued/running/waiting_human/succeeded/blocked/failed/cancelled 语义固定。
- [ ] 失败不会 fallback 到 V1 或第二套 graph。

### 2.2 真实交易数据

- [ ] BTC/ETH/SOL 首批标的通过真实交易所公共接口。
- [ ] mark、index、ticker、funding、open interest、order book 可验证。
- [ ] source level 和 freshness 入库并展示。
- [ ] 限流、超时、过期、字段缺失和 symbol mismatch 均 fail-closed。
- [ ] Web Search 不能满足 exchange-native 事实门禁。

### 2.3 Web Research

- [ ] Provider capability probe 验证 built-in web search。
- [ ] 不支持 built-in 时使用明确配置的官方搜索 Tool。
- [ ] Deep Agent 只有 search/fetch 只读权限。
- [ ] Model/Tool call limit、retry、timeout 和 recursion limit 生效。
- [ ] 搜索查询、URL、发布时间、抓取时间、摘要和引用完整入库。
- [ ] 搜索不可用时页面明确显示，不生成伪结果。

### 2.4 Agent 分析

- [ ] 使用 `create_agent`，没有自定义 Agent Loop。
- [ ] 使用 Pydantic Structured Output。
- [ ] 输出包含方向、动作、置信度、价格、风险、失效条件和证据引用。
- [ ] 原始 provider payload 不直接成为产品 DTO。
- [ ] 模型、Prompt Version、Token、时延、成本和观测 ID 入库。

### 2.5 确定性门禁

- [ ] Evidence Gate 覆盖来源、freshness、symbol 和冲突。
- [ ] Risk Gate 覆盖 action、entry、stop、target、leverage、risk ratio 和 TTL。
- [ ] 多 confidence cap 取最低值。
- [ ] 模型无法覆盖 blocked 结果。
- [ ] 通知失败不改变 Decision/RiskVerdict。
- [ ] 所有规则是无网络、无数据库、无模型依赖的纯函数测试。

完成证据：Graph integration test、真实 Provider gated test、数据库记录和 LangSmith/Langfuse Trace。

## 3. 持久化与恢复

- [ ] 使用 PostgreSQL，不以 SQLite 作为生产主库。
- [ ] LangGraph Checkpoint 与 app business schema 分离。
- [ ] SQLAlchemy 2.x + Alembic 管理业务表。
- [ ] 所有业务表含 tenant_id，用户资源含 user_id。
- [ ] Repository 读取必须带 ActorContext。
- [ ] `persist_result` 事务与幂等通过并发测试。
- [ ] 通知使用 idempotency key。
- [ ] Agent Server 重启后 Thread 可恢复。
- [ ] waiting_human Interrupt 可恢复和响应。
- [ ] Retry 新建 Run 并记录 retry_of_run_id。
- [ ] Checkpoint 表不被产品 Repository 查询。

完成证据：PostgreSQL integration、重启恢复、重复提交和租户隔离测试。

## 4. 前端产品体验

### 4.1 官方 SDK

- [ ] 每个 Thread 只有一个根 `useStream`。
- [ ] 使用官方 submit/stop/respond/history。
- [ ] 浏览器不保存 LangSmith Secret Key。
- [ ] BFF 注入开发/生产身份和 correlation ID。
- [ ] 刷新和网络断线后可重新附着运行中的 Thread。

### 4.2 页面

- [ ] Dashboard 有真实最近运行和系统健康。
- [ ] Analyze 页面可提交并实时展示阶段。
- [ ] Runs 页面只显示当前用户数据。
- [ ] Run Detail 首屏展示结论、价格、风险和状态。
- [ ] 模型分析、交易事实、Web Evidence、风险门禁分区展示。
- [ ] Notification 和用户反馈可见。
- [ ] Settings 保留用户级配置钩子。
- [ ] Admin/Login 后置页面不阻断开发主链。

### 4.3 状态与可访问性

- [ ] 长耗时操作有进度，不允许重复提交。
- [ ] blocked 与 failed 文案和操作不同。
- [ ] Error Boundary、loading、empty、not-found 完整。
- [ ] 键盘、焦点、ARIA、对比度和 reduced-motion 通过检查。
- [ ] 桌面、平板、移动端无横向溢出和内容遮挡。
- [ ] 普通页面无 `<pre>` 原始 JSON、Python repr 和密钥。

完成证据：Playwright DOM assertions、visual snapshots、axe/a11y 检查和移动端深滚动截图。

## 5. Human-in-the-loop

- [ ] Interrupt Payload 有版本化 schema。
- [ ] 前端可以 approve/edit/reject。
- [ ] edit 后 Graph 使用用户输入继续，不重跑已完成副作用。
- [ ] reject 形成明确 cancelled/blocked 业务记录。
- [ ] 页面刷新后仍可处理待确认 Interrupt。
- [ ] 开发默认流程不强制 Interrupt，不阻断主链。

完成证据：Agent Server真实 Interrupt/Resume E2E。

## 6. LangSmith

- [ ] 自动 Trace 覆盖 Graph、Node、Agent、Tool 和 Model。
- [ ] tenant/user/thread/run/environment metadata 完整传播。
- [ ] 所有 child runs 含 thread_id/session_id。
- [ ] Prompt Version 可追踪。
- [ ] 建立最小 Dataset：正常、缺数据、过期、冲突、模型错误、通知错误。
- [ ] 离线 Experiment 可重复运行。
- [ ] Release Gate 包含结构、证据、风险和产品输出指标。
- [ ] Sensitive tenant 可 conditional tracing 或隐藏 I/O。

完成证据：LangSmith 项目链接/导出、Dataset ID、Experiment 结果和 release report。

## 7. Langfuse

- [ ] 官方 CallbackHandler 捕获 LangChain/LangGraph 调用。
- [ ] session_id 与 LangGraph thread_id 对齐。
- [ ] user_id 使用内部匿名 ID。
- [ ] Cost、latency、errors、model、tool 和 environment 可查询。
- [ ] Masking 在发送前处理密钥和 PII。
- [ ] Sampling 策略可配置。
- [ ] failed/blocked/negative-feedback 请求全量保留。
- [ ] Langfuse 不可用时主流程不失败。
- [ ] 没有 Callback + 手工 Generation 重复记录。

完成证据：Langfuse Trace、Dashboard、断网降级测试和去重检查。

## 8. 多用户正式启用

- [ ] 正式 Auth Provider 实现同一 IdentityProvider 契约。
- [ ] Agent Server resource auth 为 Thread/Run/Store 添加 owner/tenant metadata。
- [ ] Next.js Session 到 Agent Server 身份传播通过。
- [ ] 用户 A 不能读取、恢复、取消或反馈用户 B 的 Run。
- [ ] 租户 A 和租户 B 数据库查询隔离。
- [ ] Operator/Admin 权限有独立 action 和 audit event。
- [ ] 开发模式在生产构建中默认关闭。
- [ ] 无 Authorization 时生产请求 fail-closed。

完成证据：双用户/双租户 API、SDK 和 Playwright 安全测试。

## 9. V1 迁移与清理

- [ ] V2 production code 不 import V1 workflow/agent_swarm/orchestration。
- [ ] V1 业务规则逐条迁移并有 golden test。
- [ ] V1 SQLite 保持只读或一次性 ETL。
- [ ] 没有永久双写 V1/V2。
- [ ] 没有 legacy/candidate/controlled mode switch。
- [ ] 没有 fallback 回 V1 Prompt/Workflow。
- [ ] V1 历史页面明确标记 legacy archive。
- [ ] 旧代码删除清单完成并经 `rg`/import test 验证。

完成证据：静态 import gate、golden tests、ETL report 和删除 diff。

## 10. 自动化 QA

- [ ] Backend unit/integration 全通过。
- [ ] Frontend lint/typecheck/build 全通过。
- [ ] Playwright desktop/mobile 全通过。
- [ ] Visual snapshot 无未审查更新。
- [ ] API Schema/Zod contract 全通过。
- [ ] Graph resume/retry/interrupt/cancel 全通过。
- [ ] Provider timeout/rate-limit/malformed-output 全通过。
- [ ] Observability outage 不阻断测试通过。
- [ ] Secret scan、dependency audit 和 container scan 通过。
- [ ] 负载测试覆盖并发 Run、长研究和流式连接。

完成证据：CI run、HTML report、trace/video on failure、benchmark report。

## 11. 真实生产证明

- [ ] 公网 HTTPS Next.js 与 Agent Server 可访问。
- [ ] PostgreSQL/Redis 使用持久化和备份。
- [ ] 真实 OpenAI-compatible 模型 Structured Output 成功。
- [ ] 真实 Web Search 返回可验证来源。
- [ ] 真实交易所公共数据满足 exchange-native freshness。
- [ ] 同一次 Run 的模型、行情、搜索、风险、持久化和 Bark 均成功。
- [ ] Desktop/Mobile hosted visual gate 使用同一真实 Run。
- [ ] 生产错误、超时和恢复演练通过。
- [ ] 至少一个成熟 outcome 被收集和评分。
- [ ] no-trade baseline 和金融指标可查看。
- [ ] Runbook、告警、备份恢复和密钥轮换文档完成。

完成证据：同一 Run ID 的 API、页面、数据库、通知、LangSmith、Langfuse 和 outcome 证据包。

## 12. 最终完成定义

只有满足以下全部条件才可以声明“V2 最终版本完成”：

- [ ] 第 0-11 节所有 Checklist 均完成。
- [ ] 没有被跳过的 P0/P1。
- [ ] 没有用 mock/local proof 替代 hosted real proof。
- [ ] 没有隐藏失败、空 JSON、generic success 或 fallback success。
- [ ] 没有未批准的自定义 Runtime/Wrapper。
- [ ] 用户可以从浏览器真实完成主流程并读懂结果。
- [ ] 用户体系启用后不需要重写 Graph、表结构和产品 DTO。
- [ ] 文档、中文注释、实施说明和 Runbook 足以让新维护者排障。
