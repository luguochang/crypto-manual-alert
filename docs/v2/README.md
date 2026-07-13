# Crypto Intelligence Agent V2 设计索引

> 状态：已批准进入 V2 Final 实施
>
> 基线日期：2026-07-13
>
> V1 归档：`codex/legacy-v1-backup-20260711` / `a44a7d2`
>
> V2 原型归档：`codex/v2-prototype-backup-20260713` / `b583e5a`

## 1. 本目录的作用

V2 不在 V1 的自研工作流、Agent Swarm 和兼容层上继续修补，也不把最终产品限制成一张“手工预警”页面。本目录先固定商业化 C 端 Agent 产品边界、官方框架职责、代码约束、交付门禁和实施记录方式。用户明确批准这些文档前，不得创建 V2 应用代码。

## 2. 文档清单

1. [01-V2产品与架构设计](./01-v2-product-and-architecture.md)
   - 产品目标、系统边界、主流程、数据模型、多用户钩子、前后端交互、可观测性和部署方案。
2. [02-官方框架使用与禁止自研约束](./02-official-framework-constraints.md)
   - LangChain、LangGraph、Deep Agents、LangSmith、Langfuse 的使用边界，以及禁止重复造轮子的静态门禁。
3. [03-V2交付检查清单](./03-v2-delivery-checklist.md)
   - 从设计批准到真实生产验证的阶段 Checklist 和完成证据。
4. [04-每轮实施说明模板](./04-implementation-note-template.md)
   - 每一轮代码变更必须填写的目标、官方接口、改动、测试、风险和下一步记录。
5. [05-官方文档调研证据矩阵](./05-official-research-evidence.md)
   - 当前官方 API、来源、版本状态、采用方式和禁止误用边界。
6. [06-C端Agent产品蓝图](./06-c-end-agent-product-blueprint.md)
   - 最终产品定位、信息架构、核心旅程、长任务、Artifact、商业化与分阶段启用边界。
7. [07-官方文档覆盖索引](./07-official-doc-coverage-index.md)
   - `llms.txt` 全量索引审计方法、相关文档族覆盖、关键 API 和实施前复核门禁。
8. [08-生产治理与非功能规范](./08-production-governance-and-nonfunctional.md)
   - 部署决策、数据权威、渐进持久化、重试、通知幂等、双观测去重、安全、保留、SLO 和 Outcome 协议。
9. [09-评审包与决策表](./09-review-packet-and-decisions.md)
   - 十分钟评审入口、统一决策编号、推荐结论、修改方式和批准范围。
10. [10-实施路线图](./10-implementation-roadmap.md)
   - 评审通过后的阶段顺序、每阶段入口/出口、真实主链证据和停止条件。
11. [ADR 索引](./adr/README.md)
   - 已接受的部署、Web Search、身份、前端组件、观测与 Prompt 发布源决策；生产部署仍受证据门禁约束。
12. [11-核心对象、权限与恢复契约](./11-core-object-access-recovery-contract.md)
   - Thread/Task/Run 基数、ACL、开发身份硬门禁、重连重建、Interrupt 竞态、移动端和可访问性。
13. [12-生产证明、SLO 与数据生命周期契约](./12-production-proof-slo-and-lifecycle.md)
   - 量化阈值、hosted Playwright、证据 hash、重试预算、通知 Outbox、删除演练和 V1 清理证明。
14. [13-V2 Final 选择性重构规格](./13-v2-final-rebuild-spec.md)
   - 已批准的迁移/重建/删除边界、锁定版本、最终架构和真实主链完成定义。
15. [14-V2 Final 实施计划](./14-v2-final-implementation-plan.md)
   - 按 TDD、两阶段审查和逐任务提交执行的完整重构与自测计划。

## 3. 已批准基线

以下决策已于 2026-07-13 由用户明确批准，并由 `13-v2-final-rebuild-spec.md` 与 `14-v2-final-implementation-plan.md` 统一实施语义：

