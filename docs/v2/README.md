# Crypto Manual Alert V2 设计索引

> 状态：设计评审中，禁止开始实现
>
> 基线日期：2026-07-11
>
> V1 归档：`codex/legacy-v1-backup-20260711` / `a44a7d2`

## 1. 本目录的作用

V2 不在 V1 的自研工作流、Agent Swarm 和兼容层上继续修补。本目录先固定最终产品边界、官方框架职责、代码约束、交付门禁和实施记录方式。用户明确批准这些文档前，不得创建 V2 应用代码。

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

## 3. 当前已冻结的决策

- V2 使用同一 GitHub 仓库、独立工作树和独立分支，不污染 V1 归档分支。
- V2 最终按多用户产品设计，但第一阶段使用固定开发身份跑通 Agent 主链。
- 所有业务表、Graph Runtime Context、Trace Metadata 从第一天携带 `tenant_id` 和 `user_id`。
- 顶层流程使用显式 LangGraph；模型、Tool、Structured Output 和 Middleware 使用 LangChain。
- Deep Agents 仅用于受限研究任务，不负责最终风险裁决、数据库写入和通知副作用。
- 前端使用官方 `@langchain/react` / LangGraph SDK 流式与 HITL 能力，不手写另一套 SSE 状态机。
- LangSmith 与 Langfuse 同时接入，但不得在业务节点中散落双重手工埋点。
- Graph Checkpoint 与产品业务记录分库存储、职责分离。
- V2 仍是人工决策提醒系统，不提供自动下单、撤单、转账或提现。

## 4. 设计评审门禁

开始实现前必须同时满足：

- [ ] 用户批准 `01-v2-product-and-architecture.md`。
- [ ] 用户批准 `02-official-framework-constraints.md`。
- [ ] 用户批准 `03-v2-delivery-checklist.md` 的阶段顺序和完成定义。
- [ ] 部署方式、Web Search Provider、生产鉴权 Provider 三个决策有明确结论。
- [ ] 不存在 `TBD`、`TODO` 或没有责任人的开放项。

## 5. 变更规则

设计评审期间只允许修改 `docs/v2/`。任何依赖、应用目录、数据库迁移、Docker 配置或前端页面改动，都视为提前实现，必须停止并回到设计评审。