- V2 使用同一 GitHub 仓库、独立工作树和独立分支，不污染 V1 归档分支。
- V2 的最终产品是多用户加密市场智能 Agent 工作空间；`manual_analysis` 只是首条跑通的业务模式，不是架构上限。
- `Workspace`、`Thread`、`Task`、`Run`、`Subagent`、`Artifact`、`Interrupt`、`Checkpoint` 和产品事件投影是第一等概念。
- V2 最终按多用户产品设计，但第一阶段使用固定开发身份跑通 Agent 主链。
- 所有业务表、Graph Runtime Context、Trace Metadata 从第一天携带 `tenant_id` 和 `user_id`。
- 顶层流程使用显式 LangGraph；模型、Tool、Structured Output 和 Middleware 使用 LangChain。
- Deep Agents 仅用于受限研究任务，不负责最终风险裁决、数据库写入和通知副作用。
- 事件体系采用三层官方能力：Python Agent `astream_events(..., version="v3")` 与 Graph `astream(..., stream_mode=...)`、Agent Server Protocol v2、`@langchain/react` v1 selector hooks；JavaScript 对应接口名为 `streamEvents`。不手写另一套 SSE、重放、去重或子 Agent 状态机。
- `@langchain/react` 是当前连接 live projection 的唯一客户端 Runtime；Product API/PostgreSQL 是历史和可查询产品状态权威。视觉层优先使用可编辑的成熟组件库；Generative UI 只能渲染受控组件注册表，不能执行模型生成的任意 JSX。
- LangSmith 与 Langfuse 同时接入，但不得在业务节点中散落双重手工埋点。
- Graph Checkpoint 与产品业务记录逻辑隔离、账号隔离且职责分离；同实例不同 schema、不同 database 或不同实例由部署 ADR 冻结。
- V2 仍是人工决策提醒系统，不提供自动下单、撤单、转账或提现。
- 商业化所需的 workspace、entitlement、usage、credit、subscription、integration 和审计钩子从第一天进入数据与权限边界，但不阻断首条真实主流程。

## 4. 设计评审门禁

开始实现前必须同时满足。用户已于 2026-07-13 明确批准按推荐方案进行完整重构和自测：

- [x] 用户批准 `01-v2-product-and-architecture.md`。
- [x] 用户批准 `02-official-framework-constraints.md`。
- [x] 用户批准 `03-v2-delivery-checklist.md` 的阶段顺序和完成定义。
- [x] 用户批准 `06-c-end-agent-product-blueprint.md` 的最终产品范围和分阶段启用策略。
- [x] `07-official-doc-coverage-index.md` 已覆盖事件流、子 Agent、Middleware、长任务、HITL、前端和生产运行时相关官方文档族。
- [x] 用户批准 `08-production-governance-and-nonfunctional.md` 的数据权威、幂等、安全、隐私、部署和量化验收边界。
- [x] 用户批准 `09-review-packet-and-decisions.md` 的推荐结论 D01-D15。
- [x] 用户批准 ADR 0001-0007 推荐结论；ADR 0008 仍以真实生产证据为接受条件。
- [x] 用户批准 `10-implementation-roadmap.md` 的阶段顺序、停止条件和证据要求。
- [x] 用户通过 D13 与 V2 Final 批准将 `11-core-object-access-recovery-contract.md` 纳入实施权威。
- [x] 用户通过 D13 与 V2 Final 批准将 `12-production-proof-slo-and-lifecycle.md` 纳入实施权威。
- [x] 新增 `13-v2-final-rebuild-spec.md` 与 `14-v2-final-implementation-plan.md` 作为实施权威入口。

## 5. 变更规则

实施阶段必须严格执行 `14-v2-final-implementation-plan.md`。每个任务先写失败测试、再写最小实现、完成两阶段代码审查，并追加中文实施记录；没有真实运行证据不得勾选交付项。
